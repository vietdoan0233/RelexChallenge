"""Resolve a pseudonymisation target (AGENTS.md/CLAUDE.md 18.0.1).

The target is what the hardened identity layer tracks for an ACTIVE subject:
their display name, every person_aliases row (full-name variants, email,
reviewed short forms), and -- on the strict first-name basis -- the bare first
name when it safely stands for them alone (app/ingestion/name_resolution.py).
"Ana Duarte" and "Ana" are one participant, so both are rewritten to the alias.

A first name is still never *guessed*: when another participant shares it
("Nadia" with two Nadias), it is an everyday word, or it is too short, it is
left out of the target and reported on the Target so the operator can see what
was deliberately left unchanged and why.
"""

import re
import sqlite3
from dataclasses import dataclass

from app.ingestion import name_resolution


@dataclass(frozen=True)
class Target:
    subject_id: str
    display_name: str
    display_alias: str
    names: tuple[str, ...]  # display_name + every non-email alias + safe first name
    emails: tuple[str, ...]
    # The bare first name included in `names` on the strict first-name basis, or
    # None; and, if a first name exists but was NOT safe to assign, what and why.
    first_name: str | None = None
    unassigned_first_name: str | None = None
    unassigned_reason: str | None = None

    @property
    def identifiers(self) -> tuple[str, ...]:
        return (*self.names, *self.emails)

    @property
    def initials(self) -> str:
        return "".join(w[0] for w in self.display_name.split() if w).upper()


@dataclass
class PersonSummary:
    subject_id: str
    display_alias: str
    privacy_state: str
    display_name: str | None = None
    author_units: int = 0
    speaker_units: int = 0
    mentioned_units: int = 0


def resolve_active_target(conn: sqlite3.Connection, subject_id: str) -> Target | None:
    """None both when the subject does not exist and when they exist but
    are already PSEUDONYMISED -- pseudonymisation only ever runs against an
    ACTIVE subject, so both cases mean "nothing to target" to a caller."""
    person = conn.execute(
        "SELECT subject_id, display_name, display_alias, privacy_state FROM people "
        "WHERE subject_id = ?",
        (subject_id,),
    ).fetchone()
    if person is None or person["privacy_state"] != "ACTIVE" or not person["display_name"]:
        return None
    aliases = conn.execute(
        "SELECT alias, alias_type FROM person_aliases WHERE subject_id = ?", (subject_id,)
    ).fetchall()
    names = [person["display_name"]]
    emails: list[str] = []
    for row in aliases:
        (emails if row["alias_type"] == "EMAIL" else names).append(row["alias"])

    index = name_resolution.build_index(conn)
    first_name = index.first_name_of(subject_id)
    unassigned = index.unassigned_first_name(subject_id)
    already = {n.casefold() for n in names}
    if first_name and first_name.casefold() not in already:
        names.append(first_name)
    # Longest first so a full name is replaced before any shorter alias inside it.
    return Target(
        subject_id=subject_id,
        display_name=person["display_name"],
        display_alias=person["display_alias"],
        names=tuple(sorted(dict.fromkeys(names), key=len, reverse=True)),
        emails=tuple(dict.fromkeys(emails)),
        first_name=first_name,
        unassigned_first_name=unassigned.token if unassigned else None,
        unassigned_reason=unassigned.reason if unassigned else None,
    )


def name_pattern(name: str) -> re.Pattern[str]:
    """Case-insensitive, whole-token match (Unicode-aware, so 'Kwame' never
    matches inside 'Kwameh'), tolerant of any run of whitespace (including a
    line break) between the words of a multi-word name."""
    parts = [re.escape(p) for p in name.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def list_people(conn: sqlite3.Connection) -> list[PersonSummary]:
    rows = conn.execute(
        "SELECT subject_id, display_alias, privacy_state, display_name FROM people "
        "ORDER BY COALESCE(display_name, display_alias)"
    )
    people = {
        r["subject_id"]: PersonSummary(
            r["subject_id"], r["display_alias"], r["privacy_state"], r["display_name"]
        )
        for r in rows
    }
    for row in conn.execute(
        "SELECT subject_id, relation, COUNT(DISTINCT evidence_id) AS n FROM evidence_people "
        "GROUP BY subject_id, relation"
    ):
        person = people.get(row["subject_id"])
        if person is None:
            continue
        field_name = {
            "AUTHOR": "author_units",
            "SPEAKER": "speaker_units",
            "MENTIONED": "mentioned_units",
        }[row["relation"]]
        setattr(person, field_name, row["n"])
    return list(people.values())
