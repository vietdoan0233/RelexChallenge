"""Database-hydrated evidence records.

Everything a reader is shown about a unit -- speaker, date, document,
thread, exact text -- comes from these rows, never from model output
(CLAUDE.md 10, 15).
"""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    document_id: str
    filename: str
    document_type: str
    document_title: str | None
    unit_index: int
    speaker_sender: str | None
    event_date: str | None
    timestamp_text: str | None
    thread_context: str | None
    raw_text: str
    is_truncated: bool


_HYDRATE_SQL = """
    SELECT e.evidence_id, e.document_id, d.filename, d.document_type,
           d.title AS document_title, e.unit_index, e.speaker_sender, e.event_date,
           e.timestamp_text, e.thread_context, e.raw_text, e.is_truncated
    FROM evidence_units e JOIN documents d ON d.document_id = e.document_id
"""

# SQLite's default bound-variable limit is far above what retrieval uses,
# but chunking keeps this safe if a caller ever hydrates a larger set.
_CHUNK = 500


def _to_record(row: sqlite3.Row) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row["evidence_id"],
        document_id=row["document_id"],
        filename=row["filename"],
        document_type=row["document_type"],
        document_title=row["document_title"],
        unit_index=row["unit_index"],
        speaker_sender=row["speaker_sender"],
        event_date=row["event_date"],
        timestamp_text=row["timestamp_text"],
        thread_context=row["thread_context"],
        raw_text=row["raw_text"],
        is_truncated=bool(row["is_truncated"]),
    )


def hydrate(conn: sqlite3.Connection, evidence_ids: list[str]) -> list[EvidenceRecord]:
    """Records for the ids that still exist, in the order requested.

    An id with no row (deleted, or stale in a cached index) is dropped
    rather than raising: a stale index entry must never resurface as
    evidence after a deletion.
    """
    found: dict[str, EvidenceRecord] = {}
    unique = list(dict.fromkeys(evidence_ids))
    for start in range(0, len(unique), _CHUNK):
        chunk = unique[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(f"{_HYDRATE_SQL} WHERE e.evidence_id IN ({marks})", chunk).fetchall()
        found.update({row["evidence_id"]: _to_record(row) for row in rows})
    return [found[i] for i in unique if i in found]


def get_record(conn: sqlite3.Connection, evidence_id: str) -> EvidenceRecord | None:
    records = hydrate(conn, [evidence_id])
    return records[0] if records else None
