import type { Citation } from '../../types/api'
import { formatDate } from '../../lib'

export function CitationList({
  citations,
  tone,
  onOpen,
}: {
  citations: Citation[]
  tone: 'support' | 'conflict'
  onOpen: (evidenceId: string) => void
}) {
  if (citations.length === 0) return null
  const border =
    tone === 'support'
      ? 'border-l-emerald-600 dark:border-l-emerald-400'
      : 'border-l-rose-600 dark:border-l-rose-400'
  return (
    <ul className="space-y-2">
      {citations.map((c) => (
        <li key={c.evidence_id}>
          <button
            type="button"
            onClick={() => onOpen(c.evidence_id)}
            className={`w-full rounded-md border border-zinc-200 border-l-4 bg-white p-3 text-left text-sm hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 ${border}`}
          >
            <span className="block text-xs font-semibold text-zinc-600 dark:text-zinc-400">
              {tone === 'support' ? 'Supports' : 'Conflicts'} · {c.document_title ?? c.document_id} ·{' '}
              {formatDate(c.event_date)} · {c.speaker_sender ?? 'unknown sender'}
            </span>
            <span className="mt-1 block line-clamp-3">{c.raw_text}</span>
            {c.is_truncated && (
              <span className="mt-1 block text-xs font-semibold text-amber-800 dark:text-amber-300">
                Cut off in the source
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}
