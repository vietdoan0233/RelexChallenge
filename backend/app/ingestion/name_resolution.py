"""Strict name -> subject assignment on three bases: full name, first name,
and last name.

"Ana Duarte" and "Ana" are the same participant, and a pseudonymisation that
rewrites one but leaves the other behind leaks the very identity it is meant
to hide. The same is true of "Kwame Boateng" and a bare "Boateng" mentioned
by a colleague in someone else's turn/email/report -- a mention never
authored or spoken by the subject themselves. This module is the single
place that decides which subject a name form belongs to, so identity linking
(ingestion, app/ingestion/people.py's link_mentions) and the pseudonymisation
target (app/privacy/targets.py) can never disagree about which short forms
safely identify one person. Before this module covered last names too, the
two call sites *did* disagree: link_mentions used a separate, looser,
case-sensitive "unique last word" check to auto-link a MENTIONED relation to
a bare last name, but the pseudonymisation target never saw that same form
-- so the relationship was recorded while the identifying text itself was
silently left unrewritten. Last name now goes through the identical strict
basis as first name, closing that gap at its source instead of patching
around it.

Full name: an exact, case- and whitespace-insensitive match on a subject's
display name or a FULL_NAME alias.

First name and last name: each assigned to a subject only when every one of
these holds for that token; anything else is left *unassigned* (first name
only reports its reason -- see unassigned_first_name), never guessed:

  * the subject has a multi-word display name and the token is its first
    (respectively last) word,
  * the token is at least three letters,
  * no other active subject has that token as ANY part of their name (so
    "Nadia" is never assigned while both Nadia Haddad and Nadia Oberg exist,
    and a last name that is also someone else's first/last name/middle name
    is never assigned to either),
  * it is not an ordinary word (a small stoplist of given names that are
    everyday words, plus "the archive mostly uses it in lower case"),
  * it is not a reserved anonymous label or a pseudonym alias token.

Initials (e.g. "KB" for "Kwame Boateng") are deliberately NOT given this
treatment: a two/three-letter token has a much higher chance of colliding
with an ordinary word or abbreviation used elsewhere in the archive (e.g.
"OK", "IT", "PM"), and rewriting one case-insensitively would risk damaging
unrelated text purely because it happens to be corpus-unique as an acronym.
Initials remain reviewable via an explicit manifest INITIALS alias (always
authoritative, like any reviewed alias) and keep the existing looser,
unreviewed unique-owner check for MENTIONED-relationship recall only
(app/ingestion/people.py's _unique_short_name_owners) -- that check was
never wired into the pseudonymisation target and stays that way on purpose.

A first/last name a human reviewed into the identity manifest (a FIRST_NAME
or LAST_NAME row in person_aliases) is authoritative and bypasses these
heuristics: the manifest is the reviewed source of truth, the rules above are
the fallback when nobody reviewed it.

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
LAST_NAME = "LAST_NAME"

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
    _last: dict[str, str] = field(default_factory=dict)  # folded token -> subject_id
    _last_display: dict[str, str] = field(default_factory=dict)  # subject_id -> token as written
    # subject_id -> why (first name only; last name has no reason reporting)
    _unassigned: dict[str, Unassigned] = field(default_factory=dict)

    def resolve(self, name: str) -> Assignment | None:
        """The subject a name form belongs to, or None. Full name first, then
        the strict first-name basis; never fuzzy. (Last name is not resolved
        here: this method backs structural speaker/sender assignment, e.g. a
        bare "Ana" byline -- a byline is realistically a first name, never a
        bare surname, so last name is only ever consulted for mention
        detection and rewriting, via last_name_of/last_name_tokens below.)"""
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

    def last_name_of(self, subject_id: str) -> str | None:
        """The bare last name that safely stands for this subject, if any --
        the identical strict, corpus-unique basis as first_name_of, applied
        to a multi-word display name's last word instead of its first."""
        return self._last_display.get(subject_id)

    def unassigned_first_name(self, subject_id: str) -> Unassigned | None:
        return self._unassigned.get(subject_id)

    def first_name_tokens(self) -> dict[str, str]:
        """folded first-name token -> subject_id, for every assigned first name."""
        return dict(self._first)

    def last_name_tokens(self) -> dict[str, str]:
        """folded last-name token -> subject_id, for every assigned last name."""
        return dict(self._last)


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

    # ---- reviewed first/last names are authoritative
    for row in aliases:
        if row["subject_id"] not in names_by_subject:
            continue
        if row["alias_type"] == FIRST_NAME:
            index._first[_fold(row["alias"])] = row["subject_id"]
            index._first_display[row["subject_id"]] = row["alias"]
        elif row["alias_type"] == LAST_NAME:
            index._last[_fold(row["alias"])] = row["subject_id"]
            index._last_display[row["subject_id"]] = row["alias"]

    # ---- strict fallback for everything nobody reviewed. First and last
    # name share one safety bar (_short_name_reason) so a colleague's bare
    # "Boateng" is judged exactly as strictly as a bare "Kwame" -- see the
    # module docstring for why the two used to disagree.
    reserved_tokens = {
        _fold(part) for row in people for part in (row["display_alias"] or "").split()
    }
    text_box = [corpus]  # lazily loaded at most once, shared by both passes
    for row in people:
        subject_id = row["subject_id"]
        parts = row["display_name"].split()
        if len(parts) < 2:
            continue

        if subject_id not in index._first_display:
            token = parts[0]
            reason = _short_name_reason(
                token, subject_id, part_owners, reserved_tokens, index, conn, text_box
            )
            if reason is None:
                index._first[_fold(token)] = subject_id
                index._first_display[subject_id] = token
            else:
                index._unassigned[subject_id] = Unassigned(token, reason)

        if subject_id not in index._last_display:
            token = parts[-1]
            reason = _short_name_reason(
                token, subject_id, part_owners, reserved_tokens, index, conn, text_box
            )
            if reason is None:
                index._last[_fold(token)] = subject_id
                index._last_display[subject_id] = token
            # Last-name ambiguity is not reported anywhere today (unlike
            # first name's unassigned_first_name/preview reason), so an
            # unsafe last name is simply left out of the index rather than
            # recorded -- there is exactly one `_unassigned` slot per
            # subject and it is reserved for the first-name reason.

    return index


def _short_name_reason(
    token: str,
    subject_id: str,
    part_owners: dict[str, set[str]],
    reserved_tokens: set[str],
    index: NameIndex,
    conn: sqlite3.Connection,
    text_box: list[str | None],
) -> str | None:
    """None if `token` (a candidate first or last name) safely identifies
    `subject_id` alone; otherwise the reason it doesn't (too-short | reserved
    | shared | ordinary-word) -- the one strict basis both name_resolution's
    first-name and last-name passes apply, so they can never disagree with
    each other or with link_mentions/targets, which both read the result
    back out through first_name_of/last_name_of rather than recomputing it.
    `text_box` is a 1-element mutable box holding the lazily-loaded corpus
    text, shared across every call so it is read from the database at most
    once per build_index()."""
    key = _fold(token)
    if not _is_plain_name_token(token) or len(token) < MIN_FIRST_NAME_LENGTH:
        return "too-short"
    if anonymous_labels.is_non_person_label(token) or key in reserved_tokens:
        return "reserved"
    if part_owners.get(key, set()) != {subject_id} or key in index._first or key in index._last:
        return "shared"
    if key in _COMMON_WORD_NAMES:
        return "ordinary-word"
    if text_box[0] is None:
        text_box[0] = "\n".join(r[0] for r in conn.execute("SELECT raw_text FROM evidence_units"))
    if _lowercase_dominates(token, text_box[0]):
        return "ordinary-word"
    return None


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
