"""Lexical retrieval: SQLite FTS5 with BM25 ranking (CLAUDE.md 9.1)."""

import sqlite3
from dataclasses import dataclass

from app.retrieval.text import fts_match_expression, topic_terms

DEFAULT_LIMIT = 15

# bm25() column weights, in FTS column order (evidence_id is unindexed).
# The unit's own words dominate; thread title and sender only break ties
# and rescue short units whose meaning lives in their thread.
_BM25_WEIGHTS = "0.0, 1.0, 0.4, 0.4"


@dataclass(frozen=True)
class Hit:
    evidence_id: str
    rank: int  # 1-based position within its own ranked list
    score: float  # source-specific; only comparable within one list


def search(
    conn: sqlite3.Connection,
    query: str | None = None,
    *,
    terms: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    after_date: str | None = None,
) -> list[Hit]:
    """Top BM25 matches for a question or an explicit term list.

    Joining evidence_units means an FTS row whose unit no longer exists can
    never be returned. ``after_date`` keeps only strictly later evidence,
    which is how the temporal sweep reuses this same retrieval path.
    """
    if terms is None:
        terms = topic_terms(query or "")
    expression = fts_match_expression(terms)
    if expression is None:
        return []

    sql = (
        f"SELECT evidence_fts.evidence_id AS evidence_id, "
        f"bm25(evidence_fts, {_BM25_WEIGHTS}) AS score "
        "FROM evidence_fts JOIN evidence_units AS e ON e.evidence_id = evidence_fts.evidence_id "
        "WHERE evidence_fts MATCH ?"
    )
    params: list[object] = [expression]
    if after_date is not None:
        sql += " AND e.event_date > ?"
        params.append(after_date)
    # bm25() is lower-is-better; evidence_id breaks ties deterministically.
    sql += " ORDER BY score, evidence_fts.evidence_id LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        Hit(evidence_id=row["evidence_id"], rank=position, score=-float(row["score"]))
        for position, row in enumerate(rows, start=1)
    ]
