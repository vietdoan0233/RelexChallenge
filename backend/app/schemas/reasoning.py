"""What the Primary Reasoner is allowed to emit.

Evidence is referenced by id only. There is deliberately no field for a
speaker, date, document name, or quote: those are hydrated from the
database after validation (CLAUDE.md 10), so a model cannot fabricate
them. Unknown keys a model adds are ignored, not trusted.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CaseStatus, Confidence, Stance


class CandidateClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_text: str = Field(min_length=1)
    stance: Stance
    confidence: Confidence
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    uncertainty: str | None = None


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_text: str = Field(min_length=1)
    state: Stance
    confidence: Confidence
    evidence_ids: list[str] = Field(default_factory=list)


class PrimaryOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer_summary: str = Field(min_length=1)
    status: CaseStatus
    claims: list[CandidateClaim] = Field(default_factory=list)
    conflict_resolution: str | None = None
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    related_questions: list[str] = Field(default_factory=list)
    # Model suggestions that steer retrieval only; never displayed as fact.
    search_terms: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
