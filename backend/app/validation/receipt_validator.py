"""Deterministic receipt validation (CLAUDE.md 15).

Runs after the model and before anything reaches the UI. The model is an
interpreter; this module is what makes its output safe to show:

* every cited id must exist in the database, be undeleted, and (during a
  Case run) have been in the evidence the model was actually shown;
* a claim with no valid support is dropped rather than shown unsupported;
* every displayed citation field is re-read from the database.

Prefer failing a claim safely over showing unsupported provenance.
"""

import re
import sqlite3
from datetime import UTC, datetime

from app.core.enums import CaseStatus, Confidence, Stance
from app.retrieval import context
from app.retrieval.records import EvidenceRecord, hydrate
from app.schemas.reasoning import PrimaryOutput
from app.schemas.receipt import (
    CaseReceipt,
    Citation,
    EvidenceView,
    ReceiptClaim,
    ReceiptTimelineEvent,
    ReviewInfo,
    ReviewObjection,
    ValidatedClaim,
    ValidatedReceipt,
    ValidatedTimelineEvent,
    ValidationReport,
)

# Ids belong in the id fields. A model that pastes "[EV-...]" into prose leaves
# noise in the UI, and any id it names there was never validated -- so strip it.
_PROSE_ID = re.compile(r"\s*\[?\bEV-[^\s\]\[,;)]+\]?")


def clean_prose(text: str | None) -> str | None:
    if text is None:
        return None
    return re.sub(r"\s{2,}", " ", _PROSE_ID.sub("", text)).strip()


# Wording sent "for signature" is a draft. A claim that quotes it as what was
# signed, at high confidence, asserts something the archive cannot show unless
# the executed document is itself in it.
_DRAFT_MARKER = re.compile(
    r"for (?:your )?(?:signature|signing|review)|please sign|\bdraft\b|proposed wording",
    re.IGNORECASE,
)
_EXECUTED_WORD = re.compile(r"\b(?:signed|executed)\b", re.IGNORECASE)
_QUOTED = re.compile(r"[\"\u201c\u201d]")
DRAFT_NOTE = (
    "The quoted wording is the text sent for signature; the executed document is not in the "
    "archive, so it cannot be confirmed as identical."
)

EMPTY_SUMMARY = "See the claims below for what the evidence supports."

NO_SUPPORT_SUMMARY = (
    "No claim could be supported by verified evidence. See missing information for what "
    "the archive does not establish."
)


def valid_ids(conn: sqlite3.Connection, ids: set[str], visible_ids: set[str] | None) -> set[str]:
    """Ids that exist now and, when a visibility set is given, were shown."""
    candidates = ids if visible_ids is None else ids & visible_ids
    return {r.evidence_id for r in hydrate(conn, sorted(candidates))}


def validate_primary(
    conn: sqlite3.Connection,
    output: PrimaryOutput,
    *,
    query: str,
    visible_ids: set[str] | None,
) -> ValidatedReceipt:
    referenced: set[str] = set()
    for claim in output.claims:
        referenced.update(claim.supporting_evidence_ids, claim.conflicting_evidence_ids)
    for event in output.timeline_events:
        referenced.update(event.evidence_ids)

    good = valid_ids(conn, referenced, visible_ids)
    records = {r.evidence_id: r for r in hydrate(conn, sorted(good))}
    report = ValidationReport(rejected_evidence_ids=sorted(referenced - good))

    claims: list[ValidatedClaim] = []
    for claim in output.claims:
        support = _keep(claim.supporting_evidence_ids, good)
        conflicts = _keep(claim.conflicting_evidence_ids, good)
        claim_text = clean_prose(claim.claim_text)
        if not claim_text:
            # A claim that was only an id has no statement to show.
            report.dropped_claims += 1
            continue
        if not support and claim.stance != Stance.UNCERTAIN:
            report.dropped_claims += 1
            continue
        confidence = claim.confidence
        # A truncated unit is incomplete evidence: never let a claim rest at
        # high confidence on cut-off text alone.
        if support and all(records[i].is_truncated for i in support):
            if confidence != Confidence.LOW:
                confidence = Confidence.LOW
                report.downgraded_claims += 1
                report.notes.append("claim rests only on truncated evidence; confidence capped")
        uncertainty = clean_prose(claim.uncertainty)
        if (
            _QUOTED.search(claim_text)
            and _EXECUTED_WORD.search(claim_text)
            and any(_DRAFT_MARKER.search(records[i].raw_text) for i in support)
        ):
            if confidence == Confidence.HIGH:
                confidence = Confidence.MEDIUM
                report.downgraded_claims += 1
            if not uncertainty or DRAFT_NOTE not in uncertainty:
                uncertainty = f"{uncertainty} {DRAFT_NOTE}".strip() if uncertainty else DRAFT_NOTE
            report.notes.append("quoted wording is a draft sent for signature; confidence capped")
        claims.append(
            ValidatedClaim(
                claim_text=claim_text,
                stance=claim.stance,
                confidence=confidence,
                supporting_evidence_ids=support,
                conflicting_evidence_ids=conflicts,
                uncertainty=uncertainty,
            )
        )

    events: list[ValidatedTimelineEvent] = []
    for event in output.timeline_events:
        ids = _keep(event.evidence_ids, good)
        event_text = clean_prose(event.event_text)
        if not ids or not event_text:
            report.dropped_timeline_events += 1
            continue
        events.append(
            ValidatedTimelineEvent(
                event_text=event_text,
                state=event.state,
                confidence=event.confidence,
                evidence_ids=ids,
            )
        )
    events.sort(key=lambda e: _event_date(e.evidence_ids, records) or "9999-99-99")

    status = output.status
    summary = clean_prose(output.answer_summary) or EMPTY_SUMMARY
    if not any(c.supporting_evidence_ids for c in claims):
        status = CaseStatus.INSUFFICIENT_EVIDENCE
        summary = NO_SUPPORT_SUMMARY
    elif report.dropped_claims and status == CaseStatus.SUPPORTED:
        status = CaseStatus.PARTIALLY_SUPPORTED
        report.notes.append("status lowered: unsupported claims were dropped")
    if report.rejected_evidence_ids:
        report.notes.append("cited ids that do not exist or were not visible were rejected")

    return ValidatedReceipt(
        query=query,
        status=status,
        answer_summary=summary,
        claims=claims,
        conflict_resolution=clean_prose(output.conflict_resolution),
        timeline_events=events,
        missing_information=_clean_list(output.missing_information),
        related_questions=_clean_list(output.related_questions),
        validation=report,
    )


def sanitize_review(
    conn: sqlite3.Connection, review: ReviewInfo, visible_ids: set[str] | None
) -> ReviewInfo:
    """Keep only counter-evidence ids that exist (and were shown), and
    strip ids from the Skeptic's prose, exactly as for claims."""
    ids = set(review.counter_evidence_ids)
    for objection in review.objections:
        ids.update(objection.evidence_ids)
    good = valid_ids(conn, ids, visible_ids)
    objections = []
    for objection in review.objections:
        text = clean_prose(objection.text)
        if not text:
            continue
        objections.append(
            ReviewObjection(
                text=text,
                severity=objection.severity,
                evidence_ids=_keep(objection.evidence_ids, good),
            )
        )
    return review.model_copy(
        update={
            "counter_evidence_ids": _keep(review.counter_evidence_ids, good),
            "objections": objections,
        }
    )


def hydrate_receipt(
    conn: sqlite3.Connection, validated: ValidatedReceipt, *, case_id: str, created_at: str
) -> CaseReceipt:
    """Serve a stored receipt, re-checking every id against the database now.

    A unit deleted after the Case was stored simply fails to hydrate; a
    claim that loses all its support is dropped. Deleted evidence can
    therefore never render, even from a cached Case.
    """
    every = {i for ids in validated.evidence_ids().values() for i in ids}
    existing = valid_ids(conn, every, None)
    review = validated.review.model_copy(
        update={
            "counter_evidence_ids": _keep(validated.review.counter_evidence_ids, existing),
            "objections": [
                o.model_copy(update={"evidence_ids": _keep(o.evidence_ids, existing)})
                for o in validated.review.objections
            ],
        }
    )
    records = {r.evidence_id: r for r in hydrate(conn, sorted(every))}

    claims: list[ReceiptClaim] = []
    for claim in validated.claims:
        support = [
            Citation.from_record(records[i]) for i in claim.supporting_evidence_ids if i in records
        ]
        if not support and claim.stance != Stance.UNCERTAIN:
            continue
        claims.append(
            ReceiptClaim(
                claim_text=claim.claim_text,
                stance=claim.stance,
                confidence=claim.confidence,
                uncertainty=claim.uncertainty,
                support=support,
                conflicts=[
                    Citation.from_record(records[i])
                    for i in claim.conflicting_evidence_ids
                    if i in records
                ],
            )
        )

    events = []
    for event in validated.timeline_events:
        cites = [Citation.from_record(records[i]) for i in event.evidence_ids if i in records]
        if cites:
            events.append(
                ReceiptTimelineEvent(
                    event_text=event.event_text,
                    state=event.state,
                    confidence=event.confidence,
                    event_date=_event_date(event.evidence_ids, records),
                    citations=cites,
                )
            )

    status, summary = validated.status, validated.answer_summary
    if not any(c.support for c in claims):
        status, summary = CaseStatus.INSUFFICIENT_EVIDENCE, NO_SUPPORT_SUMMARY

    return CaseReceipt(
        case_id=case_id,
        query=validated.query,
        status=status,
        answer_summary=summary,
        claims=claims,
        conflict_resolution=validated.conflict_resolution,
        timeline_events=events,
        missing_information=validated.missing_information,
        related_questions=validated.related_questions,
        validation=validated.validation,
        review=review,
        created_at=created_at,
    )


def evidence_view(conn: sqlite3.Connection, evidence_id: str) -> EvidenceView | None:
    """A cited unit with its neighbour context, all read from the database."""
    windows = context.expand(conn, [evidence_id])
    if not windows:
        return None
    window = windows[0]
    records = {r.evidence_id: r for r in hydrate(conn, list(window.unit_ids))}
    position = window.unit_ids.index(evidence_id)
    return EvidenceView(
        citation=Citation.from_record(records[evidence_id]),
        context_before=[Citation.from_record(records[i]) for i in window.unit_ids[:position]],
        context_after=[Citation.from_record(records[i]) for i in window.unit_ids[position + 1 :]],
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_list(items: list[str]) -> list[str]:
    return [cleaned for item in items if (cleaned := clean_prose(item))]


def _keep(ids: list[str], good: set[str]) -> list[str]:
    return [i for i in dict.fromkeys(ids) if i in good]


def _event_date(ids: list[str], records: dict[str, EvidenceRecord]) -> str | None:
    dates = [records[i].event_date for i in ids if i in records and records[i].event_date]
    return min(dates) if dates else None
