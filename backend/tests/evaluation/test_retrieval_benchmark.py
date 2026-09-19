"""Offline retrieval regression guard over the real archive.

Runs lexical-only (no network) against a freshly ingested in-memory copy
of data/source/, so it is read-only with respect to the repository. The
hybrid (semantic) figures come from `scripts/benchmark.py`, which needs
the organizer embedding service; these floors are set at the measured
lexical-only result so a ranking regression fails loudly.
"""

from pathlib import Path

import pytest

from app.ingestion.service import ingest
from app.retrieval.benchmark import evaluate, load_topics
from app.retrieval.records import hydrate
from app.retrieval.service import RetrievalService

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_DIR = _REPO_ROOT / "data" / "source"
_TOPICS = Path(__file__).parent / "retrieval_topics.json"

pytestmark = pytest.mark.skipif(not _SOURCE_DIR.is_dir(), reason="data/source/ not present")


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    import sqlite3

    from app.db import migrations

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrations.initialize(conn)
    ingest(conn, _SOURCE_DIR, embedding_provider=None)
    yield conn
    conn.close()


def test_at_least_ten_topics_are_defined():
    assert len(load_topics(_TOPICS)) >= 10


def test_every_topic_criterion_matches_real_evidence(loaded):
    # Guards the fixture itself: a criterion that matches nothing would
    # make a topic silently unwinnable.
    rows = loaded.execute("SELECT document_id, raw_text FROM evidence_units").fetchall()
    for topic in load_topics(_TOPICS):
        for criterion in topic.criteria:
            assert any(
                r["document_id"].startswith(criterion.document_prefix)
                and (criterion.pattern is None or criterion.pattern.search(r["raw_text"]))
                for r in rows
            ), f"{topic.topic_id}: criterion matches no evidence"


def test_lexical_only_benchmark_floor(loaded):
    results = evaluate(RetrievalService(loaded, None), load_topics(_TOPICS))
    passed = sum(r.passed for r in results)
    visible = sum(r.relevant_in_visible_set for r in results)
    assert passed >= 8, f"only {passed}/{len(results)} topics have a relevant unit in the top 5"
    assert visible >= 11, f"only {visible}/{len(results)} topics surface relevant evidence"


def test_retrieval_invariants_hold_across_all_topics(loaded):
    service = RetrievalService(loaded, None)
    for topic in load_topics(_TOPICS):
        result = service.retrieve(topic.query, temporal_sweep=topic.temporal)
        ids = result.visible_evidence_ids
        assert len(ids) == len(set(ids))
        # Every visible id is a real, hydratable unit.
        assert {r.evidence_id for r in hydrate(loaded, ids)} == set(ids)
        assert len(result.fused) <= 15
        # Neighbour expansion stays bounded: nowhere near the whole archive.
        assert len(ids) < 250


def test_bakery_temporal_sweep_finds_later_evidence(loaded):
    result = RetrievalService(loaded, None).retrieve("Is bakery still inside the fresh workstream?")
    assert result.is_temporal and result.temporal is not None
    dates = [result.records[h.evidence_id].event_date for h in result.temporal.hits]
    assert dates and all(d > result.temporal.after_date for d in dates)
