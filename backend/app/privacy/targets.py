"""Resolve a deletion target (CLAUDE.md 18.1).

The target is exactly what the hardened identity layer already tracks: the
canonical name, its reviewed aliases (including any human-reviewed
short-form alias), and email addresses. Nothing fuzzy is added here -- a
first name that has not been reviewed into the manifest is deliberately
*not* redacted, because it may belong to someone else.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

# The archive itself spells the same person both ways ("Henrik Sørensen" in an
# Attendees header, "Henrik Sorensen" in that speaker's own captions), so a
# purge that matches only one spelling leaves the other behind -- and a
# redaction that lands on half of a document's spellings corrupts its structure.
_FOLD_EXTRA = str.maketrans({"ø": "o", "Ø": "O", "ß": "s", "đ": "d", "ł": "l"})


def fold(text: str) -> str:
    """Lower-cased, diacritic-free form used to compare names and to scan."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_FOLD_EXTRA))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


_VARIANTS = {
    "a": "aàáâãäåā",
    "c": "cçč",
    "e": "eèéêëē",
    "i": "iìíîï",
    "n": "nñ",
    "o": "oòóôõöøō",
    "s": "sšß",
    "u": "uùúûüū",
    "y": "yýÿ",
    "z": "zž",
}


@dataclass(frozen=True)
class Target:
    person_id: str
    canonical_name: str
    names: tuple[str, ...]  # canonical name + every non-email alias
    emails: tuple[str, ...]

    @property
    def identifiers(self) -> tuple[str, ...]:
        return (*self.names, *self.emails)

    @property
    def initials(self) -> str:
        return "".join(w[0] for w in self.canonical_name.split() if w).upper()


@dataclass
class PersonSummary:
    person_id: str
    canonical_name: str
    author_units: int = 0
    speaker_units: int = 0
    mentioned_units: int = 0
    cases: int = 0
    extras: dict = field(default_factory=dict)


def resolve_target(conn: sqlite3.Connection, person_id: str) -> Target | None:
    person = conn.execute(
        "SELECT person_id, canonical_name FROM people WHERE person_id = ?", (person_id,)
    ).fetchone()
    if person is None:
        return None
    aliases = conn.execute(
        "SELECT alias, alias_type FROM person_aliases WHERE person_id = ?", (person_id,)
    ).fetchall()
    names = [person["canonical_name"]]
    emails = []
    for row in aliases:
        (emails if row["alias_type"] == "EMAIL" else names).append(row["alias"])
    # Longest first so a full name is replaced before any shorter alias inside it.
    return Target(
        person_id=person["person_id"],
        canonical_name=person["canonical_name"],
        names=tuple(sorted(dict.fromkeys(names), key=len, reverse=True)),
        emails=tuple(dict.fromkeys(emails)),
    )


def name_pattern(name: str) -> re.Pattern[str]:
    """Case-insensitive, whole-token match (Unicode-aware, so 'Kwame' never
    matches inside 'Kwameh'), tolerant of any run of whitespace between
    the words of a multi-word name."""
    parts = ["".join(_char_class(ch) for ch in word) for word in name.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _char_class(ch: str) -> str:
    base = fold(ch)
    variants = _VARIANTS.get(base)
    return f"[{variants}]" if variants else re.escape(ch)


def list_people(conn: sqlite3.Connection) -> list[PersonSummary]:
    rows = conn.execute("SELECT person_id, canonical_name FROM people ORDER BY canonical_name")
    people = {r["person_id"]: PersonSummary(r["person_id"], r["canonical_name"]) for r in rows}
    for row in conn.execute(
        "SELECT person_id, relation, COUNT(DISTINCT evidence_id) AS n FROM evidence_people "
        "GROUP BY person_id, relation"
    ):
        person = people.get(row["person_id"])
        if person is None:
            continue
        field_name = {
            "AUTHOR": "author_units",
            "SPEAKER": "speaker_units",
            "MENTIONED": "mentioned_units",
        }[row["relation"]]
        setattr(person, field_name, row["n"])
    return list(people.values())
