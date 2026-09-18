"""Shared message-splitting for the Outlook-export thread format that
emails and reports both use: reverse-chronological, every earlier message
quoted below the newest one, each message headed by its own Subject/
From/Date-or-Sent/To/Cc block.

The corpus mixes locales -- most messages use English Outlook headers,
but a substantial minority use a German or Swedish Outlook UI (Von/
Gesendet/An/Betreff, or Från/Skickat/Till/Ämne/Kopia). Missing these was
a real bug, not a hypothetical one: matching only the English labels
silently swallowed every German- or Swedish-headed message into the
body of whichever English-headed message preceded it, undercounting
messages in about a third of the email files.
"""

import re
from dataclasses import dataclass
from datetime import datetime

_HEADER_ALIASES = {
    "Subject": "Subject",
    "Betreff": "Subject",
    "Ämne": "Subject",
    "From": "From",
    "Von": "From",
    "Från": "From",
    "Sent": "Sent",
    "Gesendet": "Sent",
    "Skickat": "Sent",
    "Date": "Date",
    "Datum": "Date",
    "To": "To",
    "An": "To",
    "Till": "To",
    "Cc": "Cc",
    "Kopia": "Cc",
    "Messages in thread": "Messages in thread",
}
_HEADER_FIELD = re.compile("^(" + "|".join(re.escape(k) for k in _HEADER_ALIASES) + r"):\s*(.*)$")
_FROM_LABELS = ("From", "Von", "Från")
_FROM_LINE = re.compile("^(" + "|".join(_FROM_LABELS) + r"):\s*(.*)$")
_NAME_EMAIL = re.compile(r"^(.*?)\s*<([^>]+)>\s*$")
_DISCLAIMER_PREFIX = "***"

_WEEKDAY_PREFIX = re.compile(r"^[^\d,]+,\s*")
_SWEDISH_DEN_PREFIX = re.compile(r"^den\s+", re.IGNORECASE)
_DAY_WITH_PERIOD = re.compile(r"^(\d{1,2})\.\s+")

_MONTH_TRANSLATIONS = {
    # German
    "januar": "January",
    "februar": "February",
    "märz": "March",
    "marz": "March",
    "april": "April",
    "mai": "May",
    "juni": "June",
    "juli": "July",
    "august": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "dezember": "December",
    # Swedish (several overlap with the German entries above)
    "januari": "January",
    "februari": "February",
    "mars": "March",
    "maj": "May",
    "augusti": "August",
}

_DATE_FORMATS = (
    "%B %d, %Y %I:%M %p",  # October 30, 2025 12:02 PM
    "%B %d, %Y %H:%M",  # September 4, 2025 14:20
    "%d %B %Y %H:%M",  # 29 June 2026 10:15 (German/Swedish, after normalizing)
)


@dataclass
class ThreadMessage:
    header: dict[str, str]
    body: str
    natural_locator: str
    sender_name: str | None
    sender_email: str | None
    event_date: str | None


def split_messages(text: str) -> tuple[list[ThreadMessage], list[str]]:
    lines = text.splitlines()
    warnings: list[str] = []

    start = 0
    while start < len(lines) and (
        not lines[start].strip() or lines[start].strip().startswith(_DISCLAIMER_PREFIX)
    ):
        start += 1

    from_indices = [i for i in range(start, len(lines)) if _FROM_LINE.match(lines[i].strip())]
    if not from_indices:
        warnings.append("no 'From:' header found; thread could not be split into messages")
        return [], warnings

    messages: list[ThreadMessage] = []
    for idx, from_i in enumerate(from_indices):
        # The header block's fields aren't in a fixed order: the newest
        # message puts Subject before From, but every quoted message
        # below it puts Subject after To/Cc. Scan backward from the
        # From: line first to pick up a preceding Subject (bounded by the
        # previous message's own From: line, so this can never walk into
        # a different message's header).
        floor = from_indices[idx - 1] + 1 if idx > 0 else 0
        header_start = from_i
        j = from_i - 1
        while j >= floor and _HEADER_FIELD.match(lines[j].strip()):
            header_start = j
            j -= 1

        header: dict[str, str] = {}
        i = header_start
        while i < len(lines):
            stripped = lines[i].strip()
            match = _HEADER_FIELD.match(stripped)
            if not match:
                break
            canonical_key = _HEADER_ALIASES[match.group(1)]
            header[canonical_key] = match.group(2).strip()
            i += 1

        body_end = from_indices[idx + 1] if idx + 1 < len(from_indices) else len(lines)
        body = "\n".join(lines[i:body_end]).strip()

        sender_name, sender_email = _split_name_email(header.get("From", ""))
        date_value = header.get("Date") or header.get("Sent") or ""
        event_date = _parse_event_date(date_value)

        messages.append(
            ThreadMessage(
                header=header,
                body=body,
                natural_locator=_slugify(date_value) or f"msg{idx}",
                sender_name=sender_name,
                sender_email=sender_email,
                event_date=event_date,
            )
        )

    return messages, warnings


def _split_name_email(value: str) -> tuple[str | None, str | None]:
    match = _NAME_EMAIL.match(value.strip())
    if match:
        name = match.group(1).strip() or None
        return name, match.group(2).strip()
    if "@" in value:
        return None, value.strip()
    return (value.strip() or None), None


def _parse_event_date(value: str) -> str | None:
    value = _SWEDISH_DEN_PREFIX.sub("", value.strip())
    value = _WEEKDAY_PREFIX.sub("", value)
    value = _translate_months(value)
    value = _DAY_WITH_PERIOD.sub(r"\1 ", value)

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _translate_months(value: str) -> str:
    def replace(match: re.Match) -> str:
        return _MONTH_TRANSLATIONS.get(match.group(0).lower(), match.group(0))

    return re.sub(r"[A-Za-zÀ-ÿ]+", replace, value)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
