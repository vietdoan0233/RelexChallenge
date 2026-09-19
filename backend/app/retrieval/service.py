"""Hybrid retrieval orchestration (CLAUDE.md 9).

    question -> lexical + semantic -> RRF -> neighbour context
                                   -> (temporal questions) later-evidence sweep

The service never sends the archive anywhere and never drops to a model
for ranking. If the embedding provider is missing or fails it degrades to
lexical-only and says so in ``warnings`` -- a visible degradation, not a
silent one.
"""

import logging
import sqlite3
from dataclasses import dataclass, field

from app.ingestion.embeddings import EmbeddingProvider
from app.retrieval import context, lexical, temporal
from app.retrieval.fusion import FusedHit, reciprocal_rank_fusion
from app.retrieval.lexical import Hit
from app.retrieval.records import EvidenceRecord, hydrate
from app.retrieval.semantic import SemanticIndex, SemanticIndexError
from app.retrieval.temporal import TemporalSweep
from app.retrieval.text import is_temporal_query, topic_terms

_LOGGER = logging.getLogger(__name__)

FUSED_LIMIT = 15
# Only the strongest hits get neighbour expansion; expanding all of them
# would drift toward sending the whole archive to the reasoner.
CONTEXT_SEED_COUNT = 8
_SWEEP_ANCHOR_COUNT = 5


@dataclass
class RetrievalResult:
    query: str
    terms: list[str]
    lexical_hits: list[Hit]
    semantic_hits: list[Hit]
    fused: list[FusedHit]
    windows: list[context.ContextWindow]
    temporal: TemporalSweep | None
    is_temporal: bool
    semantic_used: bool
    warnings: list[str] = field(default_factory=list)
    records: dict[str, EvidenceRecord] = field(default_factory=dict)

    @property
    def ranked_ids(self) -> list[str]:
        return [h.evidence_id for h in self.fused]

    @property
    def visible_evidence_ids(self) -> list[str]:
        """Every id a reasoner would be shown: hits, their context, and
        later evidence. The validator later requires cited ids to be in
        this set (CLAUDE.md 15)."""
        ids: dict[str, None] = dict.fromkeys(self.ranked_ids)
        for window in self.windows:
            ids.update(dict.fromkeys(window.unit_ids))
        if self.temporal:
            ids.update(dict.fromkeys(h.evidence_id for h in self.temporal.hits))
        return [i for i in ids if i in self.records]

    def trace(self) -> dict:
        """Ids and counts only -- never evidence text (CLAUDE.md 28)."""
        return {
            "terms": self.terms,
            "lexical_ids": [h.evidence_id for h in self.lexical_hits],
            "semantic_ids": [h.evidence_id for h in self.semantic_hits],
            "fused_ids": self.ranked_ids,
            "context_ids": sorted({i for w in self.windows for i in w.context_ids}),
            "temporal": bool(self.temporal),
            "temporal_after": self.temporal.after_date if self.temporal else None,
            "temporal_new_ids": self.temporal.new_evidence_ids if self.temporal else [],
            "semantic_used": self.semantic_used,
            "warnings": self.warnings,
        }


class RetrievalService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        provider: EmbeddingProvider | None = None,
        *,
        fused_limit: int = FUSED_LIMIT,
        index: SemanticIndex | None = None,
    ) -> None:
        """``index`` lets a server share one loaded matrix across per-request
        connections (SQLite connections are not shared across threads)."""
        self._conn = conn
        self._provider = provider
        self._fused_limit = fused_limit
        self._index: SemanticIndex | None = index
        self._index_error: str | None = None
        if index is None:
            self.refresh()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def refresh(self) -> None:
        """Reload embeddings from the database. Must be called after any
        deletion/rebuild so a cached matrix can never resurrect removed
        evidence."""
        try:
            self._index = SemanticIndex.load(self._conn)
            self._index_error = None
        except SemanticIndexError as exc:
            self._index = None
            self._index_error = str(exc)

    def retrieve(self, query: str, *, temporal_sweep: bool | None = None) -> RetrievalResult:
        terms = topic_terms(query)
        warnings: list[str] = []

        lexical_hits = lexical.search(self._conn, terms=terms, limit=self._fused_limit)
        query_vector, semantic_hits = self._semantic(query, warnings)
        semantic_used = query_vector is not None

        ranked = {"lexical": lexical_hits}
        if semantic_used:
            ranked["semantic"] = semantic_hits
        fused = reciprocal_rank_fusion(ranked, limit=self._fused_limit)

        needs_sweep = is_temporal_query(query) if temporal_sweep is None else temporal_sweep
        sweep = self._sweep(terms, fused, query_vector) if needs_sweep else None

        windows = context.expand(self._conn, [h.evidence_id for h in fused[:CONTEXT_SEED_COUNT]])

        result = RetrievalResult(
            query=query,
            terms=terms,
            lexical_hits=lexical_hits,
            semantic_hits=semantic_hits,
            fused=fused,
            windows=windows,
            temporal=sweep,
            is_temporal=needs_sweep,
            semantic_used=semantic_used,
            warnings=warnings,
        )
        wanted = list(
            dict.fromkeys(
                result.ranked_ids
                + [i for w in windows for i in w.unit_ids]
                + ([h.evidence_id for h in sweep.hits] if sweep else [])
            )
        )
        result.records = {r.evidence_id: r for r in hydrate(self._conn, wanted)}
        # Drop any id that no longer hydrates (stale index after a deletion).
        result.fused = [h for h in result.fused if h.evidence_id in result.records]
        return result

    def _semantic(self, query: str, warnings: list[str]) -> tuple[list[float] | None, list[Hit]]:
        if self._provider is None:
            warnings.append("semantic retrieval unavailable: no embedding provider configured")
            return None, []
        if self._index is None:
            reason = self._index_error or "no stored embeddings"
            warnings.append(f"semantic retrieval unavailable: {reason}")
            return None, []
        if self._provider.model_name != self._index.model_name:
            warnings.append(
                "semantic retrieval unavailable: query model differs from stored embeddings"
            )
            return None, []
        try:
            vector = self._provider.embed_batch([query])[0]
            return vector, self._index.search(vector, limit=self._fused_limit)
        except Exception as exc:
            # Type only: exception text can echo request content.
            _LOGGER.warning("query embedding failed error_type=%s", type(exc).__name__)
            warnings.append(f"semantic retrieval unavailable: {type(exc).__name__}")
            return None, []

    def _sweep(
        self, terms: list[str], fused: list[FusedHit], query_vector: list[float] | None
    ) -> TemporalSweep | None:
        anchors = [h.evidence_id for h in fused[:_SWEEP_ANCHOR_COUNT]]
        after = temporal.earliest_date(self._conn, anchors)
        if after is None or not terms:
            return None
        return temporal.later_evidence_sweep(
            self._conn,
            terms=terms,
            after_date=after,
            already_seen={h.evidence_id for h in fused},
            index=self._index,
            query_vector=query_vector,
        )
