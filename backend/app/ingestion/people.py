"""People and alias discovery.

Structural sources (transcript Attendees/speaker labels, email/report
sender headers) are high confidence and seed `people` plus an EMAIL/
FULL_NAME alias directly. A full-name-mention scan over all raw text
additionally picks up people who are only ever mentioned, never a
speaker or sender (e.g. a departed employee referenced once) -- still
recorded as a person, but with no assumed role.

A separate short-alias pass then proposes first-name/last-name/initials
aliases, and only ever commits one when it maps to exactly one person
corpus-wide; anything that maps to more than one is left unresolved
rather than guessed (CLAUDE.md 8: "leave ambiguous aliases unmerged").
This matters concretely here: the corpus contains both a Nadia Haddad
and a Nadia Öberg, so a bare "Nadia" must never resolve to either.
"""

import re
import sqlite3
from dataclasses import dataclass, field

from app.core.enums import AliasType, PersonRelation
from app.db import repository
from app.ingestion.models import ParsedDocument
from app.ingestion.text_utils import strip_image_placeholders

# [ \t]+ rather than \s+ deliberately: a full name never legitimately
# spans a line break, but an email signature block ("Nadia Haddad\nSolution
# Consultant") would otherwise be matched as one bogus three-word "name".
_FULL_NAME = re.compile(r"\b[A-ZÅÄÖØÆÉ][a-zåäöøæé'-]+(?:[ \t]+[A-ZÅÄÖØÆÉ][a-zåäöøæé'-]+){1,2}\b")

_ANONYMOUS_SPEAKER_LABELS = ("Me", "Them", "Unknown Speaker")

# Capitalized bigrams/trigrams that match the full-name shape but are
# roles or recurring phrases, not people -- drawn from this corpus's own
# job titles, status-report jargon, and email-signature boilerplate by
# running this scan against the real archive and reading the output, not
# guessed in the abstract.
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


def _looks_like_a_name(candidate: str) -> bool:
    words = candidate.split()
    # "That That", "He He", "Okay Okay": disfluencies and transcription
    # glitches repeat a word, which no real two-word name does.
    return len({w.lower() for w in words}) == len(words)


@dataclass
class PeopleReport:
    people_count: int = 0
    alias_count: int = 0
    unresolved_candidates: list[str] = field(default_factory=list)
    text_only_mentions: list[str] = field(default_factory=list)


def seed_and_discover(conn: sqlite3.Connection, documents: list[ParsedDocument]) -> PeopleReport:
    structural_names: set[str] = set()
    email_by_name: dict[str, str] = {}

    for doc in documents:
        for attendee in doc.attendees:
            if attendee not in _ANONYMOUS_SPEAKER_LABELS:
                structural_names.add(attendee)
        for unit in doc.units:
            if unit.speaker_sender and unit.speaker_sender not in _ANONYMOUS_SPEAKER_LABELS:
                structural_names.add(unit.speaker_sender)
                if unit.speaker_email:
                    email_by_name.setdefault(unit.speaker_sender, unit.speaker_email)

    mentioned_names: set[str] = set()
    for doc in documents:
        for unit in doc.units:
            cleaned_text = strip_image_placeholders(unit.raw_text)
            for match in _FULL_NAME.findall(cleaned_text):
                if (
                    match not in _NAME_STOPLIST
                    and match not in structural_names
                    and _looks_like_a_name(match)
                ):
                    mentioned_names.add(match)

    report = PeopleReport(text_only_mentions=sorted(mentioned_names))

    for name in sorted(structural_names | mentioned_names):
        person_id = repository.get_or_create_person(conn, name)
        repository.add_alias(conn, person_id, name, AliasType.FULL_NAME.value)
        report.people_count += 1
        report.alias_count += 1
        email = email_by_name.get(name)
        if email:
            repository.add_alias(conn, person_id, email, AliasType.EMAIL.value)
            report.alias_count += 1

    added, unresolved = _discover_short_aliases(conn)
    report.alias_count += added
    report.unresolved_candidates = unresolved

    return report


def _discover_short_aliases(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    people_rows = repository.all_people(conn)

    buckets: dict[AliasType, dict[str, set[str]]] = {
        AliasType.FIRST_NAME: {},
        AliasType.LAST_NAME: {},
        AliasType.INITIALS: {},
    }
    for row in people_rows:
        parts = row["canonical_name"].split()
        if len(parts) < 2:
            continue
        buckets[AliasType.FIRST_NAME].setdefault(parts[0], set()).add(row["person_id"])
        buckets[AliasType.LAST_NAME].setdefault(parts[-1], set()).add(row["person_id"])
        initials = "".join(p[0] for p in parts).upper()
        buckets[AliasType.INITIALS].setdefault(initials, set()).add(row["person_id"])

    added = 0
    unresolved: set[str] = set()
    for alias_type, mapping in buckets.items():
        for candidate, owners in mapping.items():
            if len(owners) == 1:
                (person_id,) = owners
                repository.add_alias(conn, person_id, candidate, alias_type.value)
                added += 1
            else:
                unresolved.add(candidate)
    return added, sorted(unresolved)


def link_mentions(
    conn: sqlite3.Connection, evidence_id: str, raw_text: str, exclude: set[str]
) -> int:
    """Tag every known person whose alias appears in raw_text as
    MENTIONED, except those already linked with a stronger relation
    (AUTHOR/SPEAKER) on this same unit."""
    linked = 0
    seen_people: set[str] = set()
    for row in repository.all_aliases(conn):
        person_id, alias = row["person_id"], row["alias"]
        if person_id in exclude or person_id in seen_people:
            continue
        if re.search(r"\b" + re.escape(alias) + r"\b", raw_text):
            repository.link_evidence_person(conn, evidence_id, person_id, PersonRelation.MENTIONED)
            seen_people.add(person_id)
            linked += 1
    return linked
