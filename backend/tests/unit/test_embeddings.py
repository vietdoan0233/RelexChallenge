import json

import pytest

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
    assert report.persisted_rows == 0
    assert repository.embedding_row_count(conn) == 0


def test_generate_embeddings_writes_one_row_per_evidence_unit(conn):
    rows = [("EV-1", "first"), ("EV-2", "second")]
    _seed_evidence_units(conn, ["EV-1", "EV-2"])
    report = generate_embeddings(conn, rows, provider=MockEmbeddingProvider())
    assert report.succeeded == 2
    assert report.error is None
    assert report.persisted_rows == 2
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


class _RecordingProvider:
    model_name = "recording"

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed_batch(self, texts):
        self.calls.append(texts)
        return [[float(index)] for index in range(len(texts))]


def test_generate_embeddings_sends_bounded_batches(conn):
    rows = [(f"EV-{index}", f"text {index}") for index in range(3)]
    _seed_evidence_units(conn, [row[0] for row in rows])
    provider = _RecordingProvider()

    report = generate_embeddings(conn, rows, provider, batch_size=2)

    assert provider.calls == [["text 0", "text 1"], ["text 2"]]
    assert report.succeeded == 3
    assert report.error is None
    assert repository.embedding_row_count(conn) == 3


class _TransientFailureProvider:
    model_name = "transient"

    def __init__(self):
        self.calls = 0

    def embed_batch(self, texts):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary rate limit")
        return [[1.0] for _ in texts]


def test_generate_embeddings_retries_transient_provider_failure(conn):
    _seed_evidence_units(conn, ["EV-1"])
    provider = _TransientFailureProvider()

    report = generate_embeddings(
        conn,
        [("EV-1", "text")],
        provider,
        max_retries=1,
        initial_retry_delay_seconds=0,
    )

    assert provider.calls == 2
    assert report.succeeded == 1
    assert report.error is None


class _WrongLengthProvider:
    model_name = "wrong-length"

    def embed_batch(self, texts):
        return [[1.0]]


def test_failed_batch_does_not_write_partial_embedding_rows(conn):
    _seed_evidence_units(conn, ["EV-1", "EV-2"])

    report = generate_embeddings(
        conn,
        [("EV-1", "first"), ("EV-2", "second")],
        _WrongLengthProvider(),
        max_retries=0,
    )

    assert report.succeeded == 0
    assert "returned 1 vectors for 2 evidence units" in report.error
    assert report.persisted_rows == 0
    assert repository.embedding_row_count(conn) == 0


class _FirstBatchOnlyProvider:
    model_name = "first-batch-only"

    def __init__(self):
        self.calls = 0

    def embed_batch(self, texts):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("provider unavailable")
        return [[1.0, 2.0] for _ in texts]


def test_partial_batch_failure_reports_the_persisted_prefix(conn):
    rows = [(f"EV-{index}", f"text {index}") for index in range(3)]
    _seed_evidence_units(conn, [row[0] for row in rows])

    report = generate_embeddings(
        conn,
        rows,
        _FirstBatchOnlyProvider(),
        batch_size=2,
        max_retries=0,
    )

    assert report.succeeded == 2
    assert report.persisted_rows == 2
    assert "embedding batch 2 failed" in report.error


@pytest.mark.parametrize(
    ("vector", "message"),
    [
        ([float("nan")], "non-finite"),
        (["not-a-number"], "not numeric"),
        ([], "non-empty one-dimensional"),
    ],
)
def test_malformed_vectors_are_rejected_without_writes(conn, vector, message):
    _seed_evidence_units(conn, ["EV-1"])

    class _MalformedProvider:
        model_name = "malformed"

        def embed_batch(self, texts):
            return [vector]

    report = generate_embeddings(conn, [("EV-1", "text")], _MalformedProvider(), max_retries=0)

    assert message in report.error
    assert report.persisted_rows == 0


def test_dimension_mismatch_between_batches_is_rejected(conn):
    rows = [(f"EV-{index}", f"text {index}") for index in range(2)]
    _seed_evidence_units(conn, [row[0] for row in rows])

    class _DimensionChangingProvider:
        model_name = "dimension-changing"

        def __init__(self):
            self.calls = 0

        def embed_batch(self, texts):
            self.calls += 1
            return [[1.0, 2.0] if self.calls == 1 else [1.0]]

    report = generate_embeddings(
        conn,
        rows,
        _DimensionChangingProvider(),
        batch_size=1,
        max_retries=0,
    )

    assert report.succeeded == 1
    assert report.persisted_rows == 1
    assert "dimension 1; expected 2" in report.error
