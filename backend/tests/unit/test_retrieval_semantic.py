import json

import numpy as np
import pytest

from app.retrieval.semantic import SemanticIndex, SemanticIndexError


def _store(conn, evidence_id, vector, model="m1"):
    conn.execute(
        "INSERT INTO evidence_embeddings (evidence_id, model_name, vector_json) VALUES (?, ?, ?)",
        (evidence_id, model, json.dumps(vector)),
    )


def test_cosine_ranking_and_rank_numbers(conn, seed_units):
    ids = seed_units(conn, "doc", ["a", "b", "c"])
    _store(conn, ids[0], [1.0, 0.0])
    _store(conn, ids[1], [0.9, 0.1])
    _store(conn, ids[2], [0.0, 1.0])
    index = SemanticIndex.load(conn)
    hits = index.search([1.0, 0.0])
    assert [h.evidence_id for h in hits] == [ids[0], ids[1], ids[2]]
    assert [h.rank for h in hits] == [1, 2, 3]
    assert hits[0].score == pytest.approx(1.0)


def test_scores_are_scale_invariant(conn, seed_units):
    ids = seed_units(conn, "doc", ["a", "b"])
    _store(conn, ids[0], [100.0, 0.0])
    _store(conn, ids[1], [0.0, 0.001])
    hits = SemanticIndex.load(conn).search([5.0, 0.0])
    assert hits[0].evidence_id == ids[0]
    assert hits[0].score == pytest.approx(1.0)


def test_no_embeddings_gives_no_index(conn, seed_units):
    seed_units(conn, "doc", ["a"])
    assert SemanticIndex.load(conn) is None


def test_mixed_models_are_refused(conn, seed_units):
    ids = seed_units(conn, "doc", ["a", "b"])
    _store(conn, ids[0], [1.0, 0.0], model="m1")
    _store(conn, ids[1], [1.0, 0.0], model="m2")
    with pytest.raises(SemanticIndexError):
        SemanticIndex.load(conn)


def test_mixed_dimensions_are_refused(conn, seed_units):
    ids = seed_units(conn, "doc", ["a", "b"])
    _store(conn, ids[0], [1.0, 0.0])
    _store(conn, ids[1], [1.0, 0.0, 0.0])
    with pytest.raises(SemanticIndexError):
        SemanticIndex.load(conn)


def test_query_dimension_mismatch_is_refused(conn, seed_units):
    ids = seed_units(conn, "doc", ["a"])
    _store(conn, ids[0], [1.0, 0.0])
    with pytest.raises(SemanticIndexError):
        SemanticIndex.load(conn).search([1.0, 0.0, 0.0])


def test_zero_query_vector_is_refused(conn, seed_units):
    ids = seed_units(conn, "doc", ["a"])
    _store(conn, ids[0], [1.0, 0.0])
    with pytest.raises(SemanticIndexError):
        SemanticIndex.load(conn).search([0.0, 0.0])


def test_after_date_filter(conn, seed_units):
    ids = seed_units(conn, "doc", [("a", "S", "2025-01-01"), ("b", "S", "2025-06-01")])
    _store(conn, ids[0], [1.0, 0.0])
    _store(conn, ids[1], [1.0, 0.0])
    hits = SemanticIndex.load(conn).search([1.0, 0.0], after_date="2025-03-01")
    assert [h.evidence_id for h in hits] == [ids[1]]


def test_embeddings_of_deleted_units_are_not_loaded(conn, seed_units):
    ids = seed_units(conn, "doc", ["a", "b"])
    _store(conn, ids[0], [1.0, 0.0])
    _store(conn, ids[1], [0.0, 1.0])
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM evidence_units WHERE evidence_id = ?", (ids[0],))
    index = SemanticIndex.load(conn)
    assert index.evidence_ids == [ids[1]]
    assert isinstance(index.matrix, np.ndarray)


def test_malformed_vector_json_is_a_semantic_index_error(conn, seed_units):
    ids = seed_units(conn, "doc", ["a"])
    conn.execute(
        "INSERT INTO evidence_embeddings (evidence_id, model_name, vector_json) "
        "VALUES (?, 'm1', 'not json')",
        (ids[0],),
    )
    with pytest.raises(SemanticIndexError):
        SemanticIndex.load(conn)
