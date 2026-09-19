"""Deterministic risk routing (CLAUDE.md 12).

A small, explainable ruleset -- not a numeric score. The model's
self-reported confidence is one *input* that can only escalate scrutiny,
never a reason to skip it. Any trigger sends the Case through the
Skeptic; each trigger is named so the routing can be shown to a judge.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.core.enums import CaseStatus, Confidence, Stance
from app.reasoning.evidence import EvidenceSet
from app.retrieval.service import RetrievalResult
from app.schemas.reasoning import PrimaryOutput

# Question language that asks for a judgement about agreement, authority,
# fulfilment, or current state -- the areas where a plausible answer is most
# likely to be wrong.
_QUERY_TRIGGERS = (
    (r"\bagree[ds]?\b|\bagreement\b", "asks what was agreed"),
    (r"\bdecid\w*|\bdecision\b", "asks what was decided"),
    (r"\bapprov\w*|\bauthori[sz]\w*", "asks about approval or authority"),
    (r"\bsign(?:ed)?[- ]?off\b|\bsigned\b", "asks about sign-off"),
    (r"\bcommit\w*", "asks about a commitment"),
    (r"\bfulfil\w*|\bnever done\b|\bwas it done\b|\bdelivered\b", "asks whether it was fulfilled"),
    (
        r"\bcurrent\w*|\bstill\b|\bnow\b|\blatest\b|\bfinal\w*|\bultimately\b",
        "asks about current state",
    ),
    (
        r"\bsupersed\w*|\bno longer\b|\bover time\b|\bchanged?\b",
        "asks about supersession or change",
    ),
    (r"\bassum\w*|\bproposed\b|\bwho (?:proposed|suggested)\b", "asks assumption vs decision"),
    (r"\bwho\b", "asks who"),
)

# A claim that states a specific value is exactly where a second, different
# value elsewhere in the archive would matter, so it always gets the Skeptic's
# conflicting-value search.
_SPECIFIC_VALUE = re.compile(
    r"\d[\d,.]*\s*(?:%|percent|months?|weeks?|days?|years?|hours?|tonnes?|stores?|articles?)"
    r"|\b(?:\d[\d,.]*)\b|\b(?:twelve|eighteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\b",
    re.IGNORECASE,
)

# Support spread wider than this is treated as evidence "spanning materially
# different dates".
_DATE_SPREAD_DAYS = 90
_AMBIGUOUS_STANCES = {Stance.PROPOSAL, Stance.ASSUMPTION, Stance.UNCERTAIN, Stance.SUPERSEDED}


@dataclass
class RiskAssessment:
    triggers: list[str] = field(default_factory=list)

    @property
    def deep_check(self) -> bool:
        return bool(self.triggers)

    @property
    def level(self) -> str:
        if not self.triggers:
            return "LOW"
        return "HIGH" if len(self.triggers) >= 3 else "MEDIUM"


def assess(
    query: str,
    output: PrimaryOutput,
    retrieval: RetrievalResult,
    evidence: EvidenceSet | None = None,
) -> RiskAssessment:
    triggers: list[str] = []
    lowered = query.lower()
    for pattern, reason in _QUERY_TRIGGERS:
        if re.search(pattern, lowered):
            triggers.append(f"query: {reason}")

    claims = output.claims
    records = (evidence or EvidenceSet.from_results(retrieval)).records

    if output.status in (CaseStatus.CONFLICTING_EVIDENCE, CaseStatus.PARTIALLY_SUPPORTED):
        triggers.append(f"model status is {output.status}")
    if any(c.conflicting_evidence_ids for c in claims):
        triggers.append("conflicting evidence was cited")
    if any(c.stance in _AMBIGUOUS_STANCES for c in claims):
        triggers.append("stance is ambiguous (proposal, assumption, uncertain, or superseded)")
    if any(c.confidence != Confidence.HIGH for c in claims):
        triggers.append("a claim has medium or low confidence")
    if any(
        len(set(c.supporting_evidence_ids)) == 1 for c in claims if c.stance != Stance.UNCERTAIN
    ):
        triggers.append("a claim rests on a single supporting unit")
    if any(_SPECIFIC_VALUE.search(c.claim_text) for c in claims):
        triggers.append("a claim states a specific value that another source could contradict")
    if retrieval.temporal and retrieval.temporal.hits:
        triggers.append("later relevant evidence exists")

    for claim in claims:
        cited = [records[i] for i in claim.supporting_evidence_ids if i in records]
        if _date_spread_days([r.event_date for r in cited]) > _DATE_SPREAD_DAYS:
            triggers.append("supporting evidence spans materially different dates")
            break
    types = {
        r.document_type for c in claims for i in c.supporting_evidence_ids if (r := records.get(i))
    }
    conflict_types = {
        r.document_type for c in claims for i in c.conflicting_evidence_ids if (r := records.get(i))
    }
    if conflict_types and types and conflict_types != types:
        triggers.append("source types disagree")
    if "REPORT" in (types | conflict_types) and len(types | conflict_types) > 1:
        triggers.append("a status report is set against other evidence")
    if not claims:
        triggers.append("no claim was produced")

    return RiskAssessment(triggers=list(dict.fromkeys(triggers)))


def _date_spread_days(dates: list[str | None]) -> int:
    parsed = []
    for value in dates:
        if not value:
            continue
        try:
            parsed.append(date.fromisoformat(value[:10]))
        except ValueError:
            continue
    return (max(parsed) - min(parsed)).days if len(parsed) >= 2 else 0
