"""Retrieval benchmark harness (CLAUDE.md 24, Phase 2 exit).

Topics are an evaluation fixture, not reasoning input: each names the
evidence a good retriever should surface, so a ranking regression shows
up as a number. Relevance is judged on database-hydrated text, so the
fixture survives Evidence-ID changes and never hardcodes an answer.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.retrieval.records import EvidenceRecord, hydrate
from app.retrieval.service import RetrievalService

PASS_RANK = 5


@dataclass(frozen=True)
class Criterion:
    document_prefix: str
    pattern: re.Pattern[str] | None

    def matches(self, record: EvidenceRecord) -> bool:
        if not record.document_id.startswith(self.document_prefix):
            return False
        return self.pattern is None or bool(self.pattern.search(record.raw_text))


@dataclass(frozen=True)
class Topic:
    topic_id: str
    query: str
    criteria: tuple[Criterion, ...]
    temporal: bool | None = None

    def is_relevant(self, record: EvidenceRecord) -> bool:
        return any(c.matches(record) for c in self.criteria)


@dataclass(frozen=True)
class TopicResult:
    topic_id: str
    fused_rank: int | None
    lexical_rank: int | None
    semantic_rank: int | None
    relevant_in_visible_set: bool
    semantic_used: bool

    @property
    def passed(self) -> bool:
        return self.fused_rank is not None and self.fused_rank <= PASS_RANK

    @property
    def in_top_10(self) -> bool:
        return self.fused_rank is not None and self.fused_rank <= 10


def load_topics(path: Path) -> list[Topic]:
    topics = []
    for raw in json.loads(path.read_text(encoding="utf-8")):
        criteria = tuple(
            Criterion(c["document"], re.compile(c["pattern"]) if c.get("pattern") else None)
            for c in raw["relevant"]
        )
        topics.append(Topic(raw["id"], raw["query"], criteria, raw.get("temporal")))
    return topics


def evaluate(service: RetrievalService, topics: list[Topic]) -> list[TopicResult]:
    results = []
    for topic in topics:
        outcome = service.retrieve(topic.query, temporal_sweep=topic.temporal)
        results.append(
            TopicResult(
                topic_id=topic.topic_id,
                fused_rank=_first_relevant_rank(service, topic, outcome.ranked_ids),
                lexical_rank=_first_relevant_rank(
                    service, topic, [h.evidence_id for h in outcome.lexical_hits]
                ),
                semantic_rank=_first_relevant_rank(
                    service, topic, [h.evidence_id for h in outcome.semantic_hits]
                ),
                relevant_in_visible_set=any(
                    topic.is_relevant(outcome.records[i]) for i in outcome.visible_evidence_ids
                ),
                semantic_used=outcome.semantic_used,
            )
        )
    return results


def _first_relevant_rank(service: RetrievalService, topic: Topic, ids: list[str]) -> int | None:
    records = {r.evidence_id: r for r in hydrate(service.conn, ids)}
    for position, evidence_id in enumerate(ids, start=1):
        record = records.get(evidence_id)
        if record is not None and topic.is_relevant(record):
            return position
    return None
