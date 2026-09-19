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

_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "january february march april may june july august september october november december"
        ).split(),
        start=1,
    )
}
_MONTH_YEAR = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(?:of\s+)?(20\d{2})\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")

_SUFFIXES = ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s", "ly")
_MIN_STEM_LENGTH = 4


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


# A question that asks for a quantity rarely uses the word the source uses:
# "what figures were reported" versus "thirty-one percent". Searching the unit
# word too is a plain lexical expansion, not a guess at the answer.
_QUANTITY_CUES = frozenset(
    "figure figures proportion proportions percentage percentages share rate rates ratio".split()
)
_QUANTITY_TERMS = ("percent",)


def topic_terms(query: str) -> list[str]:
    """Distinctive terms of a question, in order, without duplicates."""
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokenize(query):
        if len(token) < 2 or token in _STOPWORDS or token in _TEMPORAL_CUES or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    if any(t in _QUANTITY_CUES for t in tokenize(query)):
        terms.extend(t for t in _QUANTITY_TERMS if t not in seen)
    return terms


def is_temporal_query(query: str) -> bool:
    """True when the question concerns current state, a decision's fate, or
    change over time (CLAUDE.md 9.5). This routes an extra retrieval
    sweep; it is not a claim that newer evidence is truer."""
    lowered = query.lower()
    if any(phrase in lowered for phrase in _TEMPORAL_PHRASES):
        return True
    return any(token in _TEMPORAL_CUES for token in tokenize(lowered))


# Questions that ask for a set ("every figure", "each meeting") or a story
# ("how did it change", "show the trail") are answered by many scattered units,
# not by the handful a plain top-k keeps. They are routed to a wider pass.
_ENUMERATIVE_QUANTIFIED = re.compile(
    r"\b(?:every|each|all)\s+(?:the\s+|of\s+the\s+)?"
    r"(?:\w+\s+)?(?:figures?|numbers?|values?|percent(?:age)?s?|proportions?|mentions?|"
    r"instances?|versions?|meetings?|times?|decisions?|proposals?|changes?|updates?|"
    r"reports?|statements?|occurrences?|dates?)\b",
    re.IGNORECASE,
)
_ENUMERATIVE_PHRASES = (
    "how did",
    "how has",
    "how have",
    "changed over time",
    "show how",
    "the trail",
    "trail from",
    "timeline",
    "history of",
    "evolution",
    "evolved",
    "list all",
    "list every",
)


def is_enumerative_query(query: str) -> bool:
    """True when the question needs coverage across the archive rather than
    the single best match. Like temporal routing this only widens retrieval;
    it never decides what the answer is."""
    lowered = query.lower()
    if any(phrase in lowered for phrase in _ENUMERATIVE_PHRASES):
        return True
    return _ENUMERATIVE_QUANTIFIED.search(lowered) is not None


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


def date_range_hint(query: str) -> tuple[str, str, set[str]] | None:
    """A date window named in the question, e.g. "in September 2024".

    Returns (start, end_exclusive, tokens_consumed) as ISO dates, or None.
    A month + year gives that month; a bare year gives that year. Several
    mentions give the window that spans them. This adds a retrieval list
    restricted to the named period; it never drops evidence outside it.
    """
    lowered = query.lower()
    spans: list[tuple[str, str]] = []
    consumed: set[str] = set()
    for month_name, year in _MONTH_YEAR.findall(lowered):
        month, y = _MONTHS[month_name.lower()], int(year)
        end_month, end_year = (1, y + 1) if month == 12 else (month + 1, y)
        spans.append((f"{y:04d}-{month:02d}-01", f"{end_year:04d}-{end_month:02d}-01"))
        consumed.update({month_name.lower(), year})
    if not spans:
        for year in _YEAR.findall(lowered):
            spans.append((f"{int(year):04d}-01-01", f"{int(year) + 1:04d}-01-01"))
            consumed.add(year)
    if not spans:
        return None
    return min(s[0] for s in spans), max(s[1] for s in spans), consumed
