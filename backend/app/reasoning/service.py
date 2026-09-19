"""Case orchestration: question -> retrieval -> Primary -> validation -> receipt.

Phase 4 inserts risk routing, the Skeptic, and reconciliation between the
Primary and the validator; the validator stays the last step either way.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field

from app.db import repository
from app.reasoning import primary
from app.reasoning.llm import LLMClient
from app.retrieval.service import RetrievalService
from app.schemas.receipt import CaseReceipt, ValidatedReceipt
from app.validation import receipt_validator

_LOGGER = logging.getLogger(__name__)


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


class CaseService:
    def __init__(self, conn: sqlite3.Connection, retrieval: RetrievalService, llm: LLMClient):
        self._conn = conn
        self._retrieval = retrieval
        self._llm = llm

    def answer(self, query: str) -> tuple[CaseReceipt, CaseTrace]:
        trace = CaseTrace(request_id=uuid.uuid4().hex[:12])

        retrieval = self._retrieval.retrieve(query)
        trace.retrieved_ids = retrieval.ranked_ids
        trace.visible_count = len(retrieval.visible_evidence_ids)
        trace.semantic_used = retrieval.semantic_used

        # No evidence at all: do not ask a model to answer from nothing.
        if retrieval.visible_evidence_ids:
            output = primary.analyze(self._llm, query, retrieval)
            validated = receipt_validator.validate_primary(
                self._conn,
                output,
                query=query,
                visible_ids=set(retrieval.visible_evidence_ids),
            )
        else:
            validated = _insufficient(query)

        return self._store(validated, trace)

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
