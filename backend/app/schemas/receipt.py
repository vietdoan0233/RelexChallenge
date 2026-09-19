"""Validated receipt shapes.

`ValidatedReceipt` is what is persisted: ids only, so a stored Case holds
no evidence text of its own and a deleted unit cannot linger in it.
`CaseReceipt` is what the API serves: every citation field comes from the
database, never from the model (CLAUDE.md 15).
"""

from pydantic import BaseModel, Field

from app.core.enums import CaseStatus, Confidence, Stance
from app.retrieval.records import EvidenceRecord


class ValidationReport(BaseModel):
    """Counts and rejected ids only -- no evidence text."""

    rejected_evidence_ids: list[str] = Field(default_factory=list)
    dropped_claims: int = 0
    dropped_timeline_events: int = 0
    downgraded_claims: int = 0
    notes: list[str] = Field(default_factory=list)


class ValidatedClaim(BaseModel):
    claim_text: str
    stance: Stance
    confidence: Confidence
    supporting_evidence_ids: list[str]
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    uncertainty: str | None = None


class ValidatedTimelineEvent(BaseModel):
    event_text: str
    state: Stance
    confidence: Confidence
    evidence_ids: list[str]


class ValidatedReceipt(BaseModel):
    query: str
    status: CaseStatus
    answer_summary: str
    claims: list[ValidatedClaim]
    conflict_resolution: str | None = None
    timeline_events: list[ValidatedTimelineEvent] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    related_questions: list[str] = Field(default_factory=list)
    validation: ValidationReport = Field(default_factory=ValidationReport)

    def evidence_ids(self) -> dict[str, set[str]]:
        """Referenced ids by usage, for the case_evidence table."""
        usage: dict[str, set[str]] = {"SUPPORT": set(), "CONFLICT": set(), "TIMELINE": set()}
        for claim in self.claims:
            usage["SUPPORT"].update(claim.supporting_evidence_ids)
            usage["CONFLICT"].update(claim.conflicting_evidence_ids)
        for event in self.timeline_events:
            usage["TIMELINE"].update(event.evidence_ids)
        return usage


class Citation(BaseModel):
    evidence_id: str
    document_id: str
    filename: str
    document_type: str
    document_title: str | None
    event_date: str | None
    timestamp_text: str | None
    speaker_sender: str | None
    thread_context: str | None
    raw_text: str
    is_truncated: bool

    @classmethod
    def from_record(cls, record: EvidenceRecord) -> "Citation":
        return cls(
            evidence_id=record.evidence_id,
            document_id=record.document_id,
            filename=record.filename,
            document_type=record.document_type,
            document_title=record.document_title,
            event_date=record.event_date,
            timestamp_text=record.timestamp_text,
            speaker_sender=record.speaker_sender,
            thread_context=record.thread_context,
            raw_text=record.raw_text,
            is_truncated=record.is_truncated,
        )


class ReceiptClaim(BaseModel):
    claim_text: str
    stance: Stance
    confidence: Confidence
    uncertainty: str | None
    support: list[Citation]
    conflicts: list[Citation]


class ReceiptTimelineEvent(BaseModel):
    event_text: str
    state: Stance
    confidence: Confidence
    event_date: str | None
    citations: list[Citation]


class CaseReceipt(BaseModel):
    case_id: str
    query: str
    status: CaseStatus
    answer_summary: str
    claims: list[ReceiptClaim]
    conflict_resolution: str | None
    timeline_events: list[ReceiptTimelineEvent]
    missing_information: list[str]
    related_questions: list[str]
    validation: ValidationReport
    created_at: str


class EvidenceView(BaseModel):
    """One cited unit plus its neighbours, so a bare "yes" is never shown
    without the exchange it answers (CLAUDE.md 9.4)."""

    citation: Citation
    context_before: list[Citation]
    context_after: list[Citation]
