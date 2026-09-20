"""Reconsideration Radar pipeline (docs/RECONSIDERATION_RADAR.md).

    explicit rejected/deferred proposals -> evidence-backed blocker
      -> later internal evidence + curated external signals
      -> assessment -> Skeptic (real counter-retrieval + seven checks)
      -> deterministic guard -> validated Case + pulse_findings row

Findings are precomputed, never generated per page load, and never shown
without a linked, validated Case and Evidence Units.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.enums import Confidence
from app.core.errors import AnalysisUnavailableError
from app.db import repository
from app.radar import guard, prompts, signals
from app.radar.schemas import (
    Assessment,
    AssessmentOut,
    CheckResult,
    DiscoveredCandidate,
    Discovery,
    ExternalSignal,
    FindingCard,
    RadarVerdict,
    StoredFinding,
)
from app.reasoning import skeptic
from app.reasoning.evidence import EvidenceSet
from app.reasoning.llm import LLMClient
from app.reasoning.prompts import format_evidence_set
from app.retrieval.records import hydrate
from app.retrieval.service import RetrievalService
from app.schemas.reasoning import PrimaryOutput
from app.schemas.receipt import Citation, ReviewInfo, ReviewObjection
from app.validation import receipt_validator

_LOGGER = logging.getLogger(__name__)
CATEGORY = "RECONSIDERATION_CANDIDATE"
MAX_FINDINGS = 10

# Vocabulary-diverse discovery searches in three focused passes. One broad pass
# makes the model conservative; separate passes for rejection, deferral and
# constraint-blocked ideas each get their own evidence and their own call.
DISCOVERY_PASSES = (
    (
        "we decided against it",
        "proposal rejected not going to do that",
        "no we are not doing that turned down declined",
    ),
    (
        "deferred until later postponed not now",
        "descoped moved to a separate workstream out of scope",
        "parked for a later phase",
    ),
    (
        "on hold we will revisit this later",
        "wait until then before we do this",
        "instead of that we will do this other thing",
    ),
    (
        "cannot do this because of capacity and resources",
        "not possible because of security compliance or data protection",
        "too expensive cost budget not approved not enough data",
    ),
)
_DISCOVERY_TOP_HITS = 8


@dataclass
class RadarRun:
    surfaced: list[str] = field(default_factory=list)  # finding ids
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (proposal, reason)
    dropped_unsupported: int = 0


_M = TypeVar("_M", bound=BaseModel)


def structured(llm: LLMClient, system: str, user: str, model: type[_M]) -> _M:
    """One structured call with a single schema-repair retry, like the Primary."""
    note = ""
    for attempt in (1, 2):
        raw = llm.complete_json(system=system, user=user + note)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0]
        try:
            return model.model_validate_json(text.strip())
        except (ValidationError, ValueError) as exc:
            _LOGGER.warning(
                "radar output invalid attempt=%s error_type=%s", attempt, type(exc).__name__
            )
            note = (
                "\n\nYour previous reply was not valid for the required JSON schema. "
                "Reply again with ONE valid JSON object."
            )
    raise AnalysisUnavailableError("the Radar did not receive a usable structured answer")


def _make_visible(conn: sqlite3.Connection, evidence: EvidenceSet, ids: list[str]) -> None:
    for record in hydrate(conn, ids):
        evidence.records[record.evidence_id] = record
        if record.evidence_id not in evidence.visible_ids:
            evidence.visible_ids.append(record.evidence_id)
        evidence.hit_ids.add(record.evidence_id)


def run_radar(
    conn: sqlite3.Connection,
    retrieval: RetrievalService,
    llm: LLMClient,
    source_dir: Path,
    *,
    limit: int = 5,
) -> RadarRun:
    """Precompute findings, replacing old cards only after a usable result.

    A provider outage or a fully rejected candidate set must not erase the
    previous derived Radar. The savepoint also rolls back any partial Case or
    finding created by an interrupted run.
    """
    # Keep every caller, including the CLI, inside the product-wide cap.
    limit = min(limit, MAX_FINDINGS)
    curated = signals.load_signals(source_dir)
    result = RadarRun()
    conn.execute("SAVEPOINT radar_refresh")

    try:
        evidence = EvidenceSet()  # every id any pass showed a model: what may be cited
        discovered: list[DiscoveredCandidate] = []
        for queries in DISCOVERY_PASSES:
            batch = EvidenceSet()
            for query in queries:
                found = retrieval.retrieve(query, temporal_sweep=False)
                batch.add(found, top_hits=_DISCOVERY_TOP_HITS)
                evidence.add(found, top_hits=_DISCOVERY_TOP_HITS)
            try:
                found_here = structured(
                    llm,
                    prompts.DISCOVER_SYSTEM,
                    f"EVIDENCE\n{format_evidence_set(batch)}",
                    Discovery,
                )
            except AnalysisUnavailableError:
                continue  # one failed pass must not lose the other passes' candidates
            discovered.extend(found_here.candidates)
        discovery = Discovery(candidates=discovered)

        seen: set[str] = set()
        for candidate in discovery.candidates:
            if len(result.surfaced) >= limit:
                break
            key = candidate.proposal.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            checked = _validated_candidate(conn, candidate, set(evidence.visible_ids))
            if checked is None:
                result.dropped_unsupported += 1
                continue
            try:
                finding_id, rejection = _evaluate(conn, retrieval, llm, checked, curated)
            except AnalysisUnavailableError:
                result.rejected.append((candidate.proposal, "the check could not be completed"))
                continue
            if finding_id is None:
                result.rejected.append((candidate.proposal, rejection or "rejected by the Skeptic"))
                continue
            result.surfaced.append(finding_id)

        if result.surfaced:
            _clear_previous(conn, keep_finding_ids=set(result.surfaced))
        else:
            conn.execute("ROLLBACK TO SAVEPOINT radar_refresh")
        conn.execute("RELEASE SAVEPOINT radar_refresh")
        conn.commit()
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT radar_refresh")
        conn.execute("RELEASE SAVEPOINT radar_refresh")
        conn.rollback()
        raise
    return result


def _validated_candidate(
    conn: sqlite3.Connection, candidate: DiscoveredCandidate, visible: set[str]
) -> DiscoveredCandidate | None:
    """A candidate needs real, visible evidence for the proposal, the outcome
    and the blocker. Anything less is dropped, not softened."""

    def keep(ids: list[str]) -> list[str]:
        good = receipt_validator.valid_ids(conn, set(ids), visible)
        return [i for i in dict.fromkeys(ids) if i in good]

    updated = candidate.model_copy(
        update={
            "proposal_evidence_ids": keep(candidate.proposal_evidence_ids),
            "outcome_evidence_ids": keep(candidate.outcome_evidence_ids),
            "blocker_evidence_ids": keep(candidate.blocker_evidence_ids),
        }
    )
    if not (
        updated.proposal_evidence_ids
        and updated.outcome_evidence_ids
        and updated.blocker_evidence_ids
    ):
        return None
    return updated


def _evaluate(
    conn: sqlite3.Connection,
    retrieval: RetrievalService,
    llm: LLMClient,
    candidate: DiscoveredCandidate,
    curated: list[ExternalSignal],
) -> tuple[str | None, str | None]:
    """(finding_id, None) when surfaced; (None, reason) when the Skeptic rejects it."""
    own_ids = (
        candidate.proposal_evidence_ids
        + candidate.outcome_evidence_ids
        + candidate.blocker_evidence_ids
    )
    outcome_records = hydrate(conn, candidate.outcome_evidence_ids)
    outcome_date = min((r.event_date for r in outcome_records if r.event_date), default=None)

    evidence = EvidenceSet()
    _make_visible(conn, evidence, own_ids)
    for query in (f"{candidate.proposal} {candidate.blocker}", candidate.monitorable_condition):
        evidence.add(retrieval.retrieve(query, temporal_sweep=True), top_hits=8, top_later=6)

    relevant = [
        s for s in curated if not s.categories or candidate.blocker_category.value in s.categories
    ]
    signal_block = json.dumps(
        [s.model_dump(exclude={"categories"}) for s in relevant], indent=1, ensure_ascii=False
    )
    candidate_block = candidate.model_dump_json(indent=1)
    assessed = structured(
        llm,
        prompts.ASSESS_SYSTEM,
        f"CANDIDATE\n{candidate_block}\n\nEXTERNAL SIGNALS (curated; not internal facts)\n"
        f"{signal_block}\n\nEVIDENCE\n{format_evidence_set(evidence)}",
        AssessmentOut,
    )

    # Skeptic gate: real counter-retrieval, then the seven checks.
    stand_in = PrimaryOutput.model_validate(
        {
            "answer_summary": candidate.proposal,
            "status": "PARTIALLY_SUPPORTED",
            "claims": [
                {
                    "claim_text": f"{candidate.proposal} was {candidate.outcome.value.lower()} "
                    f"because {candidate.blocker}",
                    "stance": "OBJECTION",
                    "confidence": "MEDIUM",
                    "supporting_evidence_ids": own_ids,
                },
                {
                    "claim_text": assessed.changed_condition or "The blocker may have changed.",
                    "stance": "UNCERTAIN",
                    "confidence": "LOW",
                    "supporting_evidence_ids": assessed.internal_change_evidence_ids,
                },
            ],
        }
    )
    counter = skeptic.counter_retrieve(
        llm,
        retrieval,
        f"Was '{candidate.proposal}' really stopped, and has the blocker changed?",
        stand_in,
        evidence,
    )
    verdict = structured(
        llm,
        prompts.SKEPTIC_SYSTEM,
        f"CANDIDATE\n{candidate_block}\n\nCLAIMED CHANGE\n{assessed.changed_condition}\n"
        f"ASSESSMENT\n{assessed.assessment}: {assessed.assessment_rationale}\n\n"
        f"EVIDENCE (counter-search results marked '!')\n"
        f"{format_evidence_set(evidence, new_ids=set(counter.new_evidence_ids))}",
        RadarVerdict,
    )

    verdict = verdict.model_copy(update={"checks": _all_seven(verdict.checks)})

    # Check 1 (genuinely rejected/deferred) and 7 (obsolete) each end a candidate.
    for check in verdict.checks:
        if check.answered and check.passed is False and check.check in (1, 7):
            return None, check.note or f"failed Skeptic check {check.check}"
    if verdict.reject_candidate:
        return None, verdict.reject_reason or "the Skeptic rejected this candidate"

    visible = set(evidence.visible_ids)
    good_internal = receipt_validator.valid_ids(
        conn, set(assessed.internal_change_evidence_ids), visible
    )
    internal = [
        i for i in dict.fromkeys(assessed.internal_change_evidence_ids) if i in good_internal
    ]
    known = {s.signal_id for s in curated}
    external = [s for s in dict.fromkeys(assessed.external_signal_ids) if s in known]
    good_state = receipt_validator.valid_ids(
        conn, set(assessed.current_state_evidence_ids), visible
    )
    state = [i for i in dict.fromkeys(assessed.current_state_evidence_ids) if i in good_state]

    clean = receipt_validator.clean_prose  # ids belong in id fields, never in prose
    assessed = assessed.model_copy(
        update={
            "changed_condition": clean(assessed.changed_condition),
            "assessment_rationale": clean(assessed.assessment_rationale) or "",
            "next_check": clean(assessed.next_check) or "",
            "unestablished": [c for c in (clean(u) for u in assessed.unestablished) if c],
        }
    )
    notes: list[str] = []
    checks = [
        c.model_copy(
            update={
                "evidence_ids": [
                    i
                    for i in dict.fromkeys(c.evidence_ids)
                    if i in receipt_validator.valid_ids(conn, set(c.evidence_ids), visible)
                ],
                "note": guard.bounded(clean(c.note), notes) or "",
            }
        )
        for c in verdict.checks
    ]
    final, missing, guard_notes = guard.finalize(
        assessed,
        verdict.model_copy(update={"checks": checks}),
        valid_internal=internal,
        valid_signals=external,
    )
    notes.extend(guard_notes)
    rationale = guard.bounded(assessed.assessment_rationale, notes) or guard.WITHHELD
    next_check = guard.bounded(assessed.next_check, notes) or guard.WITHHELD
    changed = guard.bounded(assessed.changed_condition, notes)
    # monitorable_condition is the Radar's own voice ("what would have to
    # change"); proposal and blocker describe what people said in the past, so
    # they are constrained by the prompt and by their receipts instead.
    condition = guard.bounded(clean(candidate.monitorable_condition), notes) or guard.WITHHELD

    case_id = _store_case(
        conn, candidate, final, changed, internal, state, missing, checks, counter, visible
    )
    stored = StoredFinding(
        proposal=clean(candidate.proposal) or candidate.proposal,
        outcome=candidate.outcome,
        blocker=clean(candidate.blocker) or candidate.blocker,
        blocker_category=candidate.blocker_category,
        monitorable_condition=condition,
        proposal_evidence_ids=candidate.proposal_evidence_ids,
        outcome_evidence_ids=candidate.outcome_evidence_ids,
        blocker_evidence_ids=candidate.blocker_evidence_ids,
        changed_condition=changed,
        internal_change_evidence_ids=internal,
        external_signal_ids=external,
        current_state_evidence_ids=state,
        assessment=final,
        assessment_rationale=rationale,
        unestablished=missing,
        next_check=next_check,
        checks=checks,
        notes=notes,
        case_id=case_id,
    )
    return _store_finding(conn, stored, outcome_date), None


def _all_seven(checks: list[CheckResult]) -> list[CheckResult]:
    """A Skeptic that skips a check has not answered it. Missing checks become
    explicit 'not answered' entries, so a skipped check 1 or 7 shows up as
    missing information instead of silently passing."""
    by_number = {c.check: c for c in checks}
    return [
        by_number.get(n)
        or CheckResult(check=n, answered=False, passed=None, note="the Skeptic did not evaluate it")
        for n in range(1, 8)
    ]


def _store_case(
    conn, candidate, final, changed, internal, state, missing, checks, counter, visible
) -> str:
    """Represent the finding as a validated Case, not free-floating prose
    (Radar doc, Phase 3): every claim is validated like any other."""
    claims = [
        {
            "claim_text": f"Proposal: {candidate.proposal}",
            "stance": "PROPOSAL",
            "confidence": "HIGH",
            "supporting_evidence_ids": candidate.proposal_evidence_ids,
        },
        {
            "claim_text": f"It was {candidate.outcome.value.lower()}.",
            "stance": "OBJECTION",
            "confidence": "HIGH",
            "supporting_evidence_ids": candidate.outcome_evidence_ids,
        },
        {
            "claim_text": f"Why it was stopped: {candidate.blocker}",
            "stance": "STATUS_UPDATE",
            "confidence": "HIGH",
            "supporting_evidence_ids": candidate.blocker_evidence_ids,
        },
    ]
    if changed:
        claims.append(
            {
                "claim_text": f"What may have changed: {changed}",
                "stance": "STATUS_UPDATE" if internal else "UNCERTAIN",
                "confidence": "MEDIUM" if internal else "LOW",
                "supporting_evidence_ids": internal,
                "uncertainty": "An assessment, not an established organizational fact.",
            }
        )
    output = PrimaryOutput.model_validate(
        {
            "answer_summary": (
                f"Reconsideration candidate ({final.value.replace('_', ' ').lower()}): "
                f"a proposal that was {candidate.outcome.value.lower()}."
            ),
            "status": "INSUFFICIENT_EVIDENCE"
            if final == Assessment.INSUFFICIENT_EVIDENCE
            else "PARTIALLY_SUPPORTED",
            "claims": claims,
            "missing_information": missing,
            "timeline_events": [
                {
                    "event_text": "Proposed",
                    "state": "PROPOSAL",
                    "confidence": "HIGH",
                    "evidence_ids": candidate.proposal_evidence_ids,
                },
                {
                    "event_text": candidate.outcome.value.capitalize(),
                    "state": "OBJECTION",
                    "confidence": "HIGH",
                    "evidence_ids": candidate.outcome_evidence_ids,
                },
                *(
                    [
                        {
                            "event_text": "Later internal evidence",
                            "state": "STATUS_UPDATE",
                            "confidence": "MEDIUM",
                            "evidence_ids": internal,
                        }
                    ]
                    if internal
                    else []
                ),
            ],
        }
    )
    validated = receipt_validator.validate_primary(
        conn, output, query=f"Reconsideration: {candidate.proposal}", visible_ids=visible
    )
    failing = [
        ReviewObjection(text=c.note, severity=Confidence.MEDIUM, evidence_ids=c.evidence_ids)
        for c in checks
        if c.answered and c.passed is False and c.note
    ]
    review = ReviewInfo(
        risk_level="HIGH",
        risk_triggers=["reconsideration candidate"],
        skeptic_ran=True,
        counter_queries=counter.queries_run,
        counter_units_examined=len(counter.new_evidence_ids),
        objections=failing,
        reconciled=False,
        completed=True,
    )
    validated = validated.model_copy(
        update={"review": receipt_validator.sanitize_review(conn, review, visible)}
    )
    case_id = uuid.uuid4().hex
    repository.save_case(
        conn,
        case_id=case_id,
        query=validated.query,
        receipt_json=validated.model_dump_json(),
        created_at=receipt_validator.now_iso(),
        evidence_usage=validated.evidence_ids(),
    )
    return case_id


def _store_finding(conn: sqlite3.Connection, stored: StoredFinding, when: str | None) -> str:
    finding_id = f"RC-{uuid.uuid4().hex[:10]}"
    created = receipt_validator.now_iso()
    label = stored.assessment.value.replace("_", " ").lower()
    conn.execute(
        "INSERT INTO pulse_findings (finding_id, category, title, summary, status, finding_json, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            finding_id,
            CATEGORY,
            stored.proposal[:160],
            f"{stored.outcome.value.lower()} idea; assessment: {label}",
            stored.assessment.value,
            stored.model_dump_json(),
            created,
        ),
    )
    for evidence_id in sorted(stored.evidence_ids()):
        conn.execute(
            "INSERT OR IGNORE INTO finding_evidence (finding_id, evidence_id) VALUES (?, ?)",
            (finding_id, evidence_id),
        )
    _ = when
    return finding_id


def _clear_previous(
    conn: sqlite3.Connection, *, keep_finding_ids: set[str] | None = None
) -> None:
    keep_finding_ids = keep_finding_ids or set()
    for row in conn.execute(
        "SELECT finding_id, finding_json FROM pulse_findings WHERE category = ?", (CATEGORY,)
    ).fetchall():
        if row["finding_id"] in keep_finding_ids:
            continue
        case_id = json.loads(row["finding_json"]).get("case_id")
        if case_id:
            conn.execute("DELETE FROM case_evidence WHERE case_id = ?", (case_id,))
            conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM finding_evidence WHERE finding_id = ?", (row["finding_id"],))
        conn.execute("DELETE FROM pulse_findings WHERE finding_id = ?", (row["finding_id"],))


# --------------------------------------------------------------- serving


def load_findings(conn: sqlite3.Connection, source_dir: Path) -> list[FindingCard]:
    """Hydrate stored findings, re-checking every id against the database now.
    A finding whose proposal, outcome or blocker evidence has since been
    removed is not shown, and neither is its stale text."""
    curated = {s.signal_id: s for s in signals.load_signals(source_dir)}
    cards: list[FindingCard] = []
    rows = conn.execute(
        "SELECT finding_id, finding_json, created_at FROM pulse_findings WHERE category = ? "
        "ORDER BY created_at, finding_id",
        (CATEGORY,),
    ).fetchall()
    for row in rows:
        stored = StoredFinding.model_validate(json.loads(row["finding_json"]))
        records = {r.evidence_id: r for r in hydrate(conn, sorted(stored.evidence_ids()))}

        def cites(ids: list[str], records=records) -> list[Citation]:
            return [Citation.from_record(records[i]) for i in ids if i in records]

        proposal, outcome, blocker = (
            cites(stored.proposal_evidence_ids),
            cites(stored.outcome_evidence_ids),
            cites(stored.blocker_evidence_ids),
        )
        if not (proposal and outcome and blocker):
            continue
        cards.append(
            FindingCard(
                finding_id=row["finding_id"],
                proposal=stored.proposal,
                outcome=stored.outcome,
                proposal_citations=proposal,
                outcome_citations=outcome,
                blocker=stored.blocker,
                blocker_category=stored.blocker_category.value,
                blocker_citations=blocker,
                monitorable_condition=stored.monitorable_condition,
                changed_condition=stored.changed_condition,
                internal_change_citations=cites(stored.internal_change_evidence_ids),
                external_signals=[curated[i] for i in stored.external_signal_ids if i in curated],
                current_state_citations=cites(stored.current_state_evidence_ids),
                assessment=stored.assessment,
                assessment_rationale=stored.assessment_rationale,
                unestablished=stored.unestablished,
                next_check=stored.next_check,
                checks=stored.checks,
                case_id=stored.case_id,
                created_at=row["created_at"],
            )
        )
    return cards
