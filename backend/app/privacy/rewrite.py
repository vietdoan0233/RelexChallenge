"""Alias-bearing canonical-source rewriting (AGENTS.md/CLAUDE.md 18.0.4).

Superseded: app/privacy/redact.py (retired v1.5 generic-marker redaction).

Structural coverage mirrors the old redact.py -- a speaker-marker line, a
From/Von/Från header, a recipient/attendee entry, and a signature block all
identify a person as directly as an inline mention -- but the replacement
is now the target's own stable display_alias everywhere, never a generic
marker, so the rewritten speaker/sender/mention stays attributable to one
stable profile instead of collapsing every pseudonymised person into the
same three labels.

This also drops most of redact.py's role-specific branching. Because every
role now substitutes the *same* alias text, a plain whole-text find/replace
of (name pattern -> alias) and (email pattern -> alias email) already
produces the right result for a sender header ("From: NAME <email>"), a
recipient/attendee entry ("NAME (RELEX)"), and an inline mention, all at
once, while leaving the surrounding organizational structure (the "(RELEX)"
tag, the list punctuation) untouched. The two things that still need
special-casing are the ones plain substitution cannot express: dropping a
transcript's bare-initials UI chrome (there is no alias-derived equivalent
worth inventing), and dropping the extra signature-block lines (job title,
phone) that sit *under* a bare name line but are not themselves a name/email
match.
"""

import re

from app.privacy.targets import Target, name_pattern

# A signature block is the run of non-blank lines that follows a line holding
# only the person's name; capped so a missing blank line cannot swallow a body.
_MAX_SIGNATURE_LINES = 6


def alias_email(display_alias: str) -> str:
    """A synthetic address that can never collide with, or be mistaken for,
    a real one: the .invalid TLD is reserved by RFC 2606 specifically for
    addresses guaranteed never to resolve."""
    slug = re.sub(r"[^a-z0-9]+", "-", display_alias.lower()).strip("-")
    return f"{slug}@pseudonymised.invalid"


def rewrite_text(text: str, kind: str, target: Target) -> str:
    """`kind` is 'transcripts', 'emails' or 'reports' (the source subfolder)."""
    patterns = [name_pattern(n) for n in target.names]
    email_patterns = [re.compile(re.escape(e), re.IGNORECASE) for e in target.emails]
    initials = target.initials
    alias = target.display_alias
    alias_addr = alias_email(alias)

    def is_bare_name(line: str) -> bool:
        stripped = line.strip()
        return any(p.fullmatch(stripped) for p in patterns)

    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        if kind == "transcripts" and len(initials) >= 2 and line.strip() == initials:
            i += 1  # bare initials chip: UI chrome derived from the name
            continue

        if kind in ("emails", "reports") and is_bare_name(line):
            # Signature: keep the name, under its alias, but drop the
            # contiguous block beneath it (job title, phone, email) that
            # would otherwise keep identifying the person alongside it.
            out.append(alias)
            i += 1
            dropped = 0
            while i < len(lines) and lines[i].strip() and dropped < _MAX_SIGNATURE_LINES:
                i += 1
                dropped += 1
            continue

        out.append(_inline(line, patterns, email_patterns, alias, alias_addr))
        i += 1
    # A name hard-wrapped across a line break ("Kwame\nBoateng") is invisible to
    # the per-line pass above, so sweep the whole text once more. The patterns
    # already tolerate any whitespace, including a newline, between a name's words.
    return _inline("\n".join(out), patterns, email_patterns, alias, alias_addr)


def rewrite_plain_text(text: str, target: Target) -> str:
    """Plain find/replace, no line-shaped special-casing (no signature-block
    dropping, no initials-chip removal): for free-text/JSON application
    surfaces that are not transcript/email/report content but can still
    legitimately mention a participant, e.g. data/source/external_signals.json
    (its own file description requires it be treated as an application-owned
    surface just like the evidence documents -- CLAUDE.md 18.0.4's "other
    direct identifying metadata"). Safe to run on JSON text because it only
    ever substitutes identifier substrings, never structural characters."""
    patterns = [name_pattern(n) for n in target.names]
    email_patterns = [re.compile(re.escape(e), re.IGNORECASE) for e in target.emails]
    alias_addr = alias_email(target.display_alias)
    return _inline(text, patterns, email_patterns, target.display_alias, alias_addr)


def _inline(line: str, patterns, email_patterns, alias: str, alias_addr: str) -> str:
    for pattern in email_patterns:
        line = pattern.sub(alias_addr, line)
    for pattern in patterns:
        line = pattern.sub(alias, line)
    return line


def restore_text(
    text: str, display_alias: str, original_name: str, original_email: str | None
) -> str:
    """The admin reversal counterpart of rewrite_text: replaces every
    occurrence of the subject's display_alias (and its synthetic
    alias_email, if an original email exists to restore) with their
    original name/email.

    Disclosed, non-guessing limitation: pseudonymisation collapses every
    original form (full name, a reviewed first name, a reviewed spoken
    variant, ...) into the *same* alias wherever it occurred, so reversal
    cannot know which original short form belonged at any given position --
    only the vault's one canonical original_name is known with confidence.
    Every occurrence is therefore restored to that one canonical form,
    which correctly restores *who* is attributable at each position without
    ever inventing which exact original wording was there.
    """
    alias_pattern = name_pattern(display_alias)
    out = alias_pattern.sub(original_name, text)
    if original_email:
        addr_pattern = re.compile(re.escape(alias_email(display_alias)), re.IGNORECASE)
        out = addr_pattern.sub(original_email, out)
    return out
