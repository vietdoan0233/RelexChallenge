"""Role-aware source redaction (CLAUDE.md 18.1.1, 18.7).

Sanitizes the *structure* the parsers read, not only the body text: a
speaker-marker line, a From/Von/Från header, an Attendees list, a
recipient list, and a signature block all identify a person just as well
as an inline mention. The reserved markers are irreversible and generic;
nothing here records which person they replaced.

Only tracked identifiers (canonical name, reviewed aliases, emails) are
replaced. Redaction is purely textual and deterministic, so applying it to
a parsed unit's text gives the same result as parsing the redacted source
-- which the privacy service relies on and verifies before committing.
"""

import re

from app.core import anonymous_labels as labels
from app.ingestion.text_utils import split_top_level
from app.privacy import orgs as orgs_mod
from app.privacy.targets import Target, name_pattern

_SENDER_HEADER = re.compile(r"^(?P<label>\s*(?:From|Von|Från)\s*:)(?P<value>.*)$", re.IGNORECASE)
_RECIPIENT_HEADER = re.compile(
    r"^(?P<label>\s*(?:To|Cc|Bcc|An|Till|Kopia)\s*:)(?P<value>.*)$", re.IGNORECASE
)
_ATTENDEES_HEADER = re.compile(r"^(?P<label>\s*Attendees\s*:)(?P<value>.*)$", re.IGNORECASE)
_TIME_PHRASE = re.compile(r"\s+\d+\s+(?:minutes?|seconds?|hours?)\b", re.IGNORECASE)
# A signature block is the run of non-blank lines that follows a line holding
# only the person's name; capped so a missing blank line cannot swallow a body.
_MAX_SIGNATURE_LINES = 6


def content_is_empty(text: str) -> bool:
    """True when nothing but reserved markers and punctuation is left."""
    stripped = labels.redaction_marker_pattern().sub("", text)
    return not re.search(r"\w", stripped)


def sanitize_text(
    text: str, kind: str, target: Target, orgs: orgs_mod.OrgContext | None = None
) -> str:
    """`kind` is 'transcripts', 'emails' or 'reports' (the source subfolder).

    With an `orgs` context the markers keep the person's organisation
    ("[REDACTED SPEAKER: RELEX]"): the name goes, "someone from company X"
    stays. Without one the markers are the plain generic forms."""
    patterns = [name_pattern(n) for n in target.names]
    email_patterns = [re.compile(re.escape(e), re.IGNORECASE) for e in target.emails]
    initials = target.initials
    org = orgs_mod.doc_org(text, target, orgs) if orgs else None

    def mark(base: str, entry: str = "") -> str:
        entry_org = (orgs.from_parenthetical(entry) or orgs.from_address(entry)) if orgs else None
        return labels.redaction_marker(base, entry_org or org)

    def is_bare_name(line: str) -> bool:
        stripped = line.strip()
        return any(p.fullmatch(stripped) for p in patterns)

    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        if kind == "transcripts":
            if is_bare_name(line):
                out.append(mark(labels.REDACTED_SPEAKER))
                i += 1
                continue
            if len(initials) >= 2 and line.strip() == initials:
                i += 1  # bare initials chip: UI chrome derived from the name
                continue
            marker = _speaker_marker_line(line, patterns, mark(labels.REDACTED_SPEAKER))
            if marker is not None:
                out.append(marker)
                i += 1
                continue

        if kind in ("emails", "reports") and is_bare_name(line):
            # Signature: drop the name and the contiguous block under it
            # (job title, phone, email), which identify the person too.
            i += 1
            dropped = 0
            while i < len(lines) and lines[i].strip() and dropped < _MAX_SIGNATURE_LINES:
                i += 1
                dropped += 1
            continue

        header = _SENDER_HEADER.match(line)
        if header and _mentions(header.group("value"), patterns, email_patterns):
            sender = mark(labels.REDACTED_SENDER, header.group("value"))
            out.append(f"{header.group('label')} {sender}")
            i += 1
            continue

        for regex in (_RECIPIENT_HEADER, _ATTENDEES_HEADER):
            header = regex.match(line)
            if header and _mentions(header.group("value"), patterns, email_patterns):
                line = _redact_list_header(header, patterns, email_patterns, mark)
                break
        out.append(_inline(line, patterns, email_patterns, mark(labels.REDACTED_PERSON)))
        i += 1
    # A name hard-wrapped across a line break ("Kwame\nBoateng") is invisible to
    # the per-line pass above, so sweep the whole text once more. The patterns
    # already tolerate any whitespace between a name's words.
    return _inline("\n".join(out), patterns, email_patterns, mark(labels.REDACTED_PERSON))


def _mentions(value: str, patterns, email_patterns) -> bool:
    return any(p.search(value) for p in (*patterns, *email_patterns))


def _inline(line: str, patterns, email_patterns, marker: str) -> str:
    for pattern in email_patterns:
        line = pattern.sub(marker, line)
    for pattern in patterns:
        line = pattern.sub(marker, line)
    return line


def _speaker_marker_line(line: str, patterns, marker: str) -> str | None:
    """'Name 4 minutes 39 seconds' -> '[REDACTED SPEAKER] 4 minutes 39 seconds'."""
    stripped = line.strip()
    for pattern in patterns:
        match = pattern.match(stripped)
        if match and _TIME_PHRASE.match(stripped[match.end() :]):
            return f"{marker}{stripped[match.end() :]}"
    return None


def _redact_list_header(header, patterns, email_patterns, mark) -> str:
    """Replace each Attendees/To/Cc entry that names the target with an
    anonymous marker. The entry is kept (as "[REDACTED PERSON: RELEX]"), not
    dropped, so the record still shows that someone from that organisation was
    there -- and, for Attendees, the job title in the parenthetical goes."""
    is_attendees = header.group("label").strip().lower().startswith("attendees")
    sep = "," if is_attendees else ";"
    entries = split_top_level(header.group("value"), sep)
    if len(entries) <= 1 and not is_attendees:
        entries = split_top_level(header.group("value"), ",")
        sep = ","
    kept = []
    for entry in entries:
        if _mentions(entry, patterns, email_patterns):
            kept.append(mark(labels.REDACTED_PERSON, entry))
        else:
            kept.append(entry)
    joiner = f"{sep} "
    return f"{header.group('label')} {joiner.join(kept)}".rstrip()
