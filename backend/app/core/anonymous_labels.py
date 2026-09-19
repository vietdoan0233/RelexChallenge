"""Speaker/sender labels that must never become a real identity.

Three categories share one exclusion set because all must be treated
identically everywhere a name is considered for identity discovery,
relation linking, mention detection, or manifest validation:

- structural anonymous labels the corpus itself already produces (`Me`,
  `Them`, `Unknown Speaker` -- CLAUDE.md's anonymous-INTERNAL-transcript
  and Teams-UI-chrome rules),
- reserved redaction markers a future deletion/anonymization operation
  writes into sanitized canonical source (CLAUDE.md 18.7): irreversible,
  generic placeholders with no mapping back to the person they replaced,
- an unlisted Teams participant the export identifies only by a phone
  number (a dial-in) or a generic "Guest N" label: a real, attributable
  speaker whose turns are preserved under the literal label, but neither
  is a name and neither carries identity evidence (a "Guest 1" in one
  meeting is not the "Guest 1" of another), so they never become a
  `people` row or alias.

This is the single shared source for that exclusion set. Before this
module existed, the anonymous labels were hardcoded separately in the
transcript parser, people.py, and service.py; a reserved marker added to
only one of those copies (or to none) would let a sanitized
speaker_sender value quietly become a brand new fake person on the next
ingest -- exactly the failure mode Phase 1's identity hardening exists
to prevent, just triggered by redacted text instead of a stray
capitalized phrase.
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

# A Teams dial-in participant with no display name: "+" then digits with
# single-space groups, e.g. "+358 40 5512 097". Deliberately narrow (no
# hyphens/parentheses) -- the corpus only shows this shape, and a wider
# pattern would risk classifying ordinary text as a speaker label.
PHONE_NUMBER_LABEL_PATTERN = r"\+\d(?:[\d ]*\d)?"
_PHONE_NUMBER_LABEL = re.compile(rf"^{PHONE_NUMBER_LABEL_PATTERN}$")


# Teams' generic label for a guest with no display name.
GUEST_LABEL_PATTERN = r"Guest \d+"
_GUEST_LABEL = re.compile(rf"^{GUEST_LABEL_PATTERN}$")


def is_phone_number_label(value: str | None) -> bool:
    """True if `value` is exactly a phone-number speaker label."""
    if value is None:
        return False
    return _PHONE_NUMBER_LABEL.match(value.strip()) is not None


def is_guest_label(value: str | None) -> bool:
    """True if `value` is exactly a Teams "Guest N" speaker label."""
    if value is None:
        return False
    return _GUEST_LABEL.match(value.strip()) is not None


def is_unlisted_participant_label(value: str | None) -> bool:
    """True for any label Teams gives a participant absent from the
    Attendees header: a phone number or "Guest N"."""
    return is_phone_number_label(value) or is_guest_label(value)


def is_non_person_label(value: str | None) -> bool:
    """True if `value` must never be treated as a person, alias, author,
    speaker, or mentioned identity. Comparison is exact-match against
    NON_PERSON_LABELS after trimming surrounding whitespace -- never a
    substring/fuzzy check -- so ordinary text that merely contains a
    word like "redacted" is never caught by this. Phone-number and
    "Guest N" labels are matched by their full-string shape for the same
    reason."""
    if value is None:
        return False
    return value.strip() in NON_PERSON_LABELS or is_unlisted_participant_label(value)
