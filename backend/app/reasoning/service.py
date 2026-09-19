"""Case orchestration: question -> retrieval -> Primary -> validation -> receipt.

Phase 4 inserts risk routing, the Skeptic, and reconciliation between the
Primary and the validator; the validator stays the last step either way.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field

from app.core.enums import CaseStatus, Confidence
from app.core.errors import AnalysisUnavailableError
from app.db import repository
from app.reasoning import primary, reconcile, risk, skeptic
from app.reasoning.evidence import EvidenceSet
from app.reasoning.llm import LLMClient
from app.reasoning.prompts import SYSTEM_PROMPT, build_widened_prompt
from app.retrieval import temporal
from app.retrieval.service import RetrievalService
from app.retrieval.text import topic_terms
from app.schemas.reasoning import PrimaryOutput
from app.schemas.receipt import CaseReceipt, ReviewInfo, ReviewObjection, ValidatedReceipt
from app.validation import receipt_validator

_LOGGER = logging.getLogger(__name__)

_LATER_SWEEP_HITS = 6
_COVERAGE_HITS = 14

PROVISIONAL_NOTE = (
    "The adversarial check of this answer could not be completed; treat it as provisional."
)


@dataclass
class CaseTrace:
    """Ids and counts only -- never evidence text (CLAUDE.md 28)."""

    request_id: str
    case_id: str = ""
    retrieved_ids: list[str] = field(default_factory=list)
    visible_count: int = 0
    semantic_used: bool = False
    rejected_ids: list[str] = field(default_factory=list)
    final_evidence_ids: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)
    risk_level: str = "LOW"
    risk_triggers: list[str] = field(default_factory=list)
    skeptic_ran: bool = False
    counter_queries: int = 0
    counter_new_ids: list[str] = field(default_factory=list)
    counter_units_examined: int = 0
    coverage_new_ids: list[str] = field(default_factory=list)
    reconciled: bool = False
    review_completed: bool = True


class CaseService:
    def __init__(self, conn: sqlite3.Connection, retrieval: RetrievalService, llm: LLMClient):
        self._conn = conn
        self._retrieval = retrieval
        self._llm = llm

    def answer(self, query: str) -> tuple[CaseReceipt, CaseTrace]:
        trace = CaseTrace(request_id=uuid.uuid4().hex[:12])

        retrieval = self._retrieval.retrieve(query)
        evidence = EvidenceSet.from_results(retrieval)
        trace.retrieved_ids = retrieval.ranked_ids
        trace.visible_count = len(evidence.visible_ids)
        trace.semantic_used = retrieval.semantic_used

        # No evidence at all: do not ask a model to answer from nothing.
        if not evidence.visible_ids:
            return self._store(_insufficient(query), trace)

        output = primary.analyze(self._llm, query, retrieval)
        if retrieval.wide:
            output = self._widen(query, output, evidence, trace)
        review = ReviewInfo()

        # Routing is deterministic; the model's own confidence can only
        # escalate scrutiny, never waive it (CLAUDE.md 12).
        assessment = risk.assess(query, output, retrieval, evidence)
        # CLAUDE.md 9.5: sweep for later evidence on the *answer's* own topic terms,
        # which the question may never have used ("file size check").
        later_new = self._later_sweep(output, evidence)
        if later_new:
            assessment.triggers.append("later evidence on the answer's own terms exists")
        review.risk_level = assessment.level
        review.risk_triggers = assessment.triggers
        if assessment.deep_check:
            output, review = self._deep_check(query, output, evidence, review, later_new)

        trace.risk_level = review.risk_level
        trace.risk_triggers = review.risk_triggers
        trace.skeptic_ran = review.skeptic_ran
        trace.counter_queries = review.counter_queries
        trace.counter_new_ids = review.counter_evidence_ids
        trace.counter_units_examined = review.counter_units_examined
        trace.reconciled = review.reconciled
        trace.review_completed = review.completed

        validated = receipt_validator.validate_primary(
            self._conn, output, query=query, visible_ids=set(evidence.visible_ids)
        )
        validated = validated.model_copy(
            update={
                "review": receipt_validator.sanitize_review(
                    self._conn, review, set(evidence.visible_ids)
                )
            }
        )
        return self._store(validated, trace)

    def _widen(
        self, query: str, output: PrimaryOutput, evidence: EvidenceSet, trace: CaseTrace
    ) -> PrimaryOutput:
        """Enumerative questions ("every figure", "how did it change") are
        answered by units the question's own words rarely reach. Search the whole
        archive on the terms of the reasoner's first answer; if that finds units
        it had not seen, it answers again over the enlarged evidence. The added
        units get no special trust: the Skeptic and validator still run after."""
        terms = topic_terms(" ".join(output.search_terms))
        if not terms:
            return output
        added = evidence.add(
            self._retrieval.coverage_evidence(terms), top_hits=_COVERAGE_HITS, top_later=0
        )
        trace.coverage_new_ids = added
        if not added:
            return output
        return primary.parse_output(
            self._llm, SYSTEM_PROMPT, build_widened_prompt(query, evidence, set(added))
        )

    def _later_sweep(self, output: PrimaryOutput, evidence: EvidenceSet) -> list[str]:
        """Ids of later evidence not yet shown to any model, found by the Primary's
        own ``search_terms`` after the earliest evidence it cited."""
        terms = topic_terms(" ".join(output.search_terms))
        cited = {i for c in output.claims for i in c.supporting_evidence_ids}
        after = temporal.earliest_date(self._conn, sorted(cited))
        if not terms or after is None:
            return []
        return evidence.add(
            self._retrieval.later_evidence(terms, after),
            top_hits=_LATER_SWEEP_HITS,
        )

    def _deep_check(
        self,
        query: str,
        output: PrimaryOutput,
        evidence: EvidenceSet,
        review: ReviewInfo,
        later_new: list[str] | None = None,
    ) -> tuple[PrimaryOutput, ReviewInfo]:
        """Skeptic -> counter-retrieval -> reconciliation. A failure here
        never yields an unchecked confident answer: the result is degraded
        and marked provisional instead."""
        try:
            # Attempted, whether or not it finishes: a failure is then visible
            # as skeptic_ran with completed=False, never as "no check happened".
            review.skeptic_ran = True
            result = skeptic.run(
                self._llm, self._retrieval, query, output, evidence, extra_new_ids=later_new
            )
            review.counter_queries = result.queries_run
            review.counter_units_examined = len(result.new_evidence_ids)
            review.objections = [
                ReviewObjection(text=o.text, severity=o.severity, evidence_ids=o.evidence_ids)
                for o in result.objections
            ]
            review.counter_evidence_ids = list(
                dict.fromkeys(i for o in result.objections for i in o.evidence_ids)
            )
            if result.has_findings:
                output = reconcile.run(self._llm, query, output, evidence, result)
                review.reconciled = True
        except AnalysisUnavailableError:
            _LOGGER.warning("adversarial check incomplete; degrading answer")
            review.completed = False
            output = _provisional(output)
        return output, review

    def get(self, case_id: str) -> CaseReceipt | None:
        return load_case_receipt(self._conn, case_id)

    def _store(
        self, validated: ValidatedReceipt, trace: CaseTrace
    ) -> tuple[CaseReceipt, CaseTrace]:
        case_id = uuid.uuid4().hex
        created_at = receipt_validator.now_iso()
        usage = validated.evidence_ids()
        repository.save_case(
            self._conn,
            case_id=case_id,
            query=validated.query,
            receipt_json=validated.model_dump_json(),
            created_at=created_at,
            evidence_usage=usage,
        )
        self._conn.commit()

        trace.case_id = case_id
        trace.rejected_ids = validated.validation.rejected_evidence_ids
        trace.final_evidence_ids = sorted(set().union(*usage.values()))
        trace.validation_notes = validated.validation.notes
        _LOGGER.info(
            "case complete request_id=%s case_id=%s status=%s claims=%s rejected_ids=%s",
            trace.request_id,
            case_id,
            validated.status,
            len(validated.claims),
            len(trace.rejected_ids),
        )
        receipt = receipt_validator.hydrate_receipt(
            self._conn, validated, case_id=case_id, created_at=created_at
        )
        return receipt, trace


def load_case_receipt(conn: sqlite3.Connection, case_id: str) -> CaseReceipt | None:
    """Serve a stored Case, re-validating every cited id against the database now."""
    row = repository.load_case(conn, case_id)
    if row is None:
        return None
    validated = ValidatedReceipt.model_validate(json.loads(row["receipt_json"]))
    return receipt_validator.hydrate_receipt(
        conn, validated, case_id=case_id, created_at=row["created_at"]
    )


def _insufficient(query: str) -> ValidatedReceipt:
    from app.core.enums import CaseStatus

    return ValidatedReceipt(
        query=query,
        status=CaseStatus.INSUFFICIENT_EVIDENCE,
        answer_summary=receipt_validator.NO_SUPPORT_SUMMARY,
        claims=[],
        missing_information=["No evidence in the archive matched this question."],
    )


def _provisional(output: PrimaryOutput) -> PrimaryOutput:
    """Cap an answer whose required adversarial check did not finish."""
    claims = [
        c.model_copy(update={"confidence": Confidence.MEDIUM})
        if c.confidence == Confidence.HIGH
        else c
        for c in output.claims
    ]
    status = (
        CaseStatus.PARTIALLY_SUPPORTED if output.status == CaseStatus.SUPPORTED else output.status
    )
    return output.model_copy(
        update={
            "claims": claims,
            "status": status,
            "missing_information": [
                *output.missing_information,
                PROVISIONAL_NOTE,
            ],
        }
    )
