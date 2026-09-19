"""Later-evidence sweep (CLAUDE.md 9.5).

For current-state, decision, and supersession questions, an initial
top-k can be dominated by the original discussion while the outcome sits
later in the archive. The sweep re-runs the same lexical and semantic
retrieval restricted to evidence dated after the discussion.

This is a retrieval operation only. It surfaces later evidence; whether
that evidence changes the answer is for the reasoner and the Skeptic to
decide -- newer is never assumed to be truer.
"""

import sqlite3
from dataclasses import dataclass

from app.retrieval import lexical
from app.retrieval.fusion import FusedHit, reciprocal_rank_fusion
from app.retrieval.semantic import SemanticIndex

SWEEP_LIMIT = 10


@dataclass(frozen=True)
class TemporalSweep:
    after_date: str
    # Fused later evidence, best match first.
    hits: list[FusedHit]
    # The subset the initial retrieval had not already surfaced.
    new_evidence_ids: list[str]


def earliest_date(conn: sqlite3.Connection, evidence_ids: list[str]) -> str | None:
    if not evidence_ids:
        return None
    marks = ",".join("?" * len(evidence_ids))
    row = conn.execute(
        f"SELECT MIN(event_date) AS d FROM evidence_units WHERE evidence_id IN ({marks})",
        evidence_ids,
    ).fetchone()
    return row["d"]


def later_evidence_sweep(
    conn: sqlite3.Connection,
    *,
    terms: list[str],
    after_date: str,
    already_seen: set[str],
    index: SemanticIndex | None = None,
    query_vector: list[float] | None = None,
    limit: int = SWEEP_LIMIT,
) -> TemporalSweep:
    ranked = {"lexical": lexical.search(conn, terms=terms, limit=limit, after_date=after_date)}
    if index is not None and query_vector is not None:
        ranked["semantic"] = index.search(query_vector, limit=limit, after_date=after_date)

    fused = reciprocal_rank_fusion(ranked, limit=limit)
    return TemporalSweep(
        after_date=after_date,
        hits=fused,
        new_evidence_ids=[h.evidence_id for h in fused if h.evidence_id not in already_seen],
    )
