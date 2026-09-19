"""Ingestion orchestration: enumerate data/source/, parse every document,
assign stable identity (documents, evidence units, people/aliases), and
populate FTS + embeddings.

Safe to re-run: every ingestion-owned table (documents, evidence_units,
people, person_aliases, evidence_people, evidence_embeddings,
evidence_fts -- see migrations._REBUILDABLE_TABLES) is dropped and
regenerated every time. That is not "every table except source_locators":
Cases/Pulse tables (cases, case_evidence, pulse_findings, finding_evidence)
are separate, not-yet-implemented Phase 2+ concerns and this reset does
not touch them. Regenerating people/person_aliases fresh from data/source/
plus the reviewed identity manifest on each run, rather than accumulating
them across runs, is safe specifically because both of those inputs are
sanitizable: a false identity from an earlier extraction pass cannot
outlive the run that produced it, and a rebuild after a deletion cannot
resurrect what was removed as long as both inputs stay sanitized
(CLAUDE.md 7.3, 18.3).

Failure safety: source files and the reviewed identity manifest are fully
parsed and validated (see people.load_reviewed_identities) *before* the
destructive reset runs, so a malformed manifest edit fails loudly without
having dropped the existing database first. This does not make the reset
itself atomic -- a failure partway through the write/repopulation phase
that follows the reset (e.g. an unexpected exception while inserting
evidence units) can still leave a partially-rebuilt database, because
SQLite's DDL/DML transaction semantics in the sqlite3 stdlib module are
not reliable enough on this project's supported Python versions to safely
roll back a DROP TABLE. Re-running ingestion after fixing the underlying
cause is the documented recovery path for that residual failure mode.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core import anonymous_labels
from app.core.enums import DocumentType, PersonRelation
from app.db import migrations, repository
from app.ingestion import locator_manifest, people, text_utils
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
    # people_count/alias_count/relation_counts are read back from the
    # database after everything commits -- never from attempted-insert
    # tallies, which can overstate what actually got stored.
    people_count: int = 0
    alias_count: int = 0
    relation_counts: dict[str, int] = field(default_factory=dict)
    unresolved_alias_candidates: list[str] = field(default_factory=list)
    reviewed_text_only: list[str] = field(default_factory=list)
    reviewed_short_aliases: list[str] = field(default_factory=list)
    rejected_candidates: list[str] = field(default_factory=list)
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
    # Non-destructive: ensures source_locators exists so locator assignment
    # below can read/write it. The destructive reset is deliberately held
    # off until every source file is parsed and the reviewed identity
    # manifest has passed validation, so a malformed manifest edit raises
    # ManifestValidationError before the existing database is dropped.
    migrations.initialize(conn)

    documents = parse_all(source_dir)
    for doc in documents:
        if doc.document_type == DocumentType.TRANSCRIPT.value:
            doc.units = transcript_parser.assign_locators_and_merge(
                conn, doc.document_id, doc.fragments
            )

    people.load_reviewed_identities(source_dir)

    migrations.reset_rebuildable_tables(conn)

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
            repository.insert_fts_row(
                conn,
                evidence_id,
                text_utils.search_text(unit.raw_text),
                thread_context=unit.thread_context or doc.thread_context,
                speaker_sender=unit.speaker_sender,
            )
            evidence_rows_for_embedding.append((evidence_id, unit.raw_text))
            unit_records.append((evidence_id, doc.document_type, unit))

            report.evidence_units_by_type[doc.document_type] = (
                report.evidence_units_by_type.get(doc.document_type, 0) + 1
            )

    people_report = people.seed_and_discover(conn, documents, source_dir)
    report.unresolved_alias_candidates = people_report.unresolved_alias_candidates
    report.reviewed_text_only = people_report.reviewed_text_only
    report.reviewed_short_aliases = people_report.reviewed_short_aliases
    report.rejected_candidates = people_report.rejected_candidates

    _link_relations(conn, unit_records)

    report.fts_row_count = repository.fts_row_count(conn)
    migrations.mark_fts_current(conn)
    report.embeddings = generate_embeddings(conn, evidence_rows_for_embedding, embedding_provider)

    conn.commit()

    # Read actual stored counts back after commit rather than trusting
    # attempted-insert tallies -- INSERT OR IGNORE silently no-ops on a
    # duplicate, so "rows we tried to insert" and "rows that exist" can
    # legitimately differ.
    report.people_count = repository.people_row_count(conn)
    report.alias_count = repository.alias_row_count(conn)
    report.relation_counts = repository.relation_counts(conn)

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

        is_anonymous_speaker = anonymous_labels.is_non_person_label(unit.speaker_sender)
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
