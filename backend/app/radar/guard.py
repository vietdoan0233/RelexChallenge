"""Deterministic guard for Radar findings.

The model proposes an assessment; this module decides what is allowed to be
shown. It enforces the Radar's promises in code rather than in a prompt:
bounded language, receipts for every changed-condition claim, and visible
missing information.
"""

import re

from app.radar.schemas import Assessment, AssessmentOut, CheckResult, RadarVerdict

# Wording stronger than "worth reassessing". Kept as a regex over phrases the
# Radar must never emit without new internal evidence.
_OVERREACH = re.compile(
    r"\b(?:should|must|ought)\b"
    r"|\b(?:recommend|advis|suggest|urg)\w*"
    r"|\b(?:pursue|proceed|greenlight|green[- ]?light|let'?s)\b"
    r"|\bgo\s+(?:ahead|for\s+it)\b"
    r"|\bapprove\b|\bfund\s+(?:it|this)\b"
    r"|\b(?:is|are|now)\s+(?:now\s+)?(?:approved|funded|safe|ready|justified|the\s+right)\b"
    r"|\bstrategic(?:ally)?\b|\bdefinitely\b|\bmakes\s+sense\s+to\b|\bthe\s+right\s+time\b",
    re.IGNORECASE,
)
WITHHELD = "Wording withheld: the Radar states only that a blocker may have changed."

# What the archive can almost never establish about reopening an idea, and
# which the card must therefore always show as unknown.
DEFAULT_UNESTABLISHED = (
    "No internal evidence establishes a budget, an owner, or an approval to reopen this idea."
)
EXTERNAL_ONLY_UNESTABLISHED = (
    "No internal evidence shows the organization's current position on this idea."
)


def is_overreach(text: str | None) -> bool:
    return bool(text and _OVERREACH.search(text))


def bounded(text: str | None, notes: list[str]) -> str | None:
    """Replace narrative that overreaches, and say that it was replaced."""
    if text and is_overreach(text):
        notes.append("overreaching wording was withheld")
        return WITHHELD
    return text


def _failed(checks: list[CheckResult], number: int) -> bool:
    return any(c.check == number and c.answered and c.passed is False for c in checks)


def finalize(
    assessed: AssessmentOut,
    verdict: RadarVerdict,
    *,
    valid_internal: list[str],
    valid_signals: list[str],
) -> tuple[Assessment, list[str], list[str]]:
    """The assessment that may be shown, the missing-information list, notes."""
    notes: list[str] = []
    result = assessed.assessment
    receipts = bool(valid_internal or valid_signals)

    # A claim that a condition changed needs a receipt for the change.
    if result in (Assessment.WORTH_REASSESSING, Assessment.PARTIALLY_CHANGED) and not receipts:
        result = Assessment.INSUFFICIENT_EVIDENCE
        notes.append("no receipt for a changed condition: assessment lowered")

    # Check 4: the new signal must address the original blocker.
    if result == Assessment.WORTH_REASSESSING and _failed(verdict.checks, 4):
        result = Assessment.PARTIALLY_CHANGED
        notes.append("the change does not directly address the blocker: assessment lowered")
    # Check 6: recent internal evidence argues against reopening.
    if result in (Assessment.WORTH_REASSESSING, Assessment.PARTIALLY_CHANGED) and _failed(
        verdict.checks, 6
    ):
        result = Assessment.STILL_BLOCKED
        notes.append("recent internal evidence argues against reopening: assessment lowered")

    missing: list[str] = []
    for item in assessed.unestablished:
        if is_overreach(item):
            # Dropped, not replaced: a "wording withheld" bullet under
            # "unestablished" would read as a missing fact.
            notes.append("an overreaching missing-information line was dropped")
        elif item:
            missing.append(item)
    for check in verdict.checks:
        if not check.answered:
            missing.append(
                f"Skeptic check {check.check} could not be answered: {check.note}".strip()
            )
    if result in (Assessment.WORTH_REASSESSING, Assessment.PARTIALLY_CHANGED):
        if not any(re.search(r"budget|owner|approv", m, re.IGNORECASE) for m in missing):
            missing.append(DEFAULT_UNESTABLISHED)
        if not valid_internal and valid_signals:
            missing.append(EXTERNAL_ONLY_UNESTABLISHED)
    return result, list(dict.fromkeys(missing)), notes
