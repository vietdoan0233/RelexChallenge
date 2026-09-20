export type Stance =
  | 'PROPOSAL'
  | 'ASSUMPTION'
  | 'OBJECTION'
  | 'AGREEMENT'
  | 'COMMITMENT'
  | 'STATUS_UPDATE'
  | 'IMPLEMENTATION_EVIDENCE'
  | 'SUPERSEDED'
  | 'UNCERTAIN'

export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW'

export type CaseStatus =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'CONFLICTING_EVIDENCE'
  | 'INSUFFICIENT_EVIDENCE'

// Every field below is hydrated from the database by the backend; the UI
// only renders it and never composes provenance itself.
export interface Citation {
  evidence_id: string
  document_id: string
  filename: string
  document_type: string
  document_title: string | null
  event_date: string | null
  timestamp_text: string | null
  speaker_sender: string | null
  thread_context: string | null
  raw_text: string
  is_truncated: boolean
  // The AUTHOR/SPEAKER participant for this unit, or null for an anonymous
  // label ("Me", "Them", a Teams guest) or unresolved free text. Lets
  // speaker_sender link to that participant's profile (#/people/:subjectId).
  subject_id: string | null
}

export interface ReceiptClaim {
  claim_text: string
  stance: Stance
  confidence: Confidence
  uncertainty: string | null
  support: Citation[]
  conflicts: Citation[]
}

export interface ReceiptTimelineEvent {
  event_text: string
  state: Stance
  confidence: Confidence
  event_date: string | null
  citations: Citation[]
}

export interface ReviewObjection {
  text: string
  severity: Confidence
  evidence_ids: string[]
}

export interface ReviewInfo {
  risk_level: string
  risk_triggers: string[]
  skeptic_ran: boolean
  counter_queries: number
  counter_units_examined: number
  counter_evidence_ids: string[]
  objections: ReviewObjection[]
  reconciled: boolean
  completed: boolean
}

export interface CaseReceipt {
  case_id: string
  query: string
  status: CaseStatus
  answer_summary: string
  claims: ReceiptClaim[]
  conflict_resolution: string | null
  timeline_events: ReceiptTimelineEvent[]
  missing_information: string[]
  related_questions: string[]
  validation: {
    rejected_evidence_ids: string[]
    dropped_claims: number
    dropped_timeline_events: number
    downgraded_claims: number
    notes: string[]
  }
  review: ReviewInfo
  created_at: string
}

export interface EvidenceView {
  citation: Citation
  context_before: Citation[]
  context_after: Citation[]
}

export type PrivacyState = 'ACTIVE' | 'PSEUDONYMISED'

export interface PersonSummary {
  subject_id: string
  display_alias: string
  privacy_state: PrivacyState
  display_name: string | null
  author_units: number
  speaker_units: number
  mentioned_units: number
}

export interface PseudonymisePreview {
  subject_id: string
  display_alias: string
  author_units: number
  speaker_units: number
  mentioned_units: number
  units_to_rewrite: number
  files_to_rewrite: number
  cases_to_invalidate: number
  findings_to_invalidate?: number
}

export interface PseudonymiseResult {
  operation_id: string
  subject_id: string
  display_alias: string
  privacy_state: PrivacyState
  files_rewritten: number
  units_rewritten: number
  cases_invalidated: number
  findings_invalidated?: number
  embeddings_regenerated: number
  embeddings_pending: number
  verification: Record<string, number>
  checks: Record<string, boolean>
  verified: boolean
  pseudonymised_at: string | null
}

export interface ReversalResult {
  operation_id: string
  subject_id: string
  display_alias: string
  privacy_state: PrivacyState
  files_restored: number
  verified: boolean
  verification: Record<string, number>
}

export interface ContributionEntry {
  evidence_id: string
  document_id: string
  document_type: string
  filename: string
  document_title: string | null
  relation: 'AUTHOR' | 'SPEAKER' | 'MENTIONED'
  event_date: string | null
  timestamp_text: string | null
  thread_context: string | null
  raw_text: string
  is_truncated: boolean
}

export interface PersonProfile {
  subject_id: string
  display_alias: string
  privacy_state: PrivacyState
  display_name: string | null
  author_units: number
  speaker_units: number
  mentioned_units: number
  pseudonymised_at: string | null
  verification_result: { counts?: Record<string, number>; checks?: Record<string, boolean> } | null
}

export type RadarAssessment =
  | 'STILL_BLOCKED'
  | 'PARTIALLY_CHANGED'
  | 'WORTH_REASSESSING'
  | 'INSUFFICIENT_EVIDENCE'

export interface ExternalSignal {
  signal_id: string
  title: string
  source: string
  published: string
  url: string | null
  summary: string
  categories: string[]
}

export interface RadarCheck {
  check: number
  answered: boolean
  passed: boolean | null
  note: string
  evidence_ids: string[]
}

export interface FindingCard {
  finding_id: string
  proposal: string
  outcome: 'REJECTED' | 'DEFERRED'
  proposal_citations: Citation[]
  outcome_citations: Citation[]
  blocker: string
  blocker_category: string
  blocker_citations: Citation[]
  monitorable_condition: string
  changed_condition: string | null
  internal_change_citations: Citation[]
  external_signals: ExternalSignal[]
  current_state_citations: Citation[]
  assessment: RadarAssessment
  assessment_rationale: string
  unestablished: string[]
  next_check: string
  checks: RadarCheck[]
  case_id: string
  created_at: string
}

export interface ArchiveStats {
  documents: number
  documents_by_type: Record<string, number>
  evidence_units: number
  people: number
  embeddings: number
  cases: number
  radar_findings: number
  first_date: string | null
  last_date: string | null
}

export interface RecentCase {
  case_id: string
  query: string
  status: CaseStatus | null
  claims: number
  created_at: string
}
