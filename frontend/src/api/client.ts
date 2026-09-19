import type {
  ArchiveStats,
  CaseReceipt,
  FindingCard,
  EvidenceView,
  PersonSummary,
  PurgePreview,
  PurgeResult,
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

export const api = {
  ask: (query: string) => request<CaseReceipt>('/api/cases/query', post({ query })),
  getCase: (caseId: string) => request<CaseReceipt>(`/api/cases/${encodeURIComponent(caseId)}`),
  getEvidence: (evidenceId: string) =>
    request<EvidenceView>(`/api/evidence/${encodeURIComponent(evidenceId)}`),
  people: () => request<PersonSummary[]>('/api/privacy/people'),
  preview: (personId: string) =>
    request<PurgePreview>('/api/privacy/preview', post({ person_id: personId })),
  stats: () => request<ArchiveStats>('/api/stats'),
  recentCases: () => request<RecentCase[]>('/api/cases?limit=6'),
  radar: () => request<FindingCard[]>('/api/radar'),
  purge: (personId: string) =>
    request<PurgeResult>('/api/privacy/purge', post({ person_id: personId, confirm: true })),
}
