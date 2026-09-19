"""Conditional Skeptic with real counter-retrieval (CLAUDE.md 13).

The Skeptic's job is not a second opinion. It looks for evidence that
would make the candidate answer wrong, and it must actually retrieve:
step 1 plans up to two counter-search bundles (direct contradiction,
alternative/replacement state, later implementation), step 2 runs them
through the same RetrievalService, step 3 inspects only what came back.
A prompt-only critique with no new retrieval would not count.
"""

import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.core.errors import AnalysisUnavailableError
from app.reasoning.evidence import EvidenceSet
from app.reasoning.llm import LLMClient
from app.reasoning.prompts import format_evidence_set
from app.retrieval.service import RetrievalService
from app.schemas.reasoning import PrimaryOutput, SkepticPlan, SkepticVerdict

_LOGGER = logging.getLogger(__name__)

# MVP latency control: an increase needs evaluation evidence (CLAUDE.md 13.1).
MAX_BUNDLES = 2
MAX_QUERIES_PER_BUNDLE = 3
# Per counter-query: enough to find a replacement or reversal, small enough
# to keep the verdict prompt inside its evidence budget.
_COUNTER_TOP_HITS = 5
_COUNTER_TOP_LATER = 3
_TEMPORAL_STRATEGIES = {"ALTERNATIVE_STATE", "LATER_IMPLEMENTATION"}

PLAN_SYSTEM = """[ROLE:SKEPTIC_PLAN]
You are the Skeptic of an evidence-first organizational memory auditor. You are NOT giving a second opinion and you do NOT restate the candidate answer. Your only job: find evidence that would make the candidate answer WRONG.

1. Identify the weakest, highest-impact claim.
2. Propose at most 2 counter-search bundles, each using a DIFFERENT strategy:
   - DIRECT_CONTRADICTION: explicit rejection, disagreement, cancellation, reversal, or non-approval.
   - ALTERNATIVE_STATE: later adoption of a competing technology, scope, plan, owner or implementation that would indirectly falsify the claim. Do not only negate the claim: if it says X was chosen, search the same domain for the replacement, migration, or alternative that could have superseded X.
   - LATER_IMPLEMENTATION: what the organization actually implemented, shipped, escalated, deferred or worked around after the supposed decision.
3. Each bundle has 1-3 SHORT search queries. Use vocabulary the archive is likely to use that DIFFERS from the candidate's own wording.
Also consider: lack of confirmation, proposal-only language, operational behaviour contradicting a status report, later implementation inconsistent with a stated agreement, a narrower scope than claimed, a superseding decision worded differently.

Reply with ONE JSON object only:
{"weakest_claim": string, "why_it_could_be_wrong": string,
 "bundles": [{"strategy": "DIRECT_CONTRADICTION"|"ALTERNATIVE_STATE"|"LATER_IMPLEMENTATION", "queries": [string]}]}"""

VERDICT_SYSTEM = """[ROLE:SKEPTIC_VERDICT]
You are the Skeptic. Below are the question, the candidate claims, the evidence the analyst already used, and NEW evidence (marked with '!') found by targeted counter-search. Decide whether any evidence makes the candidate answer wrong, overstated, out of date, or too broad.

Rules: cite evidence ONLY by the evidence_id in square brackets; never invent one; never write your own speaker, date or quotation. A unit marked TRUNCATED is incomplete - do not complete it. Newer is not automatically truer: distinguish superseded/stale from false/unverified. If nothing real contradicts the candidate answer, return an empty objections list - do not invent objections. Put evidence ids only in the evidence_ids fields, not in prose.

Reply with ONE JSON object only:
{"objections": [{"text": string, "severity": "HIGH"|"MEDIUM"|"LOW", "evidence_ids": [string]}]}"""


@dataclass
class SkepticResult:
    plan: SkepticPlan | None = None
    queries_run: int = 0
    new_evidence_ids: list[str] = field(default_factory=list)
    objections: list = field(default_factory=list)
    evidence: EvidenceSet | None = None

    @property
    def has_findings(self) -> bool:
        return bool(self.objections)


def counter_retrieve(
    llm: LLMClient,
    retrieval_service: RetrievalService,
    query: str,
    output: PrimaryOutput,
    evidence: EvidenceSet,
) -> SkepticResult:
    """Steps 1-2: plan up to two counter-search bundles and actually retrieve.

    Split out so other reviewers (the Reconsideration Radar) can reuse real
    counter-retrieval with their own verdict step.
    """
    plan = _plan(llm, query, output, evidence)
    result = SkepticResult(plan=plan, evidence=evidence)

    new_ids: list[str] = []
    for bundle in plan.bundles[:MAX_BUNDLES]:
        temporal = bundle.strategy.upper() in _TEMPORAL_STRATEGIES
        for text in [q.strip() for q in bundle.queries if q.strip()][:MAX_QUERIES_PER_BUNDLE]:
            found = retrieval_service.retrieve(text, temporal_sweep=temporal)
            new_ids.extend(
                evidence.add(found, top_hits=_COUNTER_TOP_HITS, top_later=_COUNTER_TOP_LATER)
            )
            result.queries_run += 1
    result.new_evidence_ids = list(dict.fromkeys(new_ids))
    return result


def run(
    llm: LLMClient,
    retrieval_service: RetrievalService,
    query: str,
    output: PrimaryOutput,
    evidence: EvidenceSet,
) -> SkepticResult:
    result = counter_retrieve(llm, retrieval_service, query, output, evidence)

    # No new evidence means there is nothing further to inspect; the
    # candidate stands as far as this search could tell.
    if not result.new_evidence_ids:
        return result

    result.objections = _verdict(llm, query, output, evidence, set(result.new_evidence_ids))
    return result


def _plan(llm: LLMClient, query: str, output: PrimaryOutput, evidence: EvidenceSet) -> SkepticPlan:
    user = (
        f"QUESTION\n{query}\n\nCANDIDATE CLAIMS\n{_claims_json(output)}\n\n"
        f"EVIDENCE USED\n{format_evidence_set(evidence)}"
    )
    return _parse(llm.complete_json(system=PLAN_SYSTEM, user=user), SkepticPlan)


def _verdict(
    llm: LLMClient, query: str, output: PrimaryOutput, evidence: EvidenceSet, new_ids: set[str]
) -> list:
    user = (
        f"QUESTION\n{query}\n\nCANDIDATE CLAIMS\n{_claims_json(output)}\n\n"
        f"EVIDENCE (new counter-search results marked '!')\n"
        f"{format_evidence_set(evidence, new_ids=new_ids)}"
    )
    return _parse(llm.complete_json(system=VERDICT_SYSTEM, user=user), SkepticVerdict).objections


def _claims_json(output: PrimaryOutput) -> str:
    return json.dumps(
        [
            {
                "claim": c.claim_text,
                "stance": c.stance,
                "confidence": c.confidence,
                "supporting_evidence_ids": c.supporting_evidence_ids,
                "conflicting_evidence_ids": c.conflicting_evidence_ids,
            }
            for c in output.claims
        ],
        indent=1,
    )


def _parse(raw: str, model):
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        return model.model_validate_json(text.strip())
    except (ValidationError, ValueError) as exc:
        # Category only: validation errors can quote model output.
        _LOGGER.warning("skeptic output invalid error_type=%s", type(exc).__name__)
        raise AnalysisUnavailableError("the Skeptic did not return a usable answer") from None
