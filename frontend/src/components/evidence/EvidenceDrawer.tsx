import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../../api/client'
import type { Citation } from '../../types/api'
import { btnSecondary, formatDate } from '../../lib'
import { IconAlert, IconX } from '../icons'
import { PersonLink } from '../PersonLink'
import { Skeleton } from '../ui'
import { DocIcon } from './CitationList'

function Unit({ unit, highlight }: { unit: Citation; highlight?: boolean }) {
  return (
    <li
      aria-current={highlight ? 'true' : undefined}
      className={
        highlight
          ? 'rounded-2xl border-2 border-brand bg-brand-soft p-4 shadow-card'
          : 'rounded-xl border border-dashed border-line p-3 text-ink-2'
      }
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 text-xs font-bold">
        <span className={highlight ? 'text-ink' : ''}>
          {unit.speaker_sender ? (
            <PersonLink subjectId={unit.subject_id} name={unit.speaker_sender} />
          ) : (
            'Unknown sender'
          )}
        </span>
        {unit.timestamp_text && <span className="font-medium opacity-80">{unit.timestamp_text}</span>}
        <span
          className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide ${
            highlight ? 'bg-brand text-white' : 'bg-neutral-soft text-ink-3'
          }`}
        >
          {highlight ? 'Cited' : 'Context'}
        </span>
      </div>
      <p className={`whitespace-pre-wrap leading-relaxed ${highlight ? 'text-base text-ink' : 'text-sm'}`}>
        {unit.raw_text}
      </p>
      {unit.is_truncated && (
        <p className="mt-2 flex items-center gap-1.5 text-xs font-bold text-warn">
          <IconAlert size={14} /> This statement is cut off in the source. It has not been completed.
        </p>
      )}
    </li>
  )
}

/** One cited unit with its neighbours, so a bare "yes" is never shown without the
 *  exchange it answers. Everything comes from the database. */
export function EvidenceDrawer({ evidenceId, onClose }: { evidenceId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['evidence', evidenceId], queryFn: () => api.getEvidence(evidenceId) })
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const citedRef = useRef<HTMLLIElement | null>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const previous = document.activeElement as HTMLElement | null
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') return onClose()
      if (event.key !== 'Tab' || !panelRef.current) return
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
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      previous?.focus()
    }
  }, [onClose])

  const cite = query.data?.citation
  useEffect(() => {
    if (cite) citedRef.current?.scrollIntoView({ block: 'center' })
  }, [cite])

  return (
    <div className="anim-fade-in fixed inset-0 z-40 flex justify-end bg-deep/50 backdrop-blur-sm" onClick={onClose}>
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Source evidence"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-xl flex-col bg-surface shadow-lift"
        style={{ animation: 'fade-up 0.3s cubic-bezier(0.2,0.7,0.2,1) both' }}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line p-5">
          <div className="min-w-0">
            <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-brand-ink">Source evidence</p>
            {cite ? (
              <h2 className="mt-1 flex items-center gap-2 text-lg font-extrabold leading-tight">
                <DocIcon type={cite.document_type} size={20} />
                <span className="truncate">{cite.document_title ?? cite.document_id}</span>
              </h2>
            ) : (
              <Skeleton className="mt-2 h-6 w-56" />
            )}
            {cite && (
              <p className="mt-0.5 text-sm text-ink-2">
                {cite.document_type.toLowerCase()} · {formatDate(cite.event_date)}
                {cite.thread_context && cite.thread_context !== cite.document_title ? ` · ${cite.thread_context}` : ''}
              </p>
            )}
          </div>
          <button ref={closeRef} type="button" className={`${btnSecondary} !px-3`} onClick={onClose} aria-label="Close source">
            <IconX size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {query.isPending && (
            <div role="status" className="space-y-3">
              <Skeleton className="h-16" />
              <Skeleton className="h-28" />
              <Skeleton className="h-16" />
            </div>
          )}
          {query.isError && (
            <p role="alert" className="rounded-xl bg-bad-soft p-4 font-semibold text-bad">
              This evidence is no longer available. It may have been removed.
            </p>
          )}
          {query.data && cite && (
            <ol className="space-y-2">
              {query.data.context_before.map((u) => (
                <Unit key={u.evidence_id} unit={u} />
              ))}
              <div ref={(el) => { citedRef.current = el as unknown as HTMLLIElement }} className="contents">
                <Unit unit={cite} highlight />
              </div>
              {query.data.context_after.map((u) => (
                <Unit key={u.evidence_id} unit={u} />
              ))}
            </ol>
          )}
        </div>
        {cite && (
          <p className="break-all border-t border-line px-5 py-3 text-xs text-ink-3">
            {cite.filename} · {cite.evidence_id}
          </p>
        )}
      </aside>
    </div>
  )
}
