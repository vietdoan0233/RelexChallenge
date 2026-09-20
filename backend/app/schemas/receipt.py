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


class ReviewObjection(BaseModel):
    text: str
    severity: Confidence
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewInfo(BaseModel):
    """How the Case was checked: risk routing and the Skeptic's work.

    Shown to the reader so a "checked for contradictions" claim is
    inspectable. Ids only; counter-evidence is served through the evidence
    endpoint like any other citation.
    """

    risk_level: str = "LOW"
    risk_triggers: list[str] = Field(default_factory=list)
    skeptic_ran: bool = False
    counter_queries: int = 0
    # How many new units the counter-search surfaced (for transparency), versus
    # `counter_evidence_ids`: only the ones the Skeptic actually relied on.
    counter_units_examined: int = 0
    counter_evidence_ids: list[str] = Field(default_factory=list)
    objections: list[ReviewObjection] = Field(default_factory=list)
    reconciled: bool = False
    # False when a required adversarial check could not finish; the answer
    # is then explicitly provisional rather than silently unchecked.
    completed: bool = True


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
    review: ReviewInfo = Field(default_factory=ReviewInfo)

    def evidence_ids(self) -> dict[str, set[str]]:
        """Referenced ids by usage, for the case_evidence table."""
        usage: dict[str, set[str]] = {"SUPPORT": set(), "CONFLICT": set(), "TIMELINE": set()}
        for claim in self.claims:
            usage["SUPPORT"].update(claim.supporting_evidence_ids)
            usage["CONFLICT"].update(claim.conflicting_evidence_ids)
        for event in self.timeline_events:
            usage["TIMELINE"].update(event.evidence_ids)
        # Counter-evidence the Skeptic *relied on* is a dependency too: deleting
        # it must invalidate the Case just like cited support. Units merely
        # surfaced by a search are not recorded, or nearly every Case would be
        # invalidated by any deletion.
        usage["CONFLICT"].update(self.review.counter_evidence_ids)
        for objection in self.review.objections:
            usage["CONFLICT"].update(objection.evidence_ids)
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
    # The AUTHOR/SPEAKER subject for this unit, or None for an anonymous
    # label / unresolved free text. Lets the UI link speaker_sender to that
    # participant's universal profile (CLAUDE.md 19.D) without a lookup.
    subject_id: str | None = None

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
            subject_id=record.subject_id,
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
    review: ReviewInfo
    created_at: str


class EvidenceView(BaseModel):
    """One cited unit plus its neighbours, so a bare "yes" is never shown
    without the exchange it answers (CLAUDE.md 9.4)."""

    citation: Citation
    context_before: list[Citation]
    context_after: list[Citation]
