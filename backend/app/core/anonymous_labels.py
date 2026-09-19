"""Speaker/sender labels that must never become a real identity.

Two categories share one exclusion set because both must be treated
identically everywhere a name is considered for identity discovery,
relation linking, mention detection, or manifest validation:

- structural anonymous labels the corpus itself already produces (`Me`,
  `Them`, `Unknown Speaker` -- CLAUDE.md's anonymous-INTERNAL-transcript
  and Teams-UI-chrome rules),
- reserved redaction markers a future deletion/anonymization operation
  writes into sanitized canonical source (CLAUDE.md 18.7): irreversible,
  generic placeholders with no mapping back to the person they replaced.

This is the single shared source for that exclusion set. Before this
module existed, the anonymous labels were hardcoded separately in the
transcript parser, people.py, and service.py; a reserved marker added to
only one of those copies (or to none) would let a sanitized
speaker_sender value quietly become a brand new fake person on the next
ingest -- exactly the failure mode Phase 1's identity hardening exists
to prevent, just triggered by redacted text instead of a stray
capitalized phrase.

Teams also captions unidentified external participants as "Guest 1",
"Guest 2", ... Those are numbered on the fly, so they are matched by
pattern (`is_guest_label`) instead of being listed. Like `Me`/`Them` they
are kept verbatim as the speaker label and never resolved to a roster
person: a guest who happens to be interleaved with a named attendee is
not thereby that attendee.
"""

import re

ANONYMOUS_SPEAKER_LABEL_ME = "Me"
ANONYMOUS_SPEAKER_LABEL_THEM = "Them"
ANONYMOUS_SPEAKER_LABEL_UNKNOWN = "Unknown Speaker"
ANONYMOUS_SPEAKER_LABELS = frozenset(
    {ANONYMOUS_SPEAKER_LABEL_ME, ANONYMOUS_SPEAKER_LABEL_THEM, ANONYMOUS_SPEAKER_LABEL_UNKNOWN}
)

# CLAUDE.md 18.7: role-aware, irreversible, generic. Never written to
# people.canonical_name or person_aliases.alias.
REDACTED_PERSON = "[REDACTED PERSON]"
REDACTED_SPEAKER = "[REDACTED SPEAKER]"
REDACTED_SENDER = "[REDACTED SENDER]"
REDACTION_MARKERS = frozenset({REDACTED_PERSON, REDACTED_SPEAKER, REDACTED_SENDER})

NON_PERSON_LABELS = ANONYMOUS_SPEAKER_LABELS | REDACTION_MARKERS


_GUEST_LABEL = re.compile(r"Guest \d+")


def is_guest_label(value: str | None) -> bool:
    """True for a Teams anonymous guest caption such as "Guest 1"."""
    return value is not None and _GUEST_LABEL.fullmatch(value.strip()) is not None


def is_non_person_label(value: str | None) -> bool:
    """True if `value` must never be treated as a person, alias, author,
    speaker, or mentioned identity. Comparison is exact-match against
    NON_PERSON_LABELS after trimming surrounding whitespace -- never a
    substring/fuzzy check -- so ordinary text that merely contains a
    word like "redacted" is never caught by this."""
    if value is None:
        return False
    return value.strip() in NON_PERSON_LABELS or is_guest_label(value)
