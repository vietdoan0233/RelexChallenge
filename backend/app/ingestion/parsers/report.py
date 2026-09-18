"""Report parser.

CLAUDE.md's deletion-radius rule requires report units at bullet/short
sub-paragraph granularity, not one unit per whole status message, so that
deleting one person's evidence does not also erase unrelated bullets that
happened to share a coarse chunk. A recognized section label (Timeline,
Risk, Topics worked on last week, ...) is kept out of raw_text -- which
must stay byte-for-byte verbatim for citation purposes -- and carried in
thread_context instead, the field the schema already reserves for "what
larger context is this quote part of".
"""

import re

from app.ingestion.models import ParsedDocument, ParsedUnit
from app.ingestion.parsers.thread import split_messages
from app.ingestion.text_utils import is_truncated_text

_SECTION_HEADER = re.compile(
    r"^(Timeline|Risk|Question|Topics worked on last week|"
    r"Topics planned for this week|Potential risk identified)\b(.*)$"
)
_BULLET_LINE = re.compile(r"^\d+\.\s*(.*)$")


def parse(text: str, document_id: str, filename: str) -> ParsedDocument:
    messages, warnings = split_messages(text)

    subject = messages[0].header.get("Subject") if messages else None

    doc = ParsedDocument(
        document_id=document_id,
        filename=filename,
        document_type="REPORT",
        title=subject,
        source_date=messages[0].event_date if messages else None,
        thread_context=subject,
        warnings=warnings,
    )

    for message in messages:
        for raw_text, section_label in _split_into_units(message.body):
            thread_context = subject
            if section_label:
                thread_context = f"{subject} — {section_label}" if subject else section_label
            doc.units.append(
                ParsedUnit(
                    raw_text=raw_text,
                    speaker_sender=message.sender_name,
                    speaker_email=message.sender_email,
                    timestamp_text=message.header.get("Date") or message.header.get("Sent"),
                    thread_context=thread_context,
                    is_truncated=is_truncated_text(raw_text),
                    natural_locator=None,  # position within a message has no natural
                    # id; the persistent source-locator manifest assigns one instead
                    event_date=message.event_date,
                )
            )

    return doc


def _split_into_units(body: str) -> list[tuple[str, str | None]]:
    """Returns (raw_text, section_label) pairs, splitting each paragraph's
    numbered bullets into their own unit once there are two or more, so a
    "Topics worked on last week" block with five items becomes five small
    units rather than one large one."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    units: list[tuple[str, str | None]] = []

    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        header_match = _SECTION_HEADER.match(lines[0].strip())

        if not header_match:
            text = " ".join(line.strip() for line in lines if line.strip())
            if text:
                units.append((text, None))
            continue

        label = header_match.group(1)
        inline_status = header_match.group(2).strip()

        # Bullet numbering must be stripped whether there are many bullets
        # or just one -- a section with a single "1. ..." line is still a
        # bullet line, not prose, and must not keep its "1." prefix.
        bullet_texts: list[str] = []
        plain_lines: list[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            bullet_match = _BULLET_LINE.match(stripped)
            if bullet_match:
                text = bullet_match.group(1).strip()
                if text:
                    bullet_texts.append(text)
            else:
                plain_lines.append(stripped)

        if len(bullet_texts) >= 2:
            if inline_status:
                units.append((inline_status, label))
            for bullet_text in bullet_texts:
                units.append((bullet_text, label))
            for plain in plain_lines:
                units.append((plain, label))
        else:
            combined = " ".join(p for p in [inline_status, *bullet_texts, *plain_lines] if p)
            if combined:
                units.append((combined, label))

    return units
