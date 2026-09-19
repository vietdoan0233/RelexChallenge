"""Final reconciliation by the Primary Reasoner (CLAUDE.md 14).

After the Skeptic, the Primary gets the original claims, all evidence, the
Skeptic's objections and any new counter-evidence, and returns the final
structured answer. There is no separate "polish" stage: the validator runs
straight after this.
"""

import json

from app.reasoning import primary
from app.reasoning.evidence import EvidenceSet
from app.reasoning.llm import LLMClient
from app.reasoning.prompts import SYSTEM_PROMPT, format_evidence_set
from app.reasoning.skeptic import SkepticResult
from app.schemas.reasoning import PrimaryOutput

RECONCILE_SYSTEM = (
    SYSTEM_PROMPT.replace("[ROLE:PRIMARY]", "[ROLE:RECONCILE]")
    + """

RECONCILIATION
You already produced initial claims. A Skeptic then searched for counter-evidence (new results are marked '!'). Produce the FINAL answer in the same JSON shape. Do not average contradictory claims: surface the conflict, explain in conflict_resolution why one interpretation is currently stronger, and preserve real uncertainty. Distinguish superseded or stale from false or unverified. If the counter-evidence shows an initial claim was wrong, overstated, or too broad, correct it. Objections that no evidence supports should be ignored, not repeated. Return INSUFFICIENT_EVIDENCE when the evidence cannot settle the question."""
)


def run(
    llm: LLMClient,
    query: str,
    initial: PrimaryOutput,
    evidence: EvidenceSet,
    skeptic: SkepticResult,
) -> PrimaryOutput:
    objections = [o.model_dump(mode="json") for o in skeptic.objections]
    user = (
        f"QUESTION\n{query}\n\nINITIAL ANSWER\n{initial.model_dump_json(indent=1)}\n\n"
        f"SKEPTIC OBJECTIONS\n{json.dumps(objections, indent=1)}\n\n"
        f"EVIDENCE\n{format_evidence_set(evidence, new_ids=set(skeptic.new_evidence_ids))}"
    )
    return primary.parse_output(
        llm, RECONCILE_SYSTEM, user, unusable="the reasoning service could not reconcile the answer"
    )
