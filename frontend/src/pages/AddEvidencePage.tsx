import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { DragEvent, ReactNode } from 'react'
import { ApiError, api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCloud,
  IconFile,
  IconFolder,
  IconMail,
  IconMessage,
  IconMic,
  IconMoreHorizontal,
  IconUpload,
  IconX,
} from '../components/icons'
import { EuFlag } from '../components/Logo'
import { Spinner, Tick } from '../components/ui'
import { btnPrimary, btnSecondary, card } from '../lib'
import type { RecentDocument, UploadDocumentType, UploadFailure, UploadResult } from '../types/api'

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

const TYPE_LABEL: Record<string, string> = { EMAIL: 'Email', TRANSCRIPT: 'Meeting notes', REPORT: 'Report' }

// Sources shown for orientation only: none of them is connected in this build.
const SOURCES: { name: string; blurb: string; icon: ReactNode; tone: string; action: string }[] = [
  { name: 'Gmail', blurb: 'Emails and attachments', icon: <IconMail size={20} />, tone: 'bg-[#fdeeed] text-[#d64545]', action: 'Connect' },
  { name: 'Outlook', blurb: 'Emails and calendar', icon: <IconMail size={20} />, tone: 'bg-[#e6f1fb] text-[#1772b8]', action: 'Connect' },
  { name: 'Google Drive', blurb: 'Documents and files', icon: <IconFolder size={20} />, tone: 'bg-[#eaf8f1] text-[#22a06b]', action: 'Connect' },
  { name: 'Microsoft Teams', blurb: 'Chats and meeting notes', icon: <IconMessage size={20} />, tone: 'bg-[#efeafb] text-[#6b55c7]', action: 'Connect' },
  { name: 'Notion', blurb: 'Pages and documentation', icon: <IconFile size={20} />, tone: 'bg-[#eef1f4] text-[#0d2c4d]', action: 'Connect' },
  { name: 'Other sources', blurb: 'iCloud, Slack, SharePoint, etc.', icon: <IconCloud size={20} />, tone: 'bg-[#eef1f4] text-[#46607b]', action: 'Set up' },
]

const formatSize = (bytes: number) => (bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`)

const formatWhen = (iso: string) => {
  const d = new Date(iso)
  const date = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
  return `${date}, ${time}`
}

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
      <span className="grid size-6 place-items-center rounded-full bg-brand-soft text-xs font-bold text-brand-ink">{n}</span>
      <h2 className="text-[13px] font-bold text-ink">{children}</h2>
    </div>
  )
}

type Tab = 'connect' | 'upload'

export function AddEvidencePage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('connect')
  const [showAll, setShowAll] = useState(false)
  const [documentType, setDocumentType] = useState<UploadDocumentType>('email')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const recent = useQuery({
    queryKey: ['ingest-recent', showAll],
    queryFn: () => api.recentDocuments(showAll ? 50 : 5),
  })

  const upload = useMutation({
    mutationFn: ({ type, list }: { type: UploadDocumentType; list: File[] }) => api.uploadEvidence(type, list),
    onSuccess: () => {
      setFiles([])
      // The archive counts (header status, Ask page) and the recent list changed.
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
      void queryClient.invalidateQueries({ queryKey: ['ingest-recent'] })
    },
  })

  const addFiles = (incoming: FileList | File[]) => {
    upload.reset()
    // A FileList is live: the picker is cleared right after this call and a drop's
    // list is only valid during the event, so copy it before the deferred update.
    const picked = Array.from(incoming)
    setFiles((current) => {
      const seen = new Set(current.map((f) => `${f.name}:${f.size}`))
      return [...current, ...picked.filter((f) => !seen.has(`${f.name}:${f.size}`))]
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
  const typeLabel = TYPES.find((t) => t.value === documentType)!.label

  return (
    <div className="mx-auto max-w-[1104px] px-4 pb-12">
      {/* ------------------------------------------------------------ hero */}
      <section className="grid items-start gap-6 pt-[26px] lg:grid-cols-[minmax(0,1fr)_323px]">
        <div className="anim-fade-up">
          <h1 className="text-balance text-[34px] font-bold leading-[42px] tracking-tight text-title">Add your organizational knowledge</h1>
          <p className="mt-[14px] max-w-[640px] text-pretty text-[15px] leading-[22px] text-ink-2">
            Give ENGRAM access to your organization's emails, meetings, documents and
            conversations. Everything you add is saved to the archive, indexed and structured, so it can be searched,
            cited and reasoned over like the original evidence.
          </p>
        </div>
        <aside className="anim-fade-up flex gap-3 rounded-[10px] border border-line bg-[#eef5fc] p-4" style={{ animationDelay: '0.08s' }}>
          <EuFlag width={40} />
          <div className="space-y-1">
            <p className="text-[12px] font-bold text-ink">Your data stays in your control</p>
            <p className="text-[10.5px] leading-[15px] text-ink-2">
              Uploads join the same archive as the original evidence, so anyone named in them can later be redacted or
              deleted from the Privacy console.
            </p>
            <a href="#/privacy" className="inline-flex items-center gap-1 text-[11px] font-bold text-brand-ink hover:underline">
              Open Privacy console <IconArrowRight size={12} />
            </a>
          </div>
        </aside>
      </section>

      {/* ------------------------------------------------------ main card */}
      <section className={`${card} mt-[22px] overflow-hidden`}>
        <div role="tablist" aria-label="How to add evidence" className="flex gap-8 border-b border-line px-6">
          {(
            [
              ['connect', 'Connect sources'],
              ['upload', 'Upload files'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              type="button"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              onClick={() => setTab(id)}
              className={`-mb-px cursor-pointer border-b-2 py-[14px] text-[13px] font-semibold transition-colors duration-200 ${
                tab === id ? 'border-brand text-brand-ink' : 'border-transparent text-ink-2 hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'connect' && (
          <div role="tabpanel" id="panel-connect" aria-labelledby="tab-connect" className="p-[13px]">
            <ul className="grid grid-cols-2 gap-[11px] md:grid-cols-3 xl:grid-cols-6">
              {SOURCES.map((src) => (
                <li key={src.name} className="flex h-[162px] flex-col items-center rounded-[10px] border border-line bg-surface px-3 pt-5 text-center">
                  <span className={`grid size-10 place-items-center rounded-xl ${src.tone}`}>{src.icon}</span>
                  <p className="mt-3 text-[12px] font-bold text-ink">{src.name}</p>
                  <p className="mt-0.5 text-[10px] leading-[13px] text-ink-3">{src.blurb}</p>
                  <button
                    type="button"
                    onClick={() => setTab('upload')}
                    title="Live connectors are not enabled in this build; this opens Upload files."
                    className="mt-auto mb-4 h-8 w-[90px] cursor-pointer rounded-full border border-brand/50 bg-surface text-[11px] font-semibold text-brand-ink transition-colors duration-200 hover:bg-brand-soft"
                  >
                    {src.action}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-3 flex items-center gap-2 rounded-lg bg-warn-soft px-3 py-2 text-[11px] text-ink" role="note">
              <IconAlert size={14} className="shrink-0 text-warn" />
              Live connectors are not enabled in this build, so nothing is fetched automatically. Use{' '}
              <button type="button" onClick={() => setTab('upload')} className="cursor-pointer font-bold text-brand-ink underline">
                Upload files
              </button>{' '}
              to add emails, meeting notes and reports as .txt files.
            </p>
          </div>
        )}

        {tab === 'upload' && (
          <form
            role="tabpanel"
            id="panel-upload"
            aria-labelledby="tab-upload"
            className="space-y-7 p-6"
            onSubmit={(e) => {
              e.preventDefault()
              if (canSubmit) upload.mutate({ type: documentType, list: files })
            }}
          >
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
                      className={`flex cursor-pointer flex-col items-center gap-2 rounded-[10px] border p-4 text-center transition-all duration-200 has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand/25 ${
                        on ? 'border-brand bg-brand-soft' : 'border-line bg-surface hover:border-brand'
                      }`}
                    >
                      <input type="radio" name="document_type" value={t.value} checked={on} onChange={() => setDocumentType(t.value)} className="sr-only" />
                      <span className={`grid size-10 place-items-center rounded-full ${on ? 'bg-surface text-brand-ink' : 'bg-surface-2 text-ink-3'}`}>{t.icon}</span>
                      <span className="text-[13px] font-bold text-ink">{t.label}</span>
                      <span className="text-[11px] leading-[15px] text-ink-2">{t.blurb}</span>
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
                className={`grid place-items-center gap-2 rounded-[10px] border-2 border-dashed px-4 py-8 text-center transition-colors duration-200 ${
                  dragging ? 'border-brand bg-brand-soft' : 'border-line bg-surface-2'
                }`}
              >
                <span className="grid size-11 place-items-center rounded-full bg-surface text-brand-ink shadow-card">
                  <IconUpload size={22} />
                </span>
                <p className="text-[12px] font-semibold text-ink-2">Drag and drop .txt files here, or</p>
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
                <p className="text-[11px] text-ink-3">
                  Up to {MAX_FILES} files · {MAX_FILE_BYTES / (1024 * 1024)} MB each · plain text only
                </p>
              </div>

              {files.length > 0 && (
                <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line" aria-label="Selected files">
                  {files.map((file, i) => (
                    <li key={`${file.name}:${file.size}`} className="flex items-center justify-between gap-3 bg-surface px-4 py-2 text-[12px]">
                      <span className="flex min-w-0 items-center gap-3">
                        <IconFile size={16} className="shrink-0 text-ink-3" />
                        <span className="min-w-0">
                          <span className="block truncate font-bold text-ink">{file.name}</span>
                          {problems[i] && <span className="block text-[11px] font-semibold text-bad">{problems[i]}</span>}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-3">
                        <span className="text-[11px] text-ink-3">{formatSize(file.size)}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${file.name}`}
                          className="grid size-7 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-neutral-soft hover:text-ink"
                          onClick={() => setFiles((current) => current.filter((_, j) => j !== i))}
                        >
                          <IconX size={14} />
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
          </form>
        )}
      </section>

      {tab === 'upload' && upload.isSuccess && upload.data.status === 'ingested' && (
        <div className="mt-4">
          <ResultPanel result={upload.data} />
        </div>
      )}
      {tab === 'upload' && upload.isError && (
        <div className="mt-4">
          <ErrorPanel error={toUploadError(upload.error)} />
        </div>
      )}

      {/* ------------------------------------------------ recent ingestions */}
      <section className={`${card} mt-[22px] overflow-hidden`} aria-labelledby="recent-title">
        <div className="flex flex-wrap items-start justify-between gap-3 px-5 pb-[14px] pt-[18px]">
          <div>
            <h2 id="recent-title" className="text-[17px] font-bold leading-6 text-ink">
              Recent ingestions
            </h2>
            <p className="text-[11px] text-ink-2">Files and data sources that have been added to your knowledge base.</p>
          </div>
          {(recent.data?.length ?? 0) >= 5 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="inline-flex h-[30px] cursor-pointer items-center gap-1.5 rounded-full border border-brand/50 bg-surface px-4 text-[11px] font-semibold text-brand-ink transition-colors duration-200 hover:bg-brand-soft"
            >
              {showAll ? 'Show fewer' : 'View all'} <IconArrowRight size={13} />
            </button>
          )}
        </div>
        {recent.isPending && <p className="border-t border-line px-5 py-6 text-center text-[12px] text-ink-3">Loading…</p>}
        {recent.isError && (
          <p role="alert" className="border-t border-line px-5 py-6 text-center text-[12px] text-bad">
            The recent list could not be loaded.
          </p>
        )}
        {recent.data && recent.data.length === 0 && (
          <p className="border-t border-line px-5 py-6 text-center text-[12px] text-ink-3">Nothing has been added yet.</p>
        )}
        {recent.data && recent.data.length > 0 && (
          <div className="overflow-x-auto px-3 pb-3">
            <table className="w-full min-w-[640px] text-left text-[12px]">
              <thead>
                <tr className="bg-surface-2 text-[11px] font-semibold text-ink-2">
                  <th className="rounded-l-lg px-3 py-2.5">Name</th>
                  <th className="px-3 py-2.5">Source</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-3 py-2.5">Items</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Added</th>
                  <th className="w-8 rounded-r-lg px-3 py-2.5">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {recent.data.map((row: RecentDocument) => (
                  <tr key={row.document_id} className="h-10">
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-2.5 font-semibold text-ink">
                        <IconFile size={15} className="shrink-0 text-ink-3" />
                        <span className="max-w-[230px] truncate" title={row.filename}>
                          {row.title ?? row.filename}
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-ink-2">
                      <span className="inline-flex items-center gap-2">
                        <IconFolder size={14} className="text-ink-3" /> Archive source
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded-md bg-neutral-soft px-2 py-0.5 text-[10.5px] font-medium text-ink-2">
                        {TYPE_LABEL[row.document_type] ?? row.document_type}
                      </span>
                    </td>
                    <td className="px-3 py-2 tabular-nums text-ink-2">{row.evidence_units.toLocaleString()}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10.5px] font-semibold ${
                          row.indexed === 'full' ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'
                        }`}
                      >
                        <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                        {row.indexed === 'full' ? 'Indexed' : 'Keyword only'}
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-ink-2">{formatWhen(row.added_at)}</td>
                    <td className="px-3 py-2 text-ink-3">
                      <IconMoreHorizontal size={16} aria-hidden="true" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
