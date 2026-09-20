"""People and alias discovery.

A name becomes a deletion-relevant `people` row only through a high-
confidence source:

1. a transcript speaker or attendee,
2. an email/report sender with a display name or address,
3. an entry in the reviewed text-only identity manifest
   (data/source/reviewed_identities.json).

A capitalized free-text span is never sufficient on its own. Earlier code
promoted every two/three-word capitalized match straight into `people`,
which is what produced false identities such as "Risk Fresh Phase" and
"This So" -- noise indistinguishable, to the deletion pipeline, from a
real person. Free-text matches are now candidates only: reported for
human review, and inserted as a person only when they exactly match a
manifest entry that a human already reviewed against its cited evidence.

Short-form aliases (first name, last name, initials, nicknames, spelling
variants) are gated the same way, and more strictly than an earlier
version of this module assumed: a candidate being unique AND used
somewhere in the corpus on its own is *not* proof it refers to the
confirmed person it was derived from -- it is only proof that a human
should look at it. The only way a short-form alias becomes
deletion-relevant is an explicit entry in the manifest's
`verified_aliases`, each carrying its own alias_type and a reviewable
source_reference. Every derivable short-form candidate that isn't
covered by such an entry is reported as unresolved, never promoted.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core import anonymous_labels
from app.core.enums import AliasType, PersonRelation
from app.db import repository
from app.ingestion import name_resolution
from app.ingestion.models import ParsedDocument
from app.ingestion.text_utils import strip_image_placeholders

_FULL_NAME = re.compile(r"\b[A-ZÅÄÖØÆÉ][a-zåäöøæé'-]+(?:[ \t]+[A-ZÅÄÖØÆÉ][a-zåäöøæé'-]+){1,2}\b")

# A manifest verified_aliases entry may not redeclare FULL_NAME: that alias
# is always assigned automatically from canonical_name, and letting the
# manifest also specify it would create two competing sources for the same
# fact.
_MANIFEST_ALIAS_TYPES = {t.value for t in AliasType if t is not AliasType.FULL_NAME}

# Capitalized bigrams/trigrams that match the full-name shape but are
# roles or recurring phrases, not people -- drawn from this corpus's own
# job titles, status-report jargon, and email-signature boilerplate.
# This stoplist is a candidate-quality aid only, not the identity
# boundary: even a phrase that slips past it can never become a `people`
# row on its own, because free-text matches are never auto-promoted.
_NAME_STOPLIST = {
    "Solution Consultant",
    "Project Manager",
    "Account Executive",
    "Solution Architect",
    "Technical Consultant",
    "Service Delivery",
    "Account Director",
    "Category Manager",
    "Data Protection",
    "Integration Lead",
    "Master Data",
    "Go Live",
    "Business Review",
    "Steering Committee",
    "Plan Better",
    "Sell More",
    "Waste Less",
    "Connect With",
    "Best Regards",
    "Kind Regards",
    "Supply Chain",
    "On Track",
    "Slight Delay",
    "West Europe",
    "Business Configuration",
    "Technical Implementation",
    "Project Initiation",
    "Store User",
}


class ManifestValidationError(ValueError):
    """The reviewed identity manifest is malformed. Raised before any
    destructive ingestion work happens, so a bad manifest edit fails
    loudly instead of silently emptying the database (see service.ingest)."""


@dataclass
class VerifiedAlias:
    alias: str
    alias_type: str
    source_reference: str = ""


@dataclass
class ReviewedIdentity:
    canonical_name: str
    verified_aliases: list[VerifiedAlias]
    review_note: str
    source_documents: list[str] = field(default_factory=list)


@dataclass
class PeopleReport:
    # people_count/alias_count are filled in by the caller from actual
    # post-commit SQL counts, never from attempted-insert tallies -- the
    # two can differ (INSERT OR IGNORE silently no-ops on a duplicate),
    # and only the real stored count is safe to report.
    people_count: int = 0
    alias_count: int = 0
    unresolved_alias_candidates: list[str] = field(default_factory=list)
    reviewed_text_only: list[str] = field(default_factory=list)
    reviewed_short_aliases: list[str] = field(default_factory=list)
    rejected_candidates: list[str] = field(default_factory=list)
    relation_counts: dict[str, int] = field(default_factory=dict)


def load_reviewed_identities(source_dir: Path) -> list[ReviewedIdentity]:
    """Reads and validates the human-reviewed text-only identity manifest.
    Lives beside (not inside) the emails/reports/transcripts
    subdirectories, so enumerate_source_files never mistakes it for an
    evidence document. Raises ManifestValidationError on any structural
    problem -- required fields, duplicate identities/aliases, an
    unsupported alias_type, or an empty value -- so a malformed edit is
    caught before ingestion touches the database at all."""
    manifest_path = source_dir / "reviewed_identities.json"
    if not manifest_path.is_file():
        return []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"reviewed_identities.json is not valid JSON: {exc}") from exc

    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ManifestValidationError("reviewed_identities.json: 'entries' must be a list")

    seen_names: set[str] = set()
    alias_owner: dict[str, str] = {}
    identities: list[ReviewedIdentity] = []

    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ManifestValidationError(
                f"reviewed_identities.json entry {index}: must be an object"
            )

        name = raw.get("canonical_name")
        if not isinstance(name, str) or not name.strip():
            raise ManifestValidationError(
                f"reviewed_identities.json entry {index}: canonical_name is required"
            )
        if anonymous_labels.is_non_person_label(name):
            raise ManifestValidationError(
                f"reviewed_identities.json entry {index}: canonical_name {name!r} is a "
                "reserved anonymous/redaction label and can never be a real person"
            )
        if name in seen_names:
            raise ManifestValidationError(
                f"reviewed_identities.json: duplicate canonical_name {name!r}"
            )
        seen_names.add(name)

        note = raw.get("review_note", "")
        if not isinstance(note, str) or not note.strip():
            raise ManifestValidationError(
                f"reviewed_identities.json entry {name!r}: review_note is required"
            )

        source_documents = raw.get("source_documents", [])
        if not isinstance(source_documents, list) or not all(
            isinstance(d, str) and d.strip() for d in source_documents
        ):
            raise ManifestValidationError(
                f"reviewed_identities.json entry {name!r}: source_documents must be a list of "
                "non-empty strings"
            )

        raw_aliases = raw.get("verified_aliases", [])
        if not isinstance(raw_aliases, list):
            raise ManifestValidationError(
                f"reviewed_identities.json entry {name!r}: verified_aliases must be a list"
            )

        aliases: list[VerifiedAlias] = []
        for alias_entry in raw_aliases:
            if not isinstance(alias_entry, dict):
                raise ManifestValidationError(
                    f"reviewed_identities.json entry {name!r}: each verified_aliases item must "
                    "be an object with alias/alias_type"
                )
            alias_value = alias_entry.get("alias")
            alias_type = alias_entry.get("alias_type")
            if not isinstance(alias_value, str) or not alias_value.strip():
                raise ManifestValidationError(
                    f"reviewed_identities.json entry {name!r}: alias value is required"
                )
            if anonymous_labels.is_non_person_label(alias_value):
                raise ManifestValidationError(
                    f"reviewed_identities.json entry {name!r}: alias {alias_value!r} is a "
                    "reserved anonymous/redaction label and can never be a reviewed alias"
                )
            if alias_type not in _MANIFEST_ALIAS_TYPES:
                raise ManifestValidationError(
                    f"reviewed_identities.json entry {name!r}: unsupported alias_type "
                    f"{alias_type!r} for alias {alias_value!r} (must be one of "
                    f"{sorted(_MANIFEST_ALIAS_TYPES)})"
                )
            existing_owner = alias_owner.get(alias_value)
            if existing_owner is not None and existing_owner != name:
                raise ManifestValidationError(
                    f"reviewed_identities.json: alias {alias_value!r} is claimed by both "
                    f"{existing_owner!r} and {name!r}"
                )
            alias_owner[alias_value] = name
            aliases.append(
                VerifiedAlias(
                    alias=alias_value,
                    alias_type=alias_type,
                    source_reference=alias_entry.get("source_reference", ""),
                )
            )

        identities.append(
            ReviewedIdentity(
                canonical_name=name,
                verified_aliases=aliases,
                review_note=note,
                source_documents=source_documents,
            )
        )

    return identities


def seed_and_discover(
    conn: sqlite3.Connection, documents: list[ParsedDocument], source_dir: Path
) -> PeopleReport:
    """Structural names are resolved against the persistent people table
    (Architecture v1.6, CLAUDE.md 18.0), not recreated from scratch: a name
    that already matches an existing FULL_NAME alias reuses that subject_id,
    and a name that already *is* someone's display_alias -- the trace a
    pseudonymisation rewrite leaves behind, e.g. "Participant Q7M4-N8" in a
    speaker position -- is recognized as that existing subject and is never
    treated as a new person or given a new FULL_NAME alias of itself. Only a
    name matching neither mints a new subject_id/display_alias."""
    structural_names: set[str] = set()
    email_by_name: dict[str, str] = {}

    for doc in documents:
        for attendee in doc.attendees:
            if not anonymous_labels.is_non_person_label(attendee):
                structural_names.add(attendee)
        for unit in doc.units:
            if unit.speaker_sender and not anonymous_labels.is_non_person_label(
                unit.speaker_sender
            ):
                structural_names.add(unit.speaker_sender)
                if unit.speaker_email:
                    email_by_name.setdefault(unit.speaker_sender, unit.speaker_email)

    # "Ana" as a speaker/sender is the participant "Ana Duarte" when exactly one
    # full name starts with it: fold it in *before* minting subjects, so one
    # person never becomes two subjects (and two aliases) for want of a surname.
    folded = name_resolution.fold_single_word_names(structural_names)
    for bare, full in folded.items():
        structural_names.discard(bare)
        if bare in email_by_name:
            email_by_name.setdefault(full, email_by_name[bare])

    reviewed = load_reviewed_identities(source_dir)
    reviewed_names = {entry.canonical_name for entry in reviewed}

    # Free-text candidates are collected for the report only. Matching a
    # reviewed name is noted as "reviewed", not "confirmed via free text":
    # the manifest, not the regex, is what actually authorized the person.
    # A known display_alias is excluded here too: it is somebody's existing
    # identity, not a free-text candidate for a new one.
    candidate_names: set[str] = set()
    for doc in documents:
        for unit in doc.units:
            cleaned_text = strip_image_placeholders(unit.raw_text)
            for match in _FULL_NAME.findall(cleaned_text):
                if match in _NAME_STOPLIST or match in structural_names:
                    continue
                if anonymous_labels.is_non_person_label(match):
                    continue
                if not _looks_like_a_name(match):
                    continue
                if repository.is_known_display_alias(conn, match):
                    continue
                candidate_names.add(match)

    report = PeopleReport(
        reviewed_text_only=sorted(reviewed_names - structural_names),
        rejected_candidates=sorted(candidate_names - reviewed_names),
    )

    for name in sorted(structural_names):
        if repository.is_known_display_alias(conn, name):
            # This *is* an existing subject's own alias (most likely the
            # rewritten trace of a pseudonymised speaker/sender); resolving
            # it to that subject happens later via evidence_people linking
            # (app/ingestion/service.py), never here -- adding it as a new
            # FULL_NAME alias of itself would pollute person_aliases with a
            # duplicate of the very alias that is supposed to be their only
            # public identifier.
            continue
        subject_id = repository.get_or_create_subject(conn, name)
        repository.add_alias(conn, subject_id, name, AliasType.FULL_NAME.value)
        email = email_by_name.get(name)
        if email:
            repository.add_alias(conn, subject_id, email, AliasType.EMAIL.value)

    for entry in reviewed:
        if repository.is_known_display_alias(conn, entry.canonical_name):
            continue
        subject_id = repository.get_or_create_subject(conn, entry.canonical_name)
        repository.add_alias(conn, subject_id, entry.canonical_name, AliasType.FULL_NAME.value)

    unresolved, reviewed_short = _apply_reviewed_short_aliases(conn, reviewed)
    report.unresolved_alias_candidates = unresolved
    report.reviewed_short_aliases = reviewed_short

    return report


def _looks_like_a_name(candidate: str) -> bool:
    words = candidate.split()
    # "That That", "He He", "Okay Okay": disfluencies and transcription
    # glitches repeat a word, which no real two-word name does.
    return len({w.lower() for w in words}) == len(words)


_SHORT_ALIAS_TYPES = tuple(
    t.value for t in AliasType if t not in (AliasType.FULL_NAME, AliasType.EMAIL)
)


def _apply_reviewed_short_aliases(
    conn: sqlite3.Connection, reviewed: list[ReviewedIdentity]
) -> tuple[list[str], list[str]]:
    """Promotes only the short-form aliases (first/last/initials/nickname/
    variant) that a human explicitly reviewed and listed in the manifest.
    Corpus-derived candidates that are unique, or even independently
    observed in the corpus text, are *not* promoted on that basis alone --
    uniqueness and independent usage are signals a reviewer can use to
    decide whether to add a manifest entry, not proof of identity by
    themselves. Everything not covered by a reviewed entry is reported as
    unresolved.

    person_aliases is persistent under Architecture v1.6 (CLAUDE.md 18.0),
    not dropped and rebuilt every ingest, so simply INSERTing from the
    current manifest is not enough on its own: a short-form alias a
    reviewer later removes from the manifest would otherwise never be
    un-promoted. These alias *types* are added exclusively through this
    function (structural discovery only ever adds FULL_NAME/EMAIL), so
    every row of these types is safe to fully recompute from the current
    manifest each run -- unlike subject_id/display_alias, nothing requires
    a short-form alias row itself to survive a rebuild unchanged."""
    placeholders = ",".join("?" * len(_SHORT_ALIAS_TYPES))
    conn.execute(
        f"DELETE FROM person_aliases WHERE alias_type IN ({placeholders})", _SHORT_ALIAS_TYPES
    )

    people_rows = repository.all_people(conn)
    full_name_by_subject = {
        row["subject_id"]: row["display_name"] for row in people_rows if row["display_name"]
    }
    subject_id_by_name = {name: subject_id for subject_id, name in full_name_by_subject.items()}

    promoted_aliases: set[str] = set()
    reviewed_short: list[str] = []
    for entry in reviewed:
        subject_id = subject_id_by_name.get(entry.canonical_name)
        if subject_id is None:
            # seed_and_discover always creates a person for every manifest
            # entry before this runs, unless the entry's canonical_name is
            # itself a known display_alias (already someone's identity, not
            # a name to promote); otherwise unreachable outside of a direct
            # unit-test calling this helper in isolation.
            continue
        for verified in entry.verified_aliases:
            repository.add_alias(conn, subject_id, verified.alias, verified.alias_type)
            promoted_aliases.add(verified.alias)
            if verified.alias_type != AliasType.EMAIL.value:
                reviewed_short.append(
                    f"{entry.canonical_name}: {verified.alias} ({verified.alias_type})"
                )

    candidates: set[str] = set()
    for display_name in full_name_by_subject.values():
        parts = display_name.split()
        if len(parts) < 2:
            continue
        candidates.add(parts[0])
        candidates.add(parts[-1])
        candidates.add("".join(p[0] for p in parts).upper())

    unresolved = {candidate for candidate in candidates if candidate not in promoted_aliases}

    return sorted(unresolved), sorted(reviewed_short)


def _observed_independently(candidate: str, full_name: str, all_text: str) -> bool:
    """True if `candidate` appears somewhere in the corpus as a standalone
    occurrence that is not part of an occurrence of `full_name` -- i.e. not
    merely derivable from the confirmed person's own name.

    This is diagnostic only: it is not used to gate alias promotion (see
    `_apply_reviewed_short_aliases`), because independent usage is not, by
    itself, confident proof that the token refers to that person. It
    exists so a reviewer deciding whether to add a manifest entry can ask
    "does this token even occur on its own anywhere?" -- and it is
    unit-tested directly because an earlier version of it was wrong in a
    way manual review alone did not catch: it looked at a
    len(full_name)-sized window ending exactly at the candidate's own
    match, which finds `full_name` when candidate is the *last* word (the
    rest of the name is behind it) but misses it entirely when candidate
    is the *first* word (the rest of the name is ahead of it, outside the
    window). Fixed by checking containment within actual occurrences of
    the full name instead of an approximate window.
    """
    full_name_spans = [(m.start(), m.end()) for m in re.finditer(re.escape(full_name), all_text)]
    pattern = re.compile(r"\b" + re.escape(candidate) + r"\b")
    for match in pattern.finditer(all_text):
        if any(start <= match.start() and match.end() <= end for start, end in full_name_spans):
            continue
        return True
    return False


def _unique_short_name_owners(
    people_rows: list[sqlite3.Row], include_first: bool = True
) -> dict[str, str]:
    """First/last/initials derived from each confirmed person's display
    name, keeping a token only when it resolves to exactly one person.

    This is deliberately separate from person_aliases: MENTIONED-detection
    recall and identity-alias promotion are different concerns with
    different risk profiles. CLAUDE.md requires that "a confirmed person
    explicitly named inside their text may still receive a MENTIONED
    relationship" -- in practice that is very often just a first name
    ("Kwame told me...") -- but person_aliases specifically drives future
    pseudonymisation target resolution (CLAUDE.md 18.1's identifier-scope
    spirit), so only a human-reviewed manifest entry may add a short form
    there. A token is still never guessed here when it is ambiguous between
    two confirmed people (e.g. "Nadia"), matching the same caution applied
    to alias promotion. A person with no display_name (PSEUDONYMISED) has
    nothing to derive a short form from and is skipped.

    `include_first=False` leaves first names out of the result (they are counted
    for collisions all the same): the caller supplies them from the strict
    first-name index instead."""
    owners: dict[str, set[str]] = {}
    for row in people_rows:
        if not row["display_name"]:
            continue
        parts = row["display_name"].split()
        if len(parts) < 2:
            continue
        for token in (parts[0], parts[-1], "".join(p[0] for p in parts).upper()):
            owners.setdefault(token, set()).add(row["subject_id"])
    first_words = (
        set()
        if include_first
        else {
            r["display_name"].split()[0]
            for r in people_rows
            if r["display_name"] and len(r["display_name"].split()) >= 2
        }
    )
    return {
        token: next(iter(ids))
        for token, ids in owners.items()
        if len(ids) == 1 and token not in first_words
    }


def link_mentions(
    conn: sqlite3.Connection,
    evidence_id: str,
    raw_text: str,
    exclude: set[str],
    index: "name_resolution.NameIndex | None" = None,
) -> int:
    """Tag every known subject whose alias appears in raw_text as MENTIONED,
    except those already linked with a stronger relation (AUTHOR/SPEAKER) on
    this same unit. Matches both person_aliases rows (an ACTIVE person's
    name/email/reviewed short forms) and every subject's own display_alias:
    the latter is what re-establishes a MENTIONED link to a PSEUDONYMISED
    subject after their source text was rewritten to say their alias
    instead of their name -- without it, a rebuild after pseudonymisation
    would silently lose every MENTIONED-only relationship. Also recognizes
    an unambiguous plain first-name/last-name/initials reference to a
    confirmed ACTIVE person even when that short form was never promoted to
    person_aliases (see _unique_short_name_owners)."""
    linked = 0
    seen_people: set[str] = set()

    candidates: list[tuple[str, str]] = [
        (row["subject_id"], row["alias"]) for row in repository.all_aliases(conn)
    ]
    candidates.extend(
        (row["subject_id"], row["display_alias"]) for row in repository.all_people(conn)
    )

    for subject_id, alias in candidates:
        if subject_id in exclude or subject_id in seen_people:
            continue
        if re.search(r"\b" + re.escape(alias) + r"\b", raw_text):
            repository.link_evidence_person(conn, evidence_id, subject_id, PersonRelation.MENTIONED)
            seen_people.add(subject_id)
            linked += 1

    people_rows = repository.all_people(conn)
    if index is None:
        short_names = _unique_short_name_owners(people_rows)
    else:
        # The strict first-name basis (app/ingestion/name_resolution.py) replaces the
        # loose "unique first word" rule, so linking and pseudonymisation agree on
        # exactly which bare first names belong to whom. Last names and initials keep
        # their existing unique-owner rule.
        short_names = _unique_short_name_owners(people_rows, include_first=False)
        for subject_id in index.first_name_tokens().values():
            token = index.first_name_of(subject_id)
            if token:
                short_names[token] = subject_id
    for token, subject_id in short_names.items():
        if subject_id in exclude or subject_id in seen_people:
            continue
        if re.search(r"\b" + re.escape(token) + r"\b", raw_text):
            repository.link_evidence_person(conn, evidence_id, subject_id, PersonRelation.MENTIONED)
            seen_people.add(subject_id)
            linked += 1

    return linked
