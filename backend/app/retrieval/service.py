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
from app.retrieval.text import (
    date_range_hint,
    is_enumerative_query,
    is_temporal_query,
    topic_terms,
)

_LOGGER = logging.getLogger(__name__)

FUSED_LIMIT = 15
# Only the strongest hits get neighbour expansion; expanding all of them
# would drift toward sending the whole archive to the reasoner.
CONTEXT_SEED_COUNT = 8
# Enumerative questions ("every figure", "how did it change") need coverage,
# not just the best few matches. The reasoner's prompt already caps total
# units, so widening here stays bounded.
WIDE_FUSED_LIMIT = 30
WIDE_CONTEXT_SEED_COUNT = 12
_WIDE_PER_DOCUMENT = 2
_SWEEP_ANCHOR_COUNT = 5
_TITLE_PER_DOCUMENT = 4
_LIST_WEIGHTS = {"title": 1.5}


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
    wide: bool = False
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
            "wide": self.wide,
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

    def retrieve(
        self, query: str, *, temporal_sweep: bool | None = None, wide: bool | None = None
    ) -> RetrievalResult:
        wide = is_enumerative_query(query) if wide is None else wide
        limit = max(self._fused_limit, WIDE_FUSED_LIMIT) if wide else self._fused_limit
        terms = topic_terms(query)
        warnings: list[str] = []
        hint = date_range_hint(query)
        if hint:
            # "September 2024" is a filter, not a word to match in the text.
            terms = [t for t in terms if t not in hint[2]]

        lexical_hits = lexical.search(self._conn, terms=terms, limit=limit)
        query_vector, semantic_hits = self._semantic(query, warnings, limit=limit)
        semantic_used = query_vector is not None

        ranked = {"lexical": lexical_hits}
        # Thread-title view, at most a few units per document so one long
        # meeting with a matching title cannot flood the list.
        ranked["title"] = lexical.search(
            self._conn,
            terms=terms,
            limit=limit,
            weights=lexical.TITLE_WEIGHTS,
            per_document_cap=_TITLE_PER_DOCUMENT,
        )
        if wide:
            # A set spread over documents: without a cap, one long meeting that
            # repeats the topic fills the list and the emails and reports that
            # state the same figure never make it in.
            ranked["spread"] = lexical.search(
                self._conn, terms=terms, limit=limit, per_document_cap=_WIDE_PER_DOCUMENT
            )
        if semantic_used:
            ranked["semantic"] = semantic_hits
        if hint:
            # An extra list restricted to the named period. It adds candidates;
            # evidence outside the window still competes in the lists above.
            ranked["dated_lexical"] = lexical.search(
                self._conn, terms=terms, limit=limit, date_from=hint[0], date_to=hint[1]
            )
            if semantic_used and self._index is not None:
                ranked["dated_semantic"] = self._index.search(
                    query_vector, limit=limit, date_from=hint[0], date_to=hint[1]
                )
        fused = reciprocal_rank_fusion(ranked, limit=limit, weights=_LIST_WEIGHTS)

        # A wide question is about change or coverage, so the later-evidence
        # sweep runs for it by default (still retrieval, never a verdict).
        if temporal_sweep is None:
            needs_sweep = wide or is_temporal_query(query)
        else:
            needs_sweep = temporal_sweep
        sweep = self._sweep(terms, fused, query_vector) if needs_sweep else None

        seeds = WIDE_CONTEXT_SEED_COUNT if wide else CONTEXT_SEED_COUNT
        windows = context.expand(self._conn, [h.evidence_id for h in fused[:seeds]])

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
            wide=wide,
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

    def later_evidence(
        self, terms: list[str], after_date: str, *, limit: int = FUSED_LIMIT
    ) -> RetrievalResult:
        """Lexical retrieval for ``terms`` restricted to evidence strictly after
        ``after_date``, packaged like any retrieval (context windows, hydrated
        records). Used for the post-answer sweep (CLAUDE.md 9.5): the terms are
        the answer's own topic, so a later change of state surfaces even when the
        question never used those words."""
        hits = lexical.search(self._conn, terms=terms, limit=limit, after_date=after_date)
        fused = reciprocal_rank_fusion({"later": hits}, limit=limit)
        windows = context.expand(self._conn, [h.evidence_id for h in fused[:CONTEXT_SEED_COUNT]])
        wanted = list(
            dict.fromkeys([h.evidence_id for h in fused] + [i for w in windows for i in w.unit_ids])
        )
        return RetrievalResult(
            query=" ".join(terms),
            terms=terms,
            lexical_hits=hits,
            semantic_hits=[],
            fused=fused,
            windows=windows,
            temporal=None,
            is_temporal=True,
            semantic_used=False,
            records={r.evidence_id: r for r in hydrate(self._conn, wanted)},
        )

    def coverage_evidence(
        self, terms: list[str], *, limit: int = WIDE_FUSED_LIMIT
    ) -> RetrievalResult:
        """Lexical retrieval for ``terms`` across the whole archive, at most a
        couple of units per document. For enumerative questions: the terms come
        from the reasoner's own first answer, so figures and statements the
        question never named (a table row, a follow-up email) can be reached,
        and one repetitive meeting cannot crowd out every other document."""
        hits = lexical.search(
            self._conn, terms=terms, limit=limit, per_document_cap=_WIDE_PER_DOCUMENT
        )
        fused = reciprocal_rank_fusion({"coverage": hits}, limit=limit)
        windows = context.expand(self._conn, [h.evidence_id for h in fused[:CONTEXT_SEED_COUNT]])
        wanted = list(
            dict.fromkeys([h.evidence_id for h in fused] + [i for w in windows for i in w.unit_ids])
        )
        return RetrievalResult(
            query=" ".join(terms),
            terms=terms,
            lexical_hits=hits,
            semantic_hits=[],
            fused=fused,
            windows=windows,
            temporal=None,
            is_temporal=False,
            semantic_used=False,
            wide=True,
            records={r.evidence_id: r for r in hydrate(self._conn, wanted)},
        )

    def _semantic(
        self, query: str, warnings: list[str], *, limit: int | None = None
    ) -> tuple[list[float] | None, list[Hit]]:
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
            return vector, self._index.search(vector, limit=limit or self._fused_limit)
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
