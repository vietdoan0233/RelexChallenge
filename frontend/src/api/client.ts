import type {
  ArchiveStats,
  CaseReceipt,
  FindingCard,
  EvidenceView,
  PersonProfile,
  PersonSummary,
  PseudonymisePreview,
  PseudonymiseResult,
  ContributionEntry,
  ReversalResult,
  RecentCase,
} from '../types/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

// The admin token gates POST /api/privacy/pseudonymise and the admin
// reversal endpoint only; it is never persisted (no localStorage/
// sessionStorage) and lives only in the current page's memory, cleared on
// reload -- consistent with treating it as a credential, not a preference.
const withAdmin = (body: unknown, token: string): RequestInit => ({
  method: 'POST',
  body: JSON.stringify(body),
  headers: { Authorization: `Bearer ${token}` },
})

export const api = {
  ask: (query: string) => request<CaseReceipt>('/api/cases/query', post({ query })),
  getCase: (caseId: string) => request<CaseReceipt>(`/api/cases/${encodeURIComponent(caseId)}`),
  getEvidence: (evidenceId: string) =>
    request<EvidenceView>(`/api/evidence/${encodeURIComponent(evidenceId)}`),
  people: () => request<PersonSummary[]>('/api/privacy/people'),
  preview: (subjectId: string) =>
    request<PseudonymisePreview>('/api/privacy/preview', post({ subject_id: subjectId })),
  stats: () => request<ArchiveStats>('/api/stats'),
  recentCases: () => request<RecentCase[]>('/api/cases?limit=6'),
  radar: () => request<FindingCard[]>('/api/radar'),
  pseudonymise: (subjectId: string, adminToken: string) =>
    request<PseudonymiseResult>(
      '/api/privacy/pseudonymise',
      withAdmin({ subject_id: subjectId }, adminToken)
    ),
  getPerson: (subjectId: string) => request<PersonProfile>(`/api/people/${encodeURIComponent(subjectId)}`),
  getPersonHistory: (subjectId: string) =>
    request<ContributionEntry[]>(`/api/people/${encodeURIComponent(subjectId)}/history`),
  reversePseudonymisation: (subjectId: string, adminToken: string, confirm: boolean) =>
    request<ReversalResult>(
      `/api/admin/people/${encodeURIComponent(subjectId)}/reverse-pseudonymisation`,
      withAdmin({ confirm }, adminToken)
    ),
}
