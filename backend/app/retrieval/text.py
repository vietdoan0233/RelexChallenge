"""Deterministic query-text helpers shared by every retrieval path.

Kept dependency-free on purpose: query analysis must be reproducible in
tests and must never need a model call, so a retrieval miss is always
attributable to ranking rather than to a hidden rewrite of the question.
"""

import re

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Question scaffolding that carries no topical signal. Deliberately small:
# an over-eager stopword list silently deletes the one distinctive term a
# question turns on.
_STOPWORDS = frozenset(
    """
    a an and are as at be been being but by did do does done for from had has have how i if in
    into is it its me my no not of on or our so than that the their them then there these they
    this those to us was we were what when where which who whom whose why will with would you
    your about after again all also any because before between both can could each few more most
    other over own same should some such too very just out came come
    """.split()
)

# Words that make a question about state-over-time. They steer temporal
# routing but say nothing about the topic, so they are excluded from the
# topic terms used to sweep for later evidence.
_TEMPORAL_CUES = frozenset(
    """
    current currently latest now still final finally ultimately eventually later
    changed change changes supersede superseded superseding superseded evolution evolve
    evolved history historically over time today anymore longer
    """.split()
)

# Multi-word cues that are matched on the raw lowercase question.
_TEMPORAL_PHRASES = (
    "over time",
    "is it still",
    "no longer",
    "what is it now",
    "as of now",
    "where does it stand",
    "what happened next",
    "what happened afterwards",
    "what happened after",
    "was it done",
    "was it ever",
    "never done",
    "did it happen",
)

_SUFFIXES = ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s", "ly")
_MIN_STEM_LENGTH = 4


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def topic_terms(query: str) -> list[str]:
    """Distinctive terms of a question, in order, without duplicates."""
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokenize(query):
        if len(token) < 2 or token in _STOPWORDS or token in _TEMPORAL_CUES or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def is_temporal_query(query: str) -> bool:
    """True when the question concerns current state, a decision's fate, or
    change over time (CLAUDE.md 9.5). This routes an extra retrieval
    sweep; it is not a claim that newer evidence is truer."""
    lowered = query.lower()
    if any(phrase in lowered for phrase in _TEMPORAL_PHRASES):
        return True
    return any(token in _TEMPORAL_CUES for token in tokenize(lowered))


# Irregular derivations plain prefix matching cannot bridge.
_IRREGULAR_STEMS = {"decid": ("decis",), "sign": ("signat",)}


def light_stem(term: str) -> str:
    """Strip one common suffix so `agreed` also finds `agreement`.

    FTS5's default tokenizer does not stem. Prefix matching on a stem is a
    cheap, deterministic stand-in that costs no dependency and stays
    inspectable.
    """
    for suffix in _SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= _MIN_STEM_LENGTH:
            stem = term[: -len(suffix)]
            # "committed" -> "committ" must still reach "commit".
            if len(stem) > _MIN_STEM_LENGTH and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
                stem = stem[:-1]
            return stem
    return term


def term_variants(term: str) -> list[str]:
    """Match prefixes for one query term: its stem plus known irregular forms."""
    stem = light_stem(term)
    return [stem, *_IRREGULAR_STEMS.get(stem, ())]


def fts_match_expression(terms: list[str]) -> str | None:
    """OR-joined, individually quoted FTS5 expression.

    Every term is quoted so user text can never inject FTS5 operators
    (`NEAR`, `-`, `:`, unbalanced quotes). OR + BM25 lets documents that
    match more, and rarer, terms rank first without requiring an exact
    conjunction the corpus rarely satisfies.
    """
    parts: list[str] = []
    for term in terms:
        for variant in term_variants(term):
            parts.append(f'"{variant}"*' if len(variant) >= _MIN_STEM_LENGTH else f'"{term}"')
    return " OR ".join(dict.fromkeys(parts)) if parts else None
