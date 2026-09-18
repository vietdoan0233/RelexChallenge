import json

from app.core.enums import DocumentType
from app.db import repository
from app.ingestion.embeddings import MockEmbeddingProvider, generate_embeddings
from app.schemas.evidence import Document, EvidenceUnit


def _seed_evidence_units(conn, evidence_ids: list[str]) -> None:
    # evidence_embeddings has a foreign key on evidence_units, so writing
    # a row for an evidence_id that was never actually ingested is not a
    # real scenario -- these tests seed the minimum that satisfies it.
    repository.upsert_document(
        conn, Document(document_id="doc1", filename="doc1.txt", document_type=DocumentType.EMAIL)
    )
    for i, evidence_id in enumerate(evidence_ids):
        repository.insert_evidence_unit(
            conn,
            EvidenceUnit(
                evidence_id=evidence_id,
                document_id="doc1",
                source_locator=f"loc{i}",
                unit_index=i,
                raw_text="placeholder",
                text_hash="hash",
            ),
        )


def test_mock_provider_is_deterministic_across_instances():
    a = MockEmbeddingProvider().embed_batch(["hello world"])
    b = MockEmbeddingProvider().embed_batch(["hello world"])
    assert a == b


def test_mock_provider_gives_different_texts_different_vectors():
    vectors = MockEmbeddingProvider().embed_batch(["alpha", "beta"])
    assert vectors[0] != vectors[1]


def test_skip_embeddings_reports_skipped_and_writes_no_rows(conn):
    report = generate_embeddings(conn, [("EV-1", "some text")], provider=None)
    assert report.skipped is True
    assert repository.embedding_row_count(conn) == 0


def test_generate_embeddings_writes_one_row_per_evidence_unit(conn):
    rows = [("EV-1", "first"), ("EV-2", "second")]
    _seed_evidence_units(conn, ["EV-1", "EV-2"])
    report = generate_embeddings(conn, rows, provider=MockEmbeddingProvider())
    assert report.succeeded == 2
    assert report.error is None
    assert repository.embedding_row_count(conn) == 2


def test_stored_vector_round_trips_as_json(conn):
    provider = MockEmbeddingProvider()
    _seed_evidence_units(conn, ["EV-1"])
    generate_embeddings(conn, [("EV-1", "text")], provider)
    row = conn.execute(
        "SELECT vector_json FROM evidence_embeddings WHERE evidence_id = 'EV-1'"
    ).fetchone()
    vector = json.loads(row["vector_json"])
    assert len(vector) == provider.dimensions


class _FailingProvider:
    model_name = "failing"

    def embed_batch(self, texts):
        raise RuntimeError("simulated API failure")


def test_provider_failure_is_reported_not_raised(conn):
    report = generate_embeddings(conn, [("EV-1", "text")], provider=_FailingProvider())
    assert report.error is not None
    assert "simulated API failure" in report.error
    assert repository.embedding_row_count(conn) == 0
