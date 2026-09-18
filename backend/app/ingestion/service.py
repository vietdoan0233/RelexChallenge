"""Ingestion orchestration: enumerate data/source/, parse every document,
assign stable identity (documents, evidence units, people/aliases), and
populate FTS + embeddings.

Safe to re-run: documents/evidence_units/evidence_people/evidence_fts are
dropped and regenerated every time, while people/person_aliases/
source_locators persist, so a rebuild after a deletion cannot resurrect
what was removed (CLAUDE.md 7.3, 18.3).
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.enums import DocumentType, PersonRelation
from app.db import migrations, repository
from app.ingestion import locator_manifest, people
from app.ingestion.embeddings import EmbeddingProvider, EmbeddingRunReport, generate_embeddings
from app.ingestion.models import ParsedDocument, ParsedUnit
from app.ingestion.parsers import email as email_parser
from app.ingestion.parsers import report as report_parser
from app.ingestion.parsers import transcript as transcript_parser
from app.schemas.evidence import Document, EvidenceUnit

_PARSERS = {
    "transcripts": (transcript_parser.parse, DocumentType.TRANSCRIPT),
    "emails": (email_parser.parse, DocumentType.EMAIL),
    "reports": (report_parser.parse, DocumentType.REPORT),
}


@dataclass
class IngestionReport:
    documents_by_type: dict[str, int] = field(default_factory=dict)
    evidence_units_by_type: dict[str, int] = field(default_factory=dict)
    parse_warnings: list[str] = field(default_factory=list)
    fts_row_count: int = 0
    people_count: int = 0
    alias_count: int = 0
    unresolved_alias_candidates: list[str] = field(default_factory=list)
    text_only_mentions: list[str] = field(default_factory=list)
    embeddings: EmbeddingRunReport = field(default_factory=EmbeddingRunReport)


def enumerate_source_files(source_dir: Path) -> list[tuple[Path, str]]:
    """Only emails/reports/transcripts under data/source/ are evidence.
    Reference material such as PRACTICE_QUESTIONS.md deliberately lives
    outside data/source/ so it is never a candidate here."""
    files = []
    for subdir in _PARSERS:
        folder = source_dir / subdir
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.txt")):
            files.append((path, subdir))
    return files


def parse_all(source_dir: Path) -> list[ParsedDocument]:
    documents = []
    for path, subdir in enumerate_source_files(source_dir):
        parse_fn, _ = _PARSERS[subdir]
        text = path.read_text(encoding="utf-8")
        documents.append(parse_fn(text, path.stem, path.name))
    return documents


def ingest(
    conn: sqlite3.Connection,
    source_dir: Path,
    embedding_provider: EmbeddingProvider | None,
) -> IngestionReport:
    migrations.initialize(conn)
    migrations.reset_rebuildable_tables(conn)

    documents = parse_all(source_dir)
    for doc in documents:
        if doc.document_type == DocumentType.TRANSCRIPT.value:
            doc.units = transcript_parser.assign_locators_and_merge(
                conn, doc.document_id, doc.fragments
            )

    report = IngestionReport()

    # (evidence_id, document_type, unit) for every inserted unit, kept for
    # the relation-linking pass below, which needs people/aliases to be
    # fully seeded first.
    unit_records: list[tuple[str, str, ParsedUnit]] = []
    evidence_rows_for_embedding: list[tuple[str, str]] = []

    for doc in documents:
        report.documents_by_type[doc.document_type] = (
            report.documents_by_type.get(doc.document_type, 0) + 1
        )
        report.parse_warnings.extend(f"{doc.filename}: {w}" for w in doc.warnings)

        repository.upsert_document(
            conn,
            Document(
                document_id=doc.document_id,
                filename=doc.filename,
                document_type=DocumentType(doc.document_type),
                title=doc.title,
                source_date=doc.source_date,
                thread_context=doc.thread_context,
            ),
        )

        locators = _assign_locators_for_document(conn, doc)

        for index, (unit, locator) in enumerate(zip(doc.units, locators, strict=True)):
            evidence_id = locator_manifest.evidence_id_for(doc.document_id, locator)
            repository.insert_evidence_unit(
                conn,
                EvidenceUnit(
                    evidence_id=evidence_id,
                    document_id=doc.document_id,
                    source_locator=locator,
                    unit_index=index,
                    speaker_sender=unit.speaker_sender,
                    event_date=unit.event_date or doc.source_date,
                    timestamp_text=unit.timestamp_text,
                    thread_context=unit.thread_context or doc.thread_context,
                    raw_text=unit.raw_text,
                    text_hash=repository.fingerprint(unit.raw_text),
                    is_truncated=unit.is_truncated,
                ),
            )
            repository.insert_fts_row(conn, evidence_id, unit.raw_text)
            evidence_rows_for_embedding.append((evidence_id, unit.raw_text))
            unit_records.append((evidence_id, doc.document_type, unit))

            report.evidence_units_by_type[doc.document_type] = (
                report.evidence_units_by_type.get(doc.document_type, 0) + 1
            )

    people_report = people.seed_and_discover(conn, documents)
    report.people_count = people_report.people_count
    report.alias_count = people_report.alias_count
    report.unresolved_alias_candidates = people_report.unresolved_candidates
    report.text_only_mentions = people_report.text_only_mentions

    _link_relations(conn, unit_records)

    report.fts_row_count = repository.fts_row_count(conn)
    report.embeddings = generate_embeddings(conn, evidence_rows_for_embedding, embedding_provider)

    conn.commit()
    return report


def _assign_locators_for_document(conn: sqlite3.Connection, doc: ParsedDocument) -> list[str]:
    """Transcripts arrive with their locators already finalized by
    transcript.assign_locators_and_merge, which had to run the manifest
    assignment itself before it could decide how to merge fragments
    safely (see that function's docstring). Only email/report units --
    which never merge -- still need assignment here."""
    if doc.document_type == DocumentType.TRANSCRIPT.value:
        return [unit.natural_locator for unit in doc.units]

    locators: list[str | None] = []
    pending_fingerprints: list[str] = []
    pending_indices: list[int] = []

    for i, unit in enumerate(doc.units):
        fp = repository.fingerprint(unit.raw_text)
        if unit.natural_locator is not None:
            assignment = locator_manifest.assign_natural_locator(
                conn, doc.document_id, unit.natural_locator, fp
            )
            locators.append(assignment.source_locator)
        else:
            locators.append(None)
            pending_fingerprints.append(fp)
            pending_indices.append(i)

    if pending_fingerprints:
        assigned = locator_manifest.assign_manifest_locators(
            conn, doc.document_id, pending_fingerprints
        )
        for idx, assignment in zip(pending_indices, assigned, strict=True):
            locators[idx] = assignment.source_locator

    return locators


def _link_relations(
    conn: sqlite3.Connection, unit_records: list[tuple[str, str, ParsedUnit]]
) -> None:
    for evidence_id, document_type, unit in unit_records:
        exclude: set[str] = set()

        is_anonymous_speaker = unit.speaker_sender in ("Me", "Them", "Unknown Speaker")
        if unit.speaker_sender and not is_anonymous_speaker:
            person_id = repository.find_person_id_by_canonical_name(conn, unit.speaker_sender)
            if person_id:
                relation = (
                    PersonRelation.AUTHOR
                    if document_type in (DocumentType.EMAIL.value, DocumentType.REPORT.value)
                    else PersonRelation.SPEAKER
                )
                repository.link_evidence_person(conn, evidence_id, person_id, relation)
                exclude.add(person_id)

        people.link_mentions(conn, evidence_id, unit.raw_text, exclude)
