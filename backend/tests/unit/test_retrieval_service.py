import json

import pytest

from app.ingestion.embeddings import MockEmbeddingProvider
from app.retrieval.service import RetrievalService


class _FailingProvider:
    model_name = "mock-embedding-v1"

    def embed_batch(self, texts):
        raise RuntimeError("secret-looking provider detail")


class _OtherModelProvider(MockEmbeddingProvider):
    model_name = "some-other-model"


def _embed_all(conn, provider):
    rows = conn.execute("SELECT evidence_id, raw_text FROM evidence_units").fetchall()
    vectors = provider.embed_batch([r["raw_text"] for r in rows])
    for row, vector in zip(rows, vectors, strict=True):
        conn.execute(
            "INSERT INTO evidence_embeddings (evidence_id, model_name, vector_json) "
            "VALUES (?, ?, ?)",
            (row["evidence_id"], provider.model_name, json.dumps(vector)),
        )
    conn.commit()


@pytest.fixture
def corpus(conn, seed_units):
    ids = seed_units(
        conn,
        "meeting",
        [
            ("Shall we include bakery in the fresh workstream?", "Ana", "2025-01-10"),
            ("Yes.", "Lena", "2025-01-10"),
            ("Unrelated chatter about lunch and parking.", "Ana", "2025-01-10"),
            ("Bakery is now a separate workstream.", "Marco", "2025-06-10"),
        ],
    )
    return ids


def test_lexical_only_fallback_is_visible_not_silent(conn, corpus):
    result = RetrievalService(conn, None).retrieve("Is bakery in the fresh workstream?")
    assert result.semantic_used is False
    assert any("no embedding provider" in w for w in result.warnings)
    assert result.ranked_ids[0] in corpus


def test_hybrid_uses_both_sources(conn, corpus):
    provider = MockEmbeddingProvider()
    _embed_all(conn, provider)
    result = RetrievalService(conn, provider).retrieve("bakery fresh workstream")
    assert result.semantic_used is True
    assert result.warnings == []
    assert any(len(h.sources) == 2 for h in result.fused)


def test_provider_failure_degrades_without_leaking_detail(conn, corpus):
    _embed_all(conn, MockEmbeddingProvider())
    result = RetrievalService(conn, _FailingProvider()).retrieve("bakery workstream")
    assert result.semantic_used is False
    assert result.ranked_ids  # lexical still answers
    joined = " ".join(result.warnings)
    assert "RuntimeError" in joined
    assert "secret-looking" not in joined


def test_model_mismatch_refuses_to_mix_vector_spaces(conn, corpus):
    _embed_all(conn, MockEmbeddingProvider())
    result = RetrievalService(conn, _OtherModelProvider()).retrieve("bakery workstream")
    assert result.semantic_used is False
    assert any("differs" in w for w in result.warnings)


def test_temporal_question_triggers_a_later_sweep(conn, corpus):
    result = RetrievalService(conn, None).retrieve("Is bakery still in the fresh workstream now?")
    assert result.is_temporal
    assert result.temporal is not None
    assert corpus[3] in [h.evidence_id for h in result.temporal.hits]


def test_plain_question_has_no_sweep_unless_forced(conn, corpus):
    service = RetrievalService(conn, None)
    assert service.retrieve("bakery workstream").temporal is None
    assert service.retrieve("bakery workstream", temporal_sweep=True).is_temporal


def test_context_makes_a_bare_yes_understandable(conn, corpus):
    result = RetrievalService(conn, None).retrieve("Yes.", temporal_sweep=False)
    visible = result.visible_evidence_ids
    # The question that "Yes." answers is in the model-visible set.
    assert corpus[0] in visible
    assert corpus[1] in visible


def test_visible_set_only_contains_hydrated_units(conn, corpus):
    result = RetrievalService(conn, None).retrieve("bakery")
    assert set(result.visible_evidence_ids) <= set(result.records)


def test_deleted_evidence_disappears_even_before_refresh(conn, corpus):
    provider = MockEmbeddingProvider()
    _embed_all(conn, provider)
    service = RetrievalService(conn, provider)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (corpus[3],))
    result = service.retrieve("bakery separate workstream", temporal_sweep=True)
    assert corpus[3] not in result.records
    assert corpus[3] not in result.visible_evidence_ids
    assert corpus[3] not in result.ranked_ids
    service.refresh()
    assert corpus[3] not in service.retrieve("bakery separate workstream").ranked_ids


def test_trace_contains_ids_never_text(conn, corpus):
    result = RetrievalService(conn, None).retrieve("bakery workstream")
    blob = json.dumps(result.trace())
    assert "lunch and parking" not in blob
    assert "Shall we include" not in blob


def test_no_results_is_an_empty_result_not_an_error(conn, corpus):
    result = RetrievalService(conn, None).retrieve("zzzqqq nonexistentterm")
    assert result.fused == []
    assert result.visible_evidence_ids == []


def test_corrupt_embeddings_degrade_to_lexical_only(conn, corpus):
    conn.execute(
        "INSERT INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        "VALUES (?, 'mock-embedding-v1', '[1.0]')",
        (corpus[0],),
    )
    conn.execute(
        "INSERT INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        "VALUES (?, 'mock-embedding-v1', '[1.0, 2.0]')",
        (corpus[1],),
    )
    result = RetrievalService(conn, MockEmbeddingProvider()).retrieve("bakery workstream")
    assert result.semantic_used is False
    assert result.ranked_ids
