"""Reconsideration Radar shapes (docs/RECONSIDERATION_RADAR.md).

The outcome vocabulary is deliberately small and bounded: the Radar may say
a blocker *may* have changed. It never says an idea is approved, funded,
safe, or right, and it never tells the organization what to do.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.receipt import Citation


class Outcome(StrEnum):
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class Assessment(StrEnum):
    STILL_BLOCKED = "STILL_BLOCKED"
    PARTIALLY_CHANGED = "PARTIALLY_CHANGED"
    WORTH_REASSESSING = "WORTH_REASSESSING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class BlockerCategory(StrEnum):
    CAPACITY_EFFORT = "CAPACITY_EFFORT"
    COST_VENDOR = "COST_VENDOR"
    TIMING_DEPENDENCY = "TIMING_DEPENDENCY"
    TECHNOLOGY_MATURITY = "TECHNOLOGY_MATURITY"
    SECURITY_COMPLIANCE = "SECURITY_COMPLIANCE"
    REGULATION = "REGULATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


CATEGORY_LABELS = {c.value: c.value.replace("_", " / ").title() for c in BlockerCategory}


# ---------------------------------------------------------- model outputs


class DiscoveredCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    proposal: str = Field(min_length=1)
    outcome: Outcome
    blocker: str = Field(min_length=1)
    blocker_category: BlockerCategory
    monitorable_condition: str = Field(min_length=1)
    proposal_evidence_ids: list[str] = Field(default_factory=list)
    outcome_evidence_ids: list[str] = Field(default_factory=list)
    blocker_evidence_ids: list[str] = Field(default_factory=list)


class Discovery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidates: list[DiscoveredCandidate] = Field(default_factory=list)


class AssessmentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    changed_condition: str | None = None
    internal_change_evidence_ids: list[str] = Field(default_factory=list)
    external_signal_ids: list[str] = Field(default_factory=list)
    current_state_evidence_ids: list[str] = Field(default_factory=list)
    assessment: Assessment
    assessment_rationale: str = Field(min_length=1)
    unestablished: list[str] = Field(default_factory=list)
    next_check: str = Field(min_length=1)


class CheckResult(BaseModel):
    """One of the seven Skeptic checks. `answered=False` means the archive
    cannot settle it; that is shown as missing information, never guessed."""

    model_config = ConfigDict(extra="ignore")

    check: int = Field(ge=1, le=7)
    answered: bool
    passed: bool | None = None
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class RadarVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checks: list[CheckResult] = Field(default_factory=list)
    reject_candidate: bool = False
    reject_reason: str | None = None


# ------------------------------------------------------------- stored form


class ExternalSignal(BaseModel):
    """A curated outside development. Never an internal organizational fact."""

    signal_id: str
    title: str
    source: str
    published: str
    url: str | None = None
    summary: str
    categories: list[str] = Field(default_factory=list)


class StoredFinding(BaseModel):
    """Persisted in pulse_findings.finding_json: ids and short model prose, no
    evidence text, so a deleted unit cannot linger in it."""

    proposal: str
    outcome: Outcome
    blocker: str
    blocker_category: BlockerCategory
    monitorable_condition: str
    proposal_evidence_ids: list[str]
    outcome_evidence_ids: list[str]
    blocker_evidence_ids: list[str]
    changed_condition: str | None
    internal_change_evidence_ids: list[str]
    external_signal_ids: list[str]
    current_state_evidence_ids: list[str]
    assessment: Assessment
    assessment_rationale: str
    unestablished: list[str]
    next_check: str
    checks: list[CheckResult]
    notes: list[str] = Field(default_factory=list)
    case_id: str

    def evidence_ids(self) -> set[str]:
        ids: set[str] = set()
        for group in (
            self.proposal_evidence_ids,
            self.outcome_evidence_ids,
            self.blocker_evidence_ids,
            self.internal_change_evidence_ids,
            self.current_state_evidence_ids,
        ):
            ids.update(group)
        for check in self.checks:
            ids.update(check.evidence_ids)
        return ids


# -------------------------------------------------------------- served card


class FindingCard(BaseModel):
    finding_id: str
    category: str = "RECONSIDERATION_CANDIDATE"
    proposal: str
    outcome: Outcome
    proposal_citations: list[Citation]
    outcome_citations: list[Citation]
    blocker: str
    blocker_category: str
    blocker_citations: list[Citation]
    monitorable_condition: str
    changed_condition: str | None
    # Kept as separate lenses: internal facts, external signals, assessment.
    internal_change_citations: list[Citation]
    external_signals: list[ExternalSignal]
    current_state_citations: list[Citation]
    assessment: Assessment
    assessment_rationale: str
    unestablished: list[str]
    next_check: str
    checks: list[CheckResult]
    case_id: str
    created_at: str
