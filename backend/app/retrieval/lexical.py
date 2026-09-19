"""Lexical retrieval: SQLite FTS5 with BM25 ranking (CLAUDE.md 9.1)."""

import sqlite3
from dataclasses import dataclass

from app.retrieval.text import fts_match_expression, topic_terms

DEFAULT_LIMIT = 15

# bm25() column weights, in FTS column order (evidence_id is unindexed).
# The unit's own words dominate; thread title and sender only break ties
# and rescue short units whose meaning lives in their thread.
_BM25_WEIGHTS = "0.0, 1.0, 0.4, 0.4"
# A second, title-heavy view: a thread subject such as "UAT sign-off - core
# replenishment" is often the best single signal that a short reply belongs to
# the question, but it is drowned out when the title only weighs 0.4.
TITLE_WEIGHTS = "0.0, 0.5, 3.0, 0.2"


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
    date_from: str | None = None,
    date_to: str | None = None,
    weights: str = _BM25_WEIGHTS,
    per_document_cap: int | None = None,
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
        f"bm25(evidence_fts, {weights}) AS score, e.document_id AS document_id "
        "FROM evidence_fts JOIN evidence_units AS e ON e.evidence_id = evidence_fts.evidence_id "
        "WHERE evidence_fts MATCH ?"
    )
    params: list[object] = [expression]
    if after_date is not None:
        sql += " AND e.event_date > ?"
        params.append(after_date)
    if date_from is not None and date_to is not None:
        sql += " AND e.event_date >= ? AND e.event_date < ?"
        params.extend([date_from, date_to])
    # bm25() is lower-is-better; evidence_id breaks ties deterministically.
    sql += " ORDER BY score, evidence_fts.evidence_id LIMIT ?"
    # A per-document cap needs headroom: rows beyond the cap are skipped.
    params.append(limit * 8 if per_document_cap else limit)

    rows = conn.execute(sql, params).fetchall()
    if per_document_cap:
        kept, per_doc = [], {}
        for row in rows:
            if per_doc.get(row["document_id"], 0) >= per_document_cap:
                continue
            per_doc[row["document_id"]] = per_doc.get(row["document_id"], 0) + 1
            kept.append(row)
        rows = kept[:limit]
    return [
        Hit(evidence_id=row["evidence_id"], rank=position, score=-float(row["score"]))
        for position, row in enumerate(rows, start=1)
    ]
