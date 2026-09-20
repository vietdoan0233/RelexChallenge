import type { FindingCard, RadarCheck } from './types/api'

const DEMO_DATE = '2026-09-20T00:00:00Z'

function demoChecks(notes: string[] = []): RadarCheck[] {
  return Array.from({ length: 7 }, (_, index) => ({
    check: index + 1,
    answered: Boolean(notes[index]),
    passed: notes[index] ? true : null,
    note: notes[index] ?? 'Not evaluated in the demo set.',
    evidence_ids: [],
  }))
}

function demoFinding(
  finding_id: string,
  proposal: string,
  outcome: FindingCard['outcome'],
  blocker: string,
  blocker_category: string,
  assessment: FindingCard['assessment'],
  assessment_rationale: string,
  changed_condition: string | null,
  monitorable_condition: string,
  unestablished: string[],
  next_check: string,
  checkNotes: string[] = [],
): FindingCard {
  return {
    finding_id,
    proposal,
    outcome,
    proposal_citations: [],
    outcome_citations: [],
    blocker,
    blocker_category,
    blocker_citations: [],
    monitorable_condition,
    changed_condition,
    internal_change_citations: [],
    external_signals: [],
    current_state_citations: [],
    assessment,
    assessment_rationale,
    unestablished,
    next_check,
    checks: demoChecks(checkNotes),
    case_id: `DEMO-CASE-${finding_id.slice(-3)}`,
    created_at: DEMO_DATE,
  }
}

// The current product build uses a fixed five-card demo set so Radar is
// populated even when the reasoning service has not produced live findings.
// These are intentionally presented as candidates, not verified conclusions.
export const DEMO_RADAR_FINDINGS: FindingCard[] = [
  demoFinding(
    'DEMO-RADAR-001',
    'Reopen scoped test-environment access for the partner team',
    'REJECTED',
    'The original access request could expose fresh configuration outside the approved boundary.',
    'SECURITY / COMPLIANCE',
    'WORTH_REASSESSING',
    'A narrower access model may address the original blocker, but the current approval and security evidence still needs verification.',
    'A scoped test role and approved extracts may now limit access without exposing fresh configuration.',
    'A security-reviewed test role with an approved data boundary is documented.',
    ['The exact permitted dataset is not established.', 'Security approval and expiry conditions are not established.'],
    'Confirm the scoped role, dataset boundary, owner, and expiry with Security and the system owner.',
    ['The proposal was genuinely rejected.', 'The blocker was explicitly stated.', 'No secondary blocker was found.', 'The changed condition directly addresses the blocker.'],
  ),
  demoFinding(
    'DEMO-RADAR-002',
    'Pilot shelf-life mapping with a smaller store cohort',
    'DEFERRED',
    'The original pilot required more master-data preparation and operational capacity than the team could commit to.',
    'CAPACITY / EFFORT',
    'PARTIALLY_CHANGED',
    'Some preparation work appears to be in place, but the smaller pilot scope and current ownership are not confirmed.',
    'Master-data preparation has progressed, while the original full-cohort effort may be reducible.',
    'A named owner, cohort size, and success criteria are agreed.',
    ['The current master-data quality is not established.'],
    'Validate a smaller cohort and obtain an explicit owner commitment before reopening the proposal.',
    ['The proposal was genuinely deferred.', 'The blocker was explicitly stated.'],
  ),
  demoFinding(
    'DEMO-RADAR-003',
    'Grant partner read access to the fresh configuration',
    'REJECTED',
    'The partner access path was blocked by unresolved security and data-handling concerns.',
    'SECURITY / COMPLIANCE',
    'STILL_BLOCKED',
    'No verified change removes the original security boundary or establishes a safe replacement.',
    null,
    'A security-approved access pattern and data-handling agreement are in force.',
    ['No current approval or replacement access pattern is evidenced.'],
    'Recheck the security review and data-handling agreement before considering the request again.',
    ['The proposal was genuinely rejected.', 'The blocker was explicitly stated.'],
  ),
  demoFinding(
    'DEMO-RADAR-004',
    'Move cohort reporting to a live operational basis',
    'DEFERRED',
    'The organization lacked enough reliable operational data to support the proposed reporting basis.',
    'INSUFFICIENT DATA',
    'INSUFFICIENT_EVIDENCE',
    'The archive does not establish whether the required operational data is now complete and reliable.',
    null,
    'A recent reconciled sample demonstrates that the required operational fields are complete.',
    ['The latest reconciled sample is not available.'],
    'Request a dated sample and compare it with the reporting fields required by the proposal.',
    ['The proposal was genuinely deferred.', 'The blocker was explicitly stated.'],
  ),
  demoFinding(
    'DEMO-RADAR-005',
    'Create a separate UAT environment for external testing',
    'DEFERRED',
    'The separate environment was deferred because its setup cost and ownership were not justified at the time.',
    'COST / VENDOR',
    'PARTIALLY_CHANGED',
    'Environment requirements may have changed, but current cost, ownership, and delivery timing remain unclear.',
    'The test process has matured, although the separate environment decision has not been revisited with current estimates.',
    'A current estimate shows the environment is affordable and has an accountable owner.',
    ['No current cost estimate or owner is established.'],
    'Obtain a current estimate and owner, then compare it with the risk of continued shared-environment testing.',
    ['The proposal was genuinely deferred.', 'The blocker was explicitly stated.'],
  ),
]
