from app.ingestion.models import ParsedDocument, ParsedUnit
from app.ingestion.parsers.thread import split_messages
from app.ingestion.text_utils import is_truncated_text


def parse(text: str, document_id: str, filename: str) -> ParsedDocument:
    messages, warnings = split_messages(text)

    subject = messages[0].header.get("Subject") if messages else None

    doc = ParsedDocument(
        document_id=document_id,
        filename=filename,
        document_type="EMAIL",
        title=subject,
        source_date=messages[0].event_date if messages else None,
        thread_context=subject,
        warnings=warnings,
    )

    for message in messages:
        if not message.body:
            continue
        doc.units.append(
            ParsedUnit(
                raw_text=message.body,
                speaker_sender=message.sender_name,
                speaker_email=message.sender_email,
                timestamp_text=message.header.get("Date") or message.header.get("Sent"),
                is_truncated=is_truncated_text(message.body),
                natural_locator=message.natural_locator,
                event_date=message.event_date,
            )
        )

    return doc
