import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../../api/client'
import type { Citation } from '../../types/api'
import { btnSecondary, formatDate } from '../../lib'

function Unit({ unit, highlight }: { unit: Citation; highlight?: boolean }) {
  return (
    <li
      aria-current={highlight ? 'true' : undefined}
      className={
        highlight
          ? 'rounded-lg border-2 border-indigo-600 bg-indigo-50 p-3 dark:border-indigo-400 dark:bg-indigo-950'
          : 'rounded-lg border border-dashed border-zinc-300 p-3 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400'
      }
    >
      <div className="mb-1 flex flex-wrap items-center gap-x-2 text-xs font-semibold">
        <span>{unit.speaker_sender ?? 'Unknown sender'}</span>
        {unit.timestamp_text && <span className="font-normal opacity-80">{unit.timestamp_text}</span>}
        <span className="ml-auto uppercase tracking-wide opacity-80">
          {highlight ? 'Cited' : 'Context'}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{unit.raw_text}</p>
      {unit.is_truncated && (
        <p className="mt-2 text-xs font-semibold text-amber-800 dark:text-amber-300">
          This statement is cut off in the source. It has not been completed.
        </p>
      )}
    </li>
  )
}

/** Shows one cited unit with its neighbours, so a bare "yes" is never shown
 *  without the exchange it answers. Everything comes from the database. */
export function EvidenceDrawer({ evidenceId, onClose }: { evidenceId: string; onClose: () => void }) {
  const query = useQuery({
    queryKey: ['evidence', evidenceId],
    queryFn: () => api.getEvidence(evidenceId),
  })
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const previous = document.activeElement as HTMLElement | null
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') return onClose()
      if (event.key !== 'Tab' || !panelRef.current) return
      // Keep focus inside the modal: cycle at the first/last focusable element.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>('button, [href], input, [tabindex]:not([tabindex="-1"])')
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previous?.focus() // return focus to the citation that opened the drawer
    }
  }, [onClose])

  const cite = query.data?.citation
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Source evidence"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white p-5 shadow-2xl dark:bg-zinc-900"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Source evidence</h2>
            {cite && (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                {cite.document_title ?? cite.document_id} · {cite.document_type.toLowerCase()} ·{' '}
                {formatDate(cite.event_date)}
              </p>
            )}
          </div>
          <button ref={closeRef} type="button" className={btnSecondary} onClick={onClose}>
            Close
          </button>
        </div>

        {query.isPending && <p role="status">Loading evidence…</p>}
        {query.isError && (
          <p role="alert" className="text-rose-800 dark:text-rose-300">
            This evidence is no longer available. It may have been removed.
          </p>
        )}
        {query.data && cite && (
          <>
            {cite.thread_context && (
              <p className="mb-3 text-sm">
                <span className="font-semibold">Thread:</span> {cite.thread_context}
              </p>
            )}
            <ol className="space-y-2">
              {query.data.context_before.map((u) => (
                <Unit key={u.evidence_id} unit={u} />
              ))}
              <Unit unit={cite} highlight />
              {query.data.context_after.map((u) => (
                <Unit key={u.evidence_id} unit={u} />
              ))}
            </ol>
            <p className="mt-4 break-all text-xs text-zinc-500 dark:text-zinc-500">
              {cite.filename} · {cite.evidence_id}
            </p>
          </>
        )}
      </aside>
    </div>
  )
}
