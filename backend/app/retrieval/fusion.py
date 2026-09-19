"""Deterministic Reciprocal Rank Fusion (CLAUDE.md 9.3).

RRF combines ranks, not scores, so BM25 and cosine similarity never need
to be put on one scale -- which is why no learned reranker is needed.
"""

from dataclasses import dataclass, field

from app.retrieval.lexical import Hit

# The conventional constant from the original RRF paper; fixed once so
# retrieval quality is not tuned against the benchmark.
RRF_K = 60


@dataclass(frozen=True)
class FusedHit:
    evidence_id: str
    rank: int
    score: float
    # Which lists contributed and at what rank, kept so the ranking is
    # explainable in a trace ("lexical#2, semantic#7").
    sources: dict[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[Hit]],
    *,
    k: int = RRF_K,
    limit: int | None = None,
    weights: dict[str, float] | None = None,
) -> list[FusedHit]:
    scores: dict[str, float] = {}
    sources: dict[str, dict[str, int]] = {}
    for name, hits in ranked_lists.items():
        for hit in hits:
            weight = (weights or {}).get(name, 1.0)
            scores[hit.evidence_id] = scores.get(hit.evidence_id, 0.0) + weight / (k + hit.rank)
            sources.setdefault(hit.evidence_id, {})[name] = hit.rank

    ordered = sorted(scores, key=lambda evidence_id: (-scores[evidence_id], evidence_id))
    if limit is not None:
        ordered = ordered[:limit]
    return [
        FusedHit(
            evidence_id=evidence_id,
            rank=position,
            score=scores[evidence_id],
            sources=sources[evidence_id],
        )
        for position, evidence_id in enumerate(ordered, start=1)
    ]
