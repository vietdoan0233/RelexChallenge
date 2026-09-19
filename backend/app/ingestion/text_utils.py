import re

# The archive's own README warns these appear in more than one form and
# says explicitly not to match on a single string: "[Image removed by
# sender]", "[cid:image001.png]", a bare "Image", and the Swedish "Bild
# borttagen av avsandaren". This alternation is deliberately a list, not
# one pattern, so a new variant can be added without touching call sites.
_IMAGE_PLACEHOLDER_PATTERNS = [
    re.compile(r"\[Image removed by sender\]", re.IGNORECASE),
    re.compile(r"\[cid:[^\]]*\]", re.IGNORECASE),
    re.compile(r"Bild borttagen av avs[äa]ndaren", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z])Image(?![A-Za-z])"),
]

_TRUNCATION_ENDINGS = ("—", "–")  # em dash, en dash


def strip_image_placeholders(text: str) -> str:
    """Remove known image-placeholder variants for text used as search/
    embedding input. Never applied to the stored raw_text -- citations
    must show exactly what the source said."""
    cleaned = text
    for pattern in _IMAGE_PLACEHOLDER_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def is_truncated_text(text: str) -> bool:
    """Flags a statement that visibly cuts off mid-thought. Deliberately
    narrow (em/en dash only) and evidence-based: every truncation the
    corpus is known to contain ends this way. Never used to complete or
    guess the missing words -- only to flag that they are missing."""
    stripped = strip_image_placeholders(text).rstrip()
    return stripped.endswith(_TRUNCATION_ENDINGS)


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on `sep`, but not when inside parentheses -- needed because
    transcript Attendees headers look like 'Robert Kahn (Acme CFO, joins
    late)', where a naive comma split would sever the parenthetical."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def strip_parenthetical(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()


# The mail gateway prepends the same warning to every external message. Indexed
# as-is it dilutes BM25 for short replies ("Signed and attached." becomes one of
# ~35 words), so it is removed from the *search index* only. raw_text, the
# evidence shown to a reader, is never altered.
_MAIL_BANNER = re.compile(
    r"This email originated from outside of RELEX\..*?using the report button\.",
    re.IGNORECASE | re.DOTALL,
)


def search_text(raw_text: str) -> str:
    """The text FTS indexes: raw text minus gateway boilerplate and image
    placeholders. Purely a ranking aid; citations always show raw_text."""
    return strip_image_placeholders(_MAIL_BANNER.sub(" ", raw_text))
