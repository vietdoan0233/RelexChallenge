import { useState } from 'react'
import type { Citation } from '../../types/api'
import { formatDate } from '../../lib'
import { IconChevronDown, IconFile, IconMail, IconMic } from '../icons'
import { PersonLink } from '../PersonLink'

export function DocIcon({ type, size = 16 }: { type: string; size?: number }) {
  if (type === 'TRANSCRIPT') return <IconMic size={size} />
  if (type === 'EMAIL') return <IconMail size={size} />
  return <IconFile size={size} />
}

const TONE = {
  support: { bar: 'border-l-ok', label: 'Supports', text: 'text-ok' },
  conflict: { bar: 'border-l-bad', label: 'Conflicts', text: 'text-bad' },
  neutral: { bar: 'border-l-brand', label: 'Source', text: 'text-brand-ink' },
} as const

export function SourceChip({
  citation: c,
  tone,
  onOpen,
}: {
  citation: Citation
  tone: keyof typeof TONE
  onOpen: (id: string) => void
}) {
  const t = TONE[tone]
  return (
    <button
      type="button"
      onClick={() => onOpen(c.evidence_id)}
      className={`group w-full cursor-pointer rounded-xl border border-line border-l-4 ${t.bar} bg-surface p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-brand hover:shadow-card`}
    >
      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs font-bold text-ink-3">
        <span className={`inline-flex items-center gap-1 ${t.text}`}>
          <DocIcon type={c.document_type} size={14} />
          {t.label}
        </span>
        <span className="text-ink-2">{c.document_title ?? c.document_id}</span>
        <span>· {formatDate(c.event_date)}</span>
        {c.speaker_sender && (
          <span>
            · <PersonLink subjectId={c.subject_id} name={c.speaker_sender} />
          </span>
        )}
      </span>
      <span className="mt-1.5 line-clamp-3 block text-sm leading-relaxed text-ink">{c.raw_text}</span>
      <span className="mt-1 flex items-center justify-between text-xs font-bold text-brand-ink">
        <span>{c.is_truncated ? 'Cut off in the source; not completed' : 'Open in context'}</span>
        <span className="opacity-0 transition-opacity duration-200 group-hover:opacity-100">→</span>
      </span>
    </button>
  )
}

/** A compact two-line row (title + filename, date at right): denser than SourceChip,
 *  used where a claim card has narrow columns and a quote preview would not fit. */
export function SourceRow({ citation: c, onOpen }: { citation: Citation; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(c.evidence_id)}
      className="group flex w-full cursor-pointer items-start gap-2.5 rounded-lg py-1.5 text-left transition-colors duration-200 hover:bg-surface-2"
    >
      <span className="mt-0.5 shrink-0 text-ink-3">
        <DocIcon type={c.document_type} size={15} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-ink">{c.document_title ?? c.filename}</span>
        <span className="block truncate text-xs text-ink-3">
          {c.speaker_sender ? <PersonLink subjectId={c.subject_id} name={c.speaker_sender} /> : c.filename}
        </span>
      </span>
      <span className="shrink-0 whitespace-nowrap text-xs font-semibold text-ink-3">{formatDate(c.event_date)}</span>
    </button>
  )
}

/** A list of sources; long lists collapse behind "show all" so a claim stays scannable. */
export function CitationList({
  citations,
  tone,
  onOpen,
  collapseAfter = 3,
}: {
  citations: Citation[]
  tone: keyof typeof TONE
  onOpen: (evidenceId: string) => void
  collapseAfter?: number
}) {
  const [all, setAll] = useState(false)
  if (citations.length === 0) return null
  const shown = all ? citations : citations.slice(0, collapseAfter)
  const hidden = citations.length - shown.length
  return (
    <div className="space-y-2">
      <ul className="grid gap-2 md:grid-cols-2">
        {shown.map((c) => (
          <li key={c.evidence_id}>
            <SourceChip citation={c} tone={tone} onOpen={onOpen} />
          </li>
        ))}
      </ul>
      {(hidden > 0 || all) && citations.length > collapseAfter && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="inline-flex min-h-11 cursor-pointer items-center gap-1 rounded-full px-3 text-sm font-bold text-brand-ink transition-colors duration-200 hover:bg-brand-soft"
          aria-expanded={all}
        >
          {all ? 'Show fewer' : `Show ${hidden} more source${hidden === 1 ? '' : 's'}`}
          <IconChevronDown size={16} className={all ? 'rotate-180' : ''} />
        </button>
      )}
    </div>
  )
}
