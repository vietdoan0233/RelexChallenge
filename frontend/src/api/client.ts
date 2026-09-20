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
  RecentDocument,
  UploadDocumentType,
  UploadResult,
} from '../types/api'

export class ApiError extends Error {
  status: number
  // The parsed JSON error body, for endpoints that return more than `detail`.
  body: unknown
  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // A FormData body needs the browser to set its own multipart boundary header.
  const isForm = init?.body instanceof FormData
  const response = await fetch(path, {
    ...init,
    headers: isForm ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    let parsed: unknown
    try {
      parsed = await response.json()
      const message = (parsed as { detail?: unknown } | null)?.detail
      if (typeof message === 'string') detail = message
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(response.status, detail, parsed)
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
  recentDocuments: (limit: number) => request<RecentDocument[]>(`/api/ingest/recent?limit=${limit}`),
  uploadEvidence: (documentType: UploadDocumentType, files: File[]) => {
    const form = new FormData()
    form.append('document_type', documentType)
    for (const file of files) form.append('files', file, file.name)
    return request<UploadResult>('/api/ingest/upload', { method: 'POST', body: form })
  },
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
