import re
import sqlite3
import unicodedata

from app.core import anonymous_labels
from app.db import repository
from app.ingestion import locator_manifest
from app.ingestion.models import ParsedDocument, ParsedUnit, TranscriptFragment
from app.ingestion.text_utils import is_truncated_text, split_top_level, strip_parenthetical

_HEADER_FIELD = re.compile(r"^(Meeting|Customer|Date|Phase|Attendees):\s*(.*)$")
_DISCLAIMER_PREFIX = "***"

_DOUBLED_TIMESTAMP = re.compile(r"^(\d{1,2}:\d{2})\1$")
_TIME_PHRASE = re.compile(r"^\s*(?:(\d+)\s+minutes?)?\s*(?:(\d+)\s+seconds?)?\s*$")
_INTERNAL_LINE = re.compile(r"^(Me|Them):\s?(.*)$")

# A participant absent from the Attendees header, which Teams can only
# label by phone number ("+358 40 5512 097") or generically ("Guest 1").
# The lazy phone group plus a mandatory minutes/seconds tail is what
# splits "+358 40 5512 097 6 minutes 17 seconds" at the right place -- the
# duration digits are otherwise indistinguishable from the number's own.
_UNLISTED_MARKER = re.compile(
    r"^(\+\d[\d ]*?\d|Guest \d+)\s+(\d+\s+minutes?(?:\s+\d+\s+seconds?)?|\d+\s+seconds?)$"
)
# The avatar chip Teams draws for such a participant on its own line: a
# "+" and a short digit run for a number ("+4"), "G" and digits for a
# guest ("G1").
_UNLISTED_CHIP = re.compile(r"^(?:\+\d{1,3}|G\d+)$")

_LENGTH_PRESERVING_MAP = str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A"})


def _normalize_name(name: str) -> str:
    """Case/diacritic-insensitive comparison key, deliberately
    length-preserving (each input character maps to exactly one output
    character) so a match against a normalized name can still be sliced
    out of the original, un-normalized line by that name's length. This
    exists because the corpus itself is inconsistent: the Attendees
    header spells a name "Henrik Sorensen" with an o-with-stroke, but
    that speaker's own caption lines render it with a plain "o"."""
    translated = name.translate(_LENGTH_PRESERVING_MAP)
    decomposed = unicodedata.normalize("NFKD", translated)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def parse(text: str, document_id: str, filename: str) -> ParsedDocument:
    lines = text.splitlines()
    header, body_start = _parse_header(lines)
    body_lines = lines[body_start:]

    doc = ParsedDocument(
        document_id=document_id,
        filename=filename,
        document_type="TRANSCRIPT",
        title=header.get("Meeting"),
        source_date=header.get("Date"),
        thread_context=header.get("Meeting"),
    )

    if any(_INTERNAL_LINE.match(line.strip()) for line in body_lines if line.strip()):
        doc.attendees = _parse_attendees(header.get("Attendees", ""))
        doc.fragments = _parse_internal(body_lines)
    else:
        attendees = _parse_attendees(header.get("Attendees", ""))
        if not attendees:
            doc.warnings.append(
                "no Attendees header found; Teams speaker matching will find nothing"
            )
        doc.attendees = attendees
        doc.fragments = _parse_teams(body_lines, attendees)

    return doc


def _parse_header(lines: list[str]) -> tuple[dict[str, str], int]:
    header: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(_DISCLAIMER_PREFIX):
            body_start = i + 1
            continue
        match = _HEADER_FIELD.match(stripped)
        if match:
            header[match.group(1)] = match.group(2).strip()
            body_start = i + 1
        elif header:
            # First non-header, non-blank line after we've seen at least
            # one header field: the header block has ended.
            break
        else:
            body_start = i + 1
    return header, body_start


def _parse_attendees(attendees_line: str) -> list[str]:
    names = []
    for entry in split_top_level(attendees_line, ","):
        name = strip_parenthetical(entry)
        if name:
            names.append(name)
    return names


def _initials(name: str) -> str:
    return "".join(word[0] for word in name.split() if word).upper()


# ------------------------------------------------------------ Teams format


def _parse_teams(body_lines: list[str], attendees: list[str]) -> list[TranscriptFragment]:
    # "Unknown Speaker" is a genuine Teams UI artifact, not a hypothetical
    # one: some turns are captioned that way because Teams itself could
    # not identify who was talking. "[REDACTED SPEAKER]" is the reserved
    # marker a future anonymization operation writes in its place
    # (CLAUDE.md 18.7). Both follow the exact same name/timestamp/
    # initials structure as a named turn, so both must be recognized as
    # marker lines in their own right -- otherwise that dialogue silently
    # merges into whichever named speaker's turn happened to precede it,
    # a real misattribution rather than a cosmetic gap, or (for a
    # redacted turn specifically) the sanitized content is silently
    # dropped as untraceable chrome instead of surviving as an anonymous
    # unit.
    canonical_names = [
        *attendees,
        anonymous_labels.ANONYMOUS_SPEAKER_LABEL_UNKNOWN,
        anonymous_labels.REDACTED_SPEAKER,
    ]
    name_by_normalized = {_normalize_name(name): name for name in canonical_names}
    known_initials = {_initials(name) for name in canonical_names}

    fragments: list[TranscriptFragment] = []
    current_lines: list[str] | None = None
    current_speaker = None
    current_seconds = None
    current_timestamp_text = None

    def flush() -> None:
        if current_speaker is None:
            return
        text = " ".join(current_lines).strip()
        if text:
            fragments.append(
                TranscriptFragment(
                    raw_text=text,
                    speaker_sender=current_speaker,
                    timestamp_text=current_timestamp_text,
                    natural_locator=f"t{current_seconds}",
                )
            )

    lines = [raw_line.strip() for raw_line in body_lines]
    previous_was_timestamp_chrome = False

    for index, line in enumerate(lines):
        if not line:
            continue
        follows_timestamp_chrome = previous_was_timestamp_chrome
        previous_was_timestamp_chrome = False

        if _normalize_name(line) in name_by_normalized:
            continue  # bare speaker-name chrome from the Teams UI
        if _DOUBLED_TIMESTAMP.match(line):
            previous_was_timestamp_chrome = True
            continue  # duplicated timestamp chrome
        if line in known_initials:
            continue  # bare initials chrome
        # An unlisted participant's chrome is dropped only where its
        # position proves it is chrome, never on shape alone: it has no
        # roster name to match, so a lone "+..." or "G1" line that happens
        # to be caption text must stay in the turn it belongs to.
        if _is_bare_unlisted_label_chrome(line, lines, index):
            continue
        if follows_timestamp_chrome and _UNLISTED_CHIP.match(line):
            continue

        marker = _match_marker(line, name_by_normalized)
        if marker:
            flush()
            current_speaker, current_seconds, current_timestamp_text = marker
            current_lines = []
        elif current_lines is not None:
            current_lines.append(line)
        # A stray line before any marker has been seen is untraceable
        # chrome/noise; dropping it is safe since it precedes real content.
    flush()

    return fragments


def _is_bare_unlisted_label_chrome(line: str, lines: list[str], index: int) -> bool:
    """A lone phone-number / "Guest N" line is UI chrome only when the
    next non-blank line is the doubled timestamp that always follows a
    bare name line."""
    if not anonymous_labels.is_unlisted_participant_label(line):
        return False
    for following in lines[index + 1 :]:
        if following:
            return _DOUBLED_TIMESTAMP.match(following) is not None
    return False


def _duration_seconds(rest: str) -> int | None:
    match = _TIME_PHRASE.match(rest)
    if match and (match.group(1) or match.group(2)):
        return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    return None


def _match_marker(line: str, name_by_normalized: dict[str, str]) -> tuple[str, int, str] | None:
    normalized_line = _normalize_name(line)
    for normalized_name, canonical_name in name_by_normalized.items():
        if normalized_line.startswith(normalized_name):
            rest = line[len(normalized_name) :]
            total = _duration_seconds(rest)
            if total is not None:
                return canonical_name, total, rest.strip()

    unlisted = _UNLISTED_MARKER.match(line)
    if unlisted:
        # The speaker label is the literal number/"Guest N" from the
        # source; nothing is inferred about who the participant is.
        rest = line[len(unlisted.group(1)) :]
        total = _duration_seconds(rest)
        if total is not None:
            return unlisted.group(1), total, rest.strip()
    return None


# --------------------------------------------------------- INTERNAL format


def _parse_internal(body_lines: list[str]) -> list[TranscriptFragment]:
    fragments: list[TranscriptFragment] = []
    for raw_line in body_lines:
        line = raw_line.strip()
        if not line:
            continue
        match = _INTERNAL_LINE.match(line)
        if not match:
            continue
        speaker, text = match.group(1), match.group(2).strip()
        if text:
            fragments.append(
                TranscriptFragment(raw_text=text, speaker_sender=speaker, natural_locator=None)
            )
    return fragments


# ---------------------------------------- locator assignment + safe merge


def assign_locators_and_merge(
    conn: sqlite3.Connection, document_id: str, fragments: list[TranscriptFragment]
) -> list[ParsedUnit]:
    """Assigns every fragment a stable (locator, genesis_position) pair,
    then merges consecutive same-speaker fragments into one Evidence Unit
    -- but ONLY when their genesis positions are also consecutive.

    That second condition is the whole point. Teams splits one
    continuous utterance into several caption fragments, and those
    should merge into a single turn. But in an alternating two-party
    dialogue, deleting a turn makes its two neighbors -- necessarily the
    same speaker -- newly adjacent in the file; naively merging same-
    speaker neighbors would fuse them into a turn that never actually
    happened as one continuous utterance. A genesis-position gap is what
    tells these two situations apart: it survives even though the file's
    *current* adjacency does not.
    """
    natural = [f.natural_locator for f in fragments]
    fingerprints = [repository.fingerprint(f.raw_text) for f in fragments]

    assignments: list[locator_manifest.LocatorAssignment] = [None] * len(fragments)  # type: ignore[list-item]
    pending_indices = [i for i, loc in enumerate(natural) if loc is None]

    for i, loc in enumerate(natural):
        if loc is not None:
            assignments[i] = locator_manifest.assign_natural_locator(
                conn, document_id, loc, fingerprints[i]
            )

    if pending_indices:
        pending_fps = [fingerprints[i] for i in pending_indices]
        pending_assignments = locator_manifest.assign_manifest_locators(
            conn, document_id, pending_fps
        )
        for i, assignment in zip(pending_indices, pending_assignments, strict=True):
            assignments[i] = assignment

    groups: list[dict] = []
    for fragment, assignment in zip(fragments, assignments, strict=True):
        same_speaker = groups and groups[-1]["speaker"] == fragment.speaker_sender
        consecutive = groups and assignment.genesis_position == groups[-1]["last_position"] + 1
        if same_speaker and consecutive:
            groups[-1]["lines"].append(fragment.raw_text)
            groups[-1]["last_position"] = assignment.genesis_position
        else:
            groups.append(
                {
                    "speaker": fragment.speaker_sender,
                    "lines": [fragment.raw_text],
                    "locator": assignment.source_locator,
                    "timestamp_text": fragment.timestamp_text,
                    "last_position": assignment.genesis_position,
                }
            )

    units = []
    for group in groups:
        text = " ".join(group["lines"]).strip()
        if not text:
            continue
        units.append(
            ParsedUnit(
                raw_text=text,
                speaker_sender=group["speaker"],
                timestamp_text=group["timestamp_text"],
                is_truncated=is_truncated_text(text),
                natural_locator=group["locator"],  # already a manifest-registered value
            )
        )
    return units
