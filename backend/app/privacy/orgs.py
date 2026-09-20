"""Which organisation a redacted person belonged to (CLAUDE.md 2.4, 18.6).

Anonymising a participant should not erase *who they spoke for*: a suggestion
from the vendor is not the customer's agreement, so "[REDACTED SPEAKER: RELEX]"
keeps the answer to a nearby question correct while the person stays unnamed.
Only the organisation is kept -- never a name, job title or role, which are
what would make a small group identifiable.

Everything is derived from the archive itself, with no hardcoded company
names: an organisation is a single word that appears in an Attendees
parenthetical ("Name (RELEX)"); an email domain maps to an organisation by the
attendees who use it.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.service import enumerate_source_files
from app.ingestion.text_utils import split_top_level
from app.privacy.targets import Target, fold, name_pattern

_ATTENDEES = re.compile(r"^\s*Attendees\s*:(?P<value>.*)$", re.IGNORECASE | re.MULTILINE)
_PAREN = re.compile(r"\(([^)]*)\)")
_ADDRESS = re.compile(r"(?P<name>[^<>;,\n]+?)\s*<(?P<addr>[^<>@\s]+@(?P<domain>[^<>\s]+))>")


@dataclass
class OrgContext:
    vocabulary: frozenset[str] = frozenset()
    domain_org: dict[str, str] = field(default_factory=dict)
    default: str | None = None

    def from_parenthetical(self, entry: str) -> str | None:
        """'Robert Kahn (Acme CFO)' -> 'Acme'; only a known organisation word counts."""
        match = _PAREN.search(entry)
        if not match:
            return None
        for word in re.findall(r"[\w.&-]+", match.group(1)):
            if word in self.vocabulary:
                return word
        return None

    def from_address(self, text: str) -> str | None:
        match = re.search(r"@([\w.-]+)", text)
        return self.domain_org.get(match.group(1).lower()) if match else None


def build(source_dir: Path, target: Target) -> OrgContext:
    files = [
        (path.read_text(encoding="utf-8"), kind)
        for path, kind in enumerate_source_files(source_dir)
    ]

    # An organisation is a single word used on its own as an attendee affiliation.
    single = Counter()
    for text, _ in files:
        for header in _ATTENDEES.finditer(text):
            for entry in split_top_level(header.group("value"), ","):
                match = _PAREN.search(entry)
                if match and re.fullmatch(r"[\w.&-]+", match.group(1).strip()):
                    single[match.group(1).strip()] += 1
    ctx = OrgContext(vocabulary=frozenset(single))

    person_orgs: dict[str, Counter] = {}
    for text, _ in files:
        for header in _ATTENDEES.finditer(text):
            for entry in split_top_level(header.group("value"), ","):
                org = ctx.from_parenthetical(entry)
                if org:
                    name = re.sub(r"\s*\([^)]*\)\s*", " ", entry).strip()
                    person_orgs.setdefault(fold(name), Counter())[org] += 1

    votes: dict[str, Counter] = {}
    for text, _ in files:
        for match in _ADDRESS.finditer(text):
            orgs = person_orgs.get(fold(match.group("name").strip()))
            if orgs:
                votes.setdefault(match.group("domain").lower(), Counter())[
                    orgs.most_common(1)[0][0]
                ] += 1
    ctx.domain_org = {d: c.most_common(1)[0][0] for d, c in votes.items()}

    own = Counter()
    for name in target.names:
        own.update(person_orgs.get(fold(name), Counter()))
    if own:
        ctx.default = own.most_common(1)[0][0]
    else:
        for email in target.emails:
            org = ctx.from_address(email)
            if org:
                ctx.default = org
                break
    return ctx


def doc_org(text: str, target: Target, ctx: OrgContext) -> str | None:
    """The organisation the target represented in *this* document (people
    change jobs), falling back to their usual one."""
    patterns = [name_pattern(n) for n in target.names]
    for header in _ATTENDEES.finditer(text):
        for entry in split_top_level(header.group("value"), ","):
            if any(p.search(entry) for p in patterns):
                org = ctx.from_parenthetical(entry)
                if org:
                    return org
    return ctx.default
