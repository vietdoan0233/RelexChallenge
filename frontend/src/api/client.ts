import type {
  ArchiveStats,
  CaseReceipt,
  FindingCard,
  EvidenceView,
  PersonSummary,
  PurgePreview,
  PurgeResult,
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
  recentDocuments: (limit: number) => request<RecentDocument[]>(`/api/ingest/recent?limit=${limit}`),
  uploadEvidence: (documentType: UploadDocumentType, files: File[]) => {
    const form = new FormData()
    form.append('document_type', documentType)
    for (const file of files) form.append('files', file, file.name)
    return request<UploadResult>('/api/ingest/upload', { method: 'POST', body: form })
  },
  radar: () => request<FindingCard[]>('/api/radar'),
  purge: (personId: string) =>
    request<PurgeResult>('/api/privacy/purge', post({ person_id: personId, confirm: true })),
}
