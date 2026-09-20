"""Strict name -> subject assignment on two bases: full name and first name.

"Ana Duarte" and "Ana" are the same participant, and a pseudonymisation that
rewrites one but leaves the other behind leaks the very identity it is meant
to hide. This module is the single place that decides which subject a name
form belongs to, so identity linking (ingestion) and the pseudonymisation
target (privacy) can never disagree.

Full name: an exact, case- and whitespace-insensitive match on a subject's
display name or a FULL_NAME alias.

First name: assigned to a subject only when every one of these holds; anything
else is left *unassigned* and reported with its reason, never guessed:

  * the subject has a multi-word display name and the token is its first word,
  * the token is at least three letters,
  * no other active subject has that token as ANY part of their name (so
    "Nadia" is never assigned while both Nadia Haddad and Nadia Oberg exist),
  * it is not an ordinary word (a small stoplist of given names that are
    everyday words, plus "the archive mostly uses it in lower case"),
  * it is not a reserved anonymous label or a pseudonym alias token.

A first name a human reviewed into the identity manifest (a FIRST_NAME row in
person_aliases) is authoritative and bypasses these heuristics: the manifest
is the reviewed source of truth, the rules above are the fallback when nobody
reviewed it.

Nothing here reads the reversal vault: only ACTIVE subjects with a public
display name take part, so a pseudonymised subject can never be resolved back
to a real name through this module.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from app.core import anonymous_labels

FULL_NAME = "FULL_NAME"
FIRST_NAME = "FIRST_NAME"

MIN_FIRST_NAME_LENGTH = 3

# Given names that are also everyday English words. A candidate-quality aid:
# the identity boundary is the uniqueness rule and the reviewed manifest.
_COMMON_WORD_NAMES = frozenset(
    {
        "will", "mark", "grace", "rose", "dawn", "hope", "faith", "summer", "april",
        "june", "august", "bill", "art", "frank", "rob", "pat", "jack", "joy", "sue",
        "ray", "rich", "earl", "chase", "victor", "guy", "case", "page", "max", "bob",
        "cash", "drew", "gene", "jay", "ken", "lee", "miles", "neil", "pearl", "ruby",
    }
)  # fmt: skip

_EMAIL = re.compile(r"\S+@\S+")


def _fold(text: str) -> str:
    """Case-, whitespace- and composition-insensitive comparison key."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _name_parts(name: str) -> list[str]:
    return [_fold(part) for part in name.split() if part]


def _is_plain_name_token(token: str) -> bool:
    # Letters (any script) with optional internal apostrophes/hyphens.
    return bool(token) and all(ch.isalpha() or ch in "'-" for ch in token) and token[0].isalpha()


@dataclass(frozen=True)
class Assignment:
    subject_id: str
    basis: str  # FULL_NAME | FIRST_NAME
    token: str


@dataclass(frozen=True)
class Unassigned:
    """A first name that exists but was deliberately not assigned."""

    token: str
    reason: str  # shared | ordinary-word | too-short | reserved


@dataclass
class NameIndex:
    _full: dict[str, str] = field(default_factory=dict)
    _first: dict[str, str] = field(default_factory=dict)  # folded token -> subject_id
    _first_display: dict[str, str] = field(default_factory=dict)  # subject_id -> token as written
    _unassigned: dict[str, Unassigned] = field(default_factory=dict)  # subject_id -> why

    def resolve(self, name: str) -> Assignment | None:
        """The subject a name form belongs to, or None. Full name first, then
        the strict first-name basis; never fuzzy."""
        key = _fold(name)
        if not key:
            return None
        subject_id = self._full.get(key)
        if subject_id is not None:
            return Assignment(subject_id, FULL_NAME, name.strip())
        subject_id = self._first.get(key)
        if subject_id is not None:
            return Assignment(subject_id, FIRST_NAME, self._first_display[subject_id])
        return None

    def first_name_of(self, subject_id: str) -> str | None:
        """The bare first name that safely stands for this subject, if any."""
        return self._first_display.get(subject_id)

    def unassigned_first_name(self, subject_id: str) -> Unassigned | None:
        return self._unassigned.get(subject_id)

    def first_name_tokens(self) -> dict[str, str]:
        """folded first-name token -> subject_id, for every assigned first name."""
        return dict(self._first)


def _lowercase_dominates(token: str, corpus: str) -> bool:
    """True when the archive uses the token mostly as an ordinary lower-case word.

    Transcripts caption real names in lower case too ("well, marco."), so a
    lower-case occurrence alone proves nothing; only when lower case outnumbers
    the capitalised form is the token treated as a word rather than a name.
    E-mail addresses are removed first: "ana.duarte@..." is not a lower-case use."""
    text = _EMAIL.sub(" ", corpus)
    capitalised = len(re.findall(r"(?<!\w)" + re.escape(token.capitalize()) + r"(?!\w)", text))
    lower = len(re.findall(r"(?<!\w)" + re.escape(token.lower()) + r"(?!\w)", text))
    return lower > capitalised


def build_index(conn: sqlite3.Connection, corpus: str | None = None) -> NameIndex:
    """Build the name index from the public people/alias rows.

    `corpus` is the archive text used for the ordinary-word check; when omitted
    it is read from evidence_units (public, already alias-bearing after a
    pseudonymisation). Only ACTIVE subjects with a display name participate."""
    people = conn.execute(
        "SELECT subject_id, display_name, display_alias FROM people "
        "WHERE privacy_state = 'ACTIVE' AND display_name IS NOT NULL"
    ).fetchall()
    aliases = conn.execute("SELECT subject_id, alias, alias_type FROM person_aliases").fetchall()

    index = NameIndex()

    names_by_subject: dict[str, set[str]] = {}
    for row in people:
        names_by_subject.setdefault(row["subject_id"], set()).add(row["display_name"])
    for row in aliases:
        if row["subject_id"] in names_by_subject and row["alias_type"] in (FULL_NAME, "VARIANT"):
            if " " in row["alias"].strip():
                names_by_subject[row["subject_id"]].add(row["alias"])

    # ---- full-name basis (kept only where the name maps to exactly one subject)
    full_owners: dict[str, set[str]] = {}
    for subject_id, names in names_by_subject.items():
        for name in names:
            full_owners.setdefault(_fold(name), set()).add(subject_id)
    index._full = {key: next(iter(ids)) for key, ids in full_owners.items() if len(ids) == 1}

    # ---- which subjects use each name part (first, middle, last) anywhere
    part_owners: dict[str, set[str]] = {}
    for subject_id, names in names_by_subject.items():
        for name in names:
            for part in _name_parts(name):
                part_owners.setdefault(part, set()).add(subject_id)

    # ---- reviewed first names are authoritative
    reviewed_first: dict[str, tuple[str, str]] = {}
    for row in aliases:
        if row["alias_type"] == FIRST_NAME and row["subject_id"] in names_by_subject:
            reviewed_first[_fold(row["alias"])] = (row["subject_id"], row["alias"])
    for key, (subject_id, written) in reviewed_first.items():
        index._first[key] = subject_id
        index._first_display[subject_id] = written

    # ---- strict fallback for everything nobody reviewed
    reserved_tokens = {
        _fold(part) for row in people for part in (row["display_alias"] or "").split()
    }
    text = corpus
    for row in people:
        subject_id = row["subject_id"]
        if subject_id in index._first_display:
            continue
        parts = row["display_name"].split()
        if len(parts) < 2:
            continue
        token = parts[0]
        key = _fold(token)

        reason: str | None = None
        if not _is_plain_name_token(token) or len(token) < MIN_FIRST_NAME_LENGTH:
            reason = "too-short"
        elif anonymous_labels.is_non_person_label(token) or key in reserved_tokens:
            reason = "reserved"
        elif part_owners.get(key, set()) != {subject_id} or key in index._first:
            reason = "shared"
        elif key in _COMMON_WORD_NAMES:
            reason = "ordinary-word"
        else:
            if text is None:
                text = "\n".join(r[0] for r in conn.execute("SELECT raw_text FROM evidence_units"))
            if _lowercase_dominates(token, text):
                reason = "ordinary-word"

        if reason is None:
            index._first[key] = subject_id
            index._first_display[subject_id] = token
        else:
            index._unassigned[subject_id] = Unassigned(token, reason)

    return index


def fold_single_word_names(structural_names: set[str]) -> dict[str, str]:
    """Map a bare structural name ("Ana", as a speaker or sender) onto the one
    multi-word structural name it is the first word of ("Ana Duarte").

    Used before any subject exists, on the names ingestion has just parsed. A bare
    name is folded only when exactly one multi-word name starts with it and no
    other multi-word name contains it anywhere -- the same uniqueness rule as
    the index, so "Nadia" (two Nadias) is never folded. A bare name that
    matches nobody stays what it is: its own name, resolved by a later run once
    its full name appears."""
    multi = [n for n in structural_names if len(n.split()) >= 2]
    folded: dict[str, str] = {}
    for name in structural_names:
        if len(name.split()) != 1:
            continue
        key = _fold(name)
        if len(name) < MIN_FIRST_NAME_LENGTH or key in _COMMON_WORD_NAMES:
            continue
        if anonymous_labels.is_non_person_label(name):
            continue
        starts = [m for m in multi if _name_parts(m)[0] == key]
        contains = [m for m in multi if key in _name_parts(m)]
        if len(starts) == 1 and len(contains) == 1:
            folded[name] = starts[0]
    return folded
