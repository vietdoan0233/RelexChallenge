"""The union of evidence a reasoning step may see.

The first retrieval, the Skeptic's counter-retrievals, and the temporal
sweeps all contribute. Everything in ``visible_ids`` is what the validator
later accepts as a citable id (CLAUDE.md 15), so a claim can only ever cite
evidence some model was actually shown.
"""

from dataclasses import dataclass, field

from app.retrieval.records import EvidenceRecord
from app.retrieval.service import RetrievalResult


@dataclass
class EvidenceSet:
    records: dict[str, EvidenceRecord] = field(default_factory=dict)
    hit_ids: set[str] = field(default_factory=set)
    later_ids: set[str] = field(default_factory=set)
    visible_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_results(cls, *results: RetrievalResult) -> "EvidenceSet":
        merged = cls()
        for result in results:
            merged.add(result)
        return merged

    def add(
        self, result: RetrievalResult, *, top_hits: int | None = None, top_later: int | None = None
    ) -> list[str]:
        """Merge a retrieval result; returns ids not previously visible.

        ``top_hits`` / ``top_later`` keep only the strongest matches, their
        context windows, and the strongest later evidence. The Skeptic uses
        this so a broad counter-search cannot bury the evidence that matters
        or blow the prompt budget.
        """
        fused = result.fused if top_hits is None else result.fused[:top_hits]
        later = result.temporal.hits if result.temporal else []
        later = later if top_later is None else later[:top_later]
        if top_hits is None and top_later is None:
            wanted = list(result.visible_evidence_ids)
        else:
            anchors = {h.evidence_id for h in fused}
            wanted = [h.evidence_id for h in fused]
            wanted += [i for w in result.windows if w.anchor_id in anchors for i in w.unit_ids]
            wanted += [h.evidence_id for h in later]
            wanted = [i for i in dict.fromkeys(wanted) if i in result.records]
        seen = set(self.visible_ids)
        new = [i for i in wanted if i not in seen]
        for i in wanted:
            self.records[i] = result.records[i]
        self.hit_ids.update(h.evidence_id for h in fused)
        self.later_ids.update(h.evidence_id for h in later)
        self.visible_ids.extend(new)
        return new
