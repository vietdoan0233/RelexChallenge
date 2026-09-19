import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { DragEvent, ReactNode } from 'react'
import { ApiError, api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconFile,
  IconMail,
  IconMic,
  IconShield,
  IconUpload,
  IconX,
} from '../components/icons'
import { Spinner, Tick } from '../components/ui'
import { btnPrimary, btnSecondary, card } from '../lib'
import type { UploadDocumentType, UploadFailure, UploadResult } from '../types/api'

// Mirrors the backend limits (app/ingestion/upload.py). The backend is the
// authority; these only save a round trip for an obviously bad selection.
const MAX_FILES = 20
const MAX_FILE_BYTES = 1024 * 1024

const TYPES: { value: UploadDocumentType; label: string; blurb: string; icon: ReactNode }[] = [
  {
    value: 'email',
    label: 'Email',
    blurb: 'An exported thread with From: and Date: headers.',
    icon: <IconMail size={22} />,
  },
  {
    value: 'transcript',
    label: 'Meeting / conversation',
    blurb: 'A Meeting: / Date: / Attendees: header, then the transcript or Me: / Them: dialogue.',
    icon: <IconMic size={22} />,
  },
  {
    value: 'report',
    label: 'Report',
    blurb: 'A status or steering report with From: and Date: headers.',
    icon: <IconFile size={22} />,
  },
]

const TYPE_LABEL: Record<string, string> = { EMAIL: 'Email', TRANSCRIPT: 'Meeting', REPORT: 'Report' }

// Rows exist only for documents the backend confirmed. They live in the query
// cache, so they last for the browser session and are never invented client-side.
interface AddedRow {
  document_id: string
  name: string
  type: string
  units: number
  keywordOnly: boolean
  addedAt: string
}

const formatSize = (bytes: number) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`)

const formatWhen = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

function problemWith(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.txt')) return 'Only .txt files are accepted.'
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_FILE_BYTES) return `Larger than ${MAX_FILE_BYTES / (1024 * 1024)} MB.`
  return null
}

interface UploadError {
  message: string
  failures: UploadFailure[]
}

function toUploadError(error: unknown): UploadError {
  if (error instanceof ApiError) {
    const failures = (error.body as { failures?: UploadFailure[] } | undefined)?.failures
    return { message: error.message, failures: Array.isArray(failures) ? failures : [] }
  }
  // fetch itself failed: the request may never have reached the archive.
  return { message: 'Could not reach the server. Nothing was confirmed as added.', failures: [] }
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-surface-2 px-4 py-3">
      <p className="text-2xl font-extrabold tabular-nums text-ink">{value.toLocaleString()}</p>
      <p className="text-xs font-bold text-ink-3">{label}</p>
    </div>
  )
}

function ResultPanel({ result }: { result: UploadResult }) {
  const emb = result.embeddings
  return (
    <section className={`${card} anim-fade-up space-y-5 p-6`} role="status" aria-live="polite">
      <div className="flex items-start gap-3">
        <Tick size={28} />
        <div>
          <h2 className="text-xl font-extrabold text-ink">
            Added to the archive: {result.documents_added} {result.documents_added === 1 ? 'document' : 'documents'}
          </h2>
          <p className="text-sm text-ink-2">
            The files are saved in the canonical source and the archive index has been rebuilt from it.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Documents added" value={result.documents_added} />
        <Stat label="Evidence units added" value={result.evidence_units_added} />
        <Stat label="Search index rows" value={result.fts_row_count} />
        <Stat label="Units with embeddings" value={emb.total_embeddings} />
      </div>

      {emb.status !== 'complete' && (
        <div className="flex gap-3 rounded-xl border border-warn/40 bg-warn-soft p-4 text-sm text-ink" role="alert">
          <IconAlert size={20} className="mt-0.5 shrink-0 text-warn" />
          <div>
            <p className="font-extrabold">{emb.status === 'skipped' ? 'Embeddings skipped' : 'Embeddings incomplete'}</p>
            <p className="text-ink-2">{emb.message}</p>
            <p className="mt-1 text-xs font-semibold text-ink-3">
              {emb.total_embeddings.toLocaleString()} of {emb.total_units.toLocaleString()} units have an embedding.
            </p>
          </div>
        </div>
      )}

      {result.files.some((f) => f.original_filename !== f.stored_filename) && (
        <p className="text-sm text-ink-2">
          {result.files
            .filter((f) => f.original_filename !== f.stored_filename)
            .map((f) => `“${f.original_filename}” was saved as ${f.stored_filename} to keep the archive unique.`)
            .join(' ')}
        </p>
      )}

      {result.parse_warnings.length > 0 && (
        <div className="rounded-xl bg-neutral-soft p-4 text-sm">
          <p className="font-extrabold text-ink">Parse warnings</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-2">
            {result.parse_warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <a href="#/" className={`${btnSecondary} w-fit`}>
        Ask about it <IconArrowRight size={16} />
      </a>
    </section>
  )
}

function ErrorPanel({ error }: { error: UploadError }) {
  return (
    <section className="anim-fade-up space-y-3 rounded-2xl border border-bad/40 bg-bad-soft p-5" role="alert">
      <div className="flex items-start gap-3">
        <IconAlert size={22} className="mt-0.5 shrink-0 text-bad" />
        <div>
          <h2 className="text-lg font-extrabold text-ink">Upload failed</h2>
          <p className="text-sm text-ink-2">{error.message}</p>
        </div>
      </div>
      {error.failures.length > 0 && (
        <ul className="space-y-1 pl-9 text-sm">
          {error.failures.map((f, i) => (
            <li key={`${f.filename}-${i}`}>
              <span className="font-bold text-ink">{f.filename}</span> <span className="text-ink-2">{f.error}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function StepHeading({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-6 place-items-center rounded-full bg-brand-soft text-xs font-extrabold text-brand-ink">{n}</span>
      <h2 className="text-sm font-extrabold text-ink">{children}</h2>
    </div>
  )
}

export function AddEvidencePage() {
  const queryClient = useQueryClient()
  const [documentType, setDocumentType] = useState<UploadDocumentType>('email')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })
  const history = useQuery<AddedRow[]>({
    queryKey: ['ingest-history'],
    queryFn: () => [],
    initialData: [],
    staleTime: Infinity,
    gcTime: Infinity,
  })

  const upload = useMutation({
    mutationFn: ({ type, list }: { type: UploadDocumentType; list: File[] }) => api.uploadEvidence(type, list),
    onSuccess: (result) => {
      setFiles([])
      const addedAt = new Date().toISOString()
      const keywordOnly = result.embeddings.status !== 'complete'
      const rows: AddedRow[] = result.files.map((f) => ({
        document_id: f.document_id,
        name: f.stored_filename,
        type: TYPE_LABEL[f.document_type] ?? f.document_type,
        units: f.evidence_units,
        keywordOnly,
        addedAt,
      }))
      queryClient.setQueryData<AddedRow[]>(['ingest-history'], (old) => [...rows, ...(old ?? [])].slice(0, 25))
      // The archive counts (header status, Ask page, this page) changed.
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const addFiles = (incoming: FileList | File[]) => {
    upload.reset()
    // A FileList is live: the picker is cleared right after this call and a drop's
    // list is only valid during the event, so copy it before the deferred update.
    const picked = Array.from(incoming)
    setFiles((current) => {
      const seen = new Set(current.map((f) => `${f.name}:${f.size}`))
      const fresh = picked.filter((f) => !seen.has(`${f.name}:${f.size}`))
      return [...current, ...fresh]
    })
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (!upload.isPending) addFiles(e.dataTransfer.files)
  }

  const problems = files.map(problemWith)
  const tooMany = files.length > MAX_FILES
  const canSubmit = files.length > 0 && !tooMany && problems.every((p) => p === null) && !upload.isPending
  const s = stats.data
  const typeLabel = TYPES.find((t) => t.value === documentType)!.label

  return (
    <div>
      <section className="hero-bg">
        <div className="mx-auto grid max-w-6xl items-center gap-8 px-4 pb-10 pt-12 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="anim-fade-up space-y-4">
            <h1 className="text-balance text-4xl font-extrabold leading-[1.08] tracking-tight text-brand-ink sm:text-5xl">
              Add evidence to the archive
            </h1>
            <p className="max-w-2xl text-pretty text-lg text-ink-2">
              Upload emails, meeting notes, reports and conversation transcripts. Each file is saved to the canonical
              archive and indexed, so it can be searched, cited and reasoned over exactly like the original evidence.
            </p>
          </div>
          <aside className={`${card} anim-fade-up flex gap-3 p-5`} style={{ animationDelay: '0.08s' }}>
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">
              <IconShield size={22} />
            </span>
            <div className="space-y-1">
              <p className="text-sm font-extrabold text-ink">Your data stays in your control</p>
              <p className="text-sm text-ink-2">
                Uploads join the same archive as the original evidence, so anyone named in them can later be redacted or
                deleted from the Privacy console.
              </p>
              <a href="#/privacy" className="inline-flex items-center gap-1 text-sm font-bold text-brand-ink hover:underline">
                Open Privacy console <IconArrowRight size={14} />
              </a>
            </div>
          </aside>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-6 px-4 pb-16 pt-2">
        <form
          className={`${card} overflow-hidden`}
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) upload.mutate({ type: documentType, list: files })
          }}
        >
          <div className="border-b border-line px-6">
            <span className="inline-block border-b-2 border-brand py-3.5 text-sm font-extrabold text-brand-ink">Upload files</span>
          </div>

          <div className="space-y-7 p-6">
            <fieldset className="space-y-3" disabled={upload.isPending}>
              <legend className="mb-3">
                <StepHeading n={1}>What are you adding?</StepHeading>
              </legend>
              <div className="grid gap-3 md:grid-cols-3">
                {TYPES.map((t) => {
                  const on = documentType === t.value
                  return (
                    <label
                      key={t.value}
                      className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border p-5 text-center transition-all duration-200 has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand/25 ${
                        on ? 'border-brand bg-brand-soft shadow-card' : 'border-line bg-surface hover:border-brand hover:shadow-card'
                      }`}
                    >
                      <input
                        type="radio"
                        name="document_type"
                        value={t.value}
                        checked={on}
                        onChange={() => setDocumentType(t.value)}
                        className="sr-only"
                      />
                      <span className={`grid size-11 place-items-center rounded-full ${on ? 'bg-surface text-brand-ink' : 'bg-surface-2 text-ink-3'}`}>
                        {t.icon}
                      </span>
                      <span className="text-sm font-extrabold text-ink">{t.label}</span>
                      <span className="text-xs text-ink-2">{t.blurb}</span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <fieldset className="space-y-3" disabled={upload.isPending}>
              <legend className="mb-3">
                <StepHeading n={2}>Choose {typeLabel.toLowerCase()} files</StepHeading>
              </legend>
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`grid place-items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-9 text-center transition-colors duration-200 ${
                  dragging ? 'border-brand bg-brand-soft' : 'border-line bg-surface-2'
                }`}
              >
                <span className="grid size-12 place-items-center rounded-full bg-surface text-brand-ink shadow-card">
                  <IconUpload size={24} />
                </span>
                <p className="text-sm font-semibold text-ink-2">Drag and drop .txt files here, or</p>
                <button type="button" className={btnSecondary} onClick={() => picker.current?.click()}>
                  Choose .txt files
                </button>
                <input
                  ref={picker}
                  type="file"
                  accept=".txt,text/plain"
                  multiple
                  className="sr-only"
                  tabIndex={-1}
                  aria-label="Choose .txt files"
                  onChange={(e) => {
                    if (e.target.files) addFiles(e.target.files)
                    e.target.value = ''
                  }}
                />
                <p className="text-xs text-ink-3">
                  Up to {MAX_FILES} files · {MAX_FILE_BYTES / (1024 * 1024)} MB each · plain text only
                </p>
              </div>

              {files.length > 0 && (
                <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line" aria-label="Selected files">
                  {files.map((file, i) => (
                    <li key={`${file.name}:${file.size}`} className="flex items-center justify-between gap-3 bg-surface px-4 py-2.5 text-sm">
                      <span className="flex min-w-0 items-center gap-3">
                        <IconFile size={18} className="shrink-0 text-ink-3" />
                        <span className="min-w-0">
                          <span className="block truncate font-bold text-ink">{file.name}</span>
                          {problems[i] && <span className="block text-xs font-semibold text-bad">{problems[i]}</span>}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-3">
                        <span className="text-xs text-ink-3">{formatSize(file.size)}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${file.name}`}
                          className="grid size-8 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-neutral-soft hover:text-ink"
                          onClick={() => setFiles((current) => current.filter((_, j) => j !== i))}
                        >
                          <IconX size={16} />
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {tooMany && <p className="text-sm font-semibold text-bad">Select at most {MAX_FILES} files per upload.</p>}
            </fieldset>

            <div className="flex flex-wrap items-center gap-4">
              <button type="submit" className={btnPrimary} disabled={!canSubmit}>
                {upload.isPending ? (
                  <>
                    <Spinner /> Adding to the archive…
                  </>
                ) : (
                  <>
                    <IconUpload size={18} />
                    {files.length > 0 ? `Add ${files.length} ${files.length === 1 ? 'file' : 'files'} to the archive` : 'Add to the archive'}
                  </>
                )}
              </button>
              {upload.isPending && (
                <p className="text-sm text-ink-2" role="status">
                  Validating, saving and re-indexing. This can take a moment while embeddings are generated.
                </p>
              )}
            </div>
          </div>
        </form>

        {upload.isSuccess && upload.data.status === 'ingested' && <ResultPanel result={upload.data} />}
        {upload.isError && <ErrorPanel error={toUploadError(upload.error)} />}

        <section className={`${card} overflow-hidden`} aria-labelledby="recent-title">
          <div className="flex flex-wrap items-end justify-between gap-2 px-6 pb-3 pt-5">
            <div>
              <h2 id="recent-title" className="text-lg font-extrabold text-ink">
                Added this session
              </h2>
              <p className="text-sm text-ink-2">Files the archive has confirmed and indexed.</p>
            </div>
            <p className="text-xs font-semibold text-ink-3" aria-live="polite">
              {s
                ? `Archive: ${s.documents} documents · ${s.evidence_units.toLocaleString()} evidence units · ${s.embeddings.toLocaleString()} embeddings`
                : stats.isError
                  ? 'Archive statistics are unavailable.'
                  : ''}
            </p>
          </div>
          {history.data.length === 0 ? (
            <p className="border-t border-line px-6 py-8 text-center text-sm text-ink-3">
              Nothing added yet. Uploaded files appear here once the archive confirms them.
            </p>
          ) : (
            <div className="overflow-x-auto border-t border-line">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="bg-surface-2 text-xs font-bold uppercase tracking-wide text-ink-3">
                  <tr>
                    <th className="px-6 py-2.5">Name</th>
                    <th className="px-3 py-2.5">Type</th>
                    <th className="px-3 py-2.5">Items</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-6 py-2.5">Added</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {history.data.map((row) => (
                    <tr key={`${row.document_id}-${row.addedAt}`}>
                      <td className="px-6 py-3 font-bold text-ink">{row.name}</td>
                      <td className="px-3 py-3">
                        <span className="rounded-md bg-neutral-soft px-2 py-0.5 text-xs font-bold text-ink-2">{row.type}</span>
                      </td>
                      <td className="px-3 py-3 tabular-nums text-ink-2">{row.units}</td>
                      <td className="px-3 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-bold ${
                            row.keywordOnly ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'
                          }`}
                        >
                          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                          {row.keywordOnly ? 'Indexed · keyword only' : 'Indexed'}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-ink-2">{formatWhen(row.addedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
