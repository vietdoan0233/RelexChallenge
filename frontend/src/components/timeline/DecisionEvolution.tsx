import type { ReceiptTimelineEvent, Stance } from '../../types/api'
import { formatDate } from '../../lib'
import { ConfidenceMeter, StanceChip } from '../ui'
import { IconCheck } from '../icons'

const DOT: Record<Stance, string> = {
  PROPOSAL: 'bg-purple',
  ASSUMPTION: 'bg-ink-3',
  OBJECTION: 'bg-bad',
  AGREEMENT: 'bg-ok',
  COMMITMENT: 'bg-ok',
  STATUS_UPDATE: 'bg-brand',
  IMPLEMENTATION_EVIDENCE: 'bg-brand',
  SUPERSEDED: 'bg-orange',
  UNCERTAIN: 'bg-warn',
}

/** How evidence-supported state changed over time. Every node has evidence and opens
 *  it; nothing is inferred to smooth the story. A short list reads as a left-to-right
 *  timeline; a long one wraps and keeps each node fully readable. */
export function DecisionEvolution({
  events,
  onOpen,
}: {
  events: ReceiptTimelineEvent[]
  onOpen: (evidenceId: string) => void
}) {
  if (events.length === 0) return null
  return (
    <ol className="grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:flex lg:items-start lg:gap-0">
      {events.map((event, index) => (
        <li key={`${event.event_date}-${index}`} className="anim-fade-up relative min-w-0 lg:flex-1 lg:px-2" style={{ animationDelay: `${index * 70}ms` }}>
          <div className="flex items-center" aria-hidden="true">
            <span className={`grid size-8 shrink-0 place-items-center rounded-full text-white ring-4 ring-bg ${DOT[event.state]}`}>
              <IconCheck size={15} strokeWidth={3} />
            </span>
            <span className={`hidden h-0.5 flex-1 lg:block ${index < events.length - 1 ? 'bg-line' : 'bg-transparent'}`} />
          </div>
          <div className="mt-3 space-y-1.5 pr-2">
            <time className="block text-xs font-extrabold uppercase tracking-wide text-ink-3">{formatDate(event.event_date)}</time>
            <p className="text-sm font-extrabold leading-snug text-ink">{event.event_text}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <StanceChip stance={event.state} />
              <ConfidenceMeter confidence={event.confidence} />
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {event.citations.map((c, i) => (
                <button
                  key={c.evidence_id}
                  type="button"
                  onClick={() => onOpen(c.evidence_id)}
                  className="min-h-8 cursor-pointer rounded-full border border-line px-3 text-xs font-semibold text-brand-ink transition-colors duration-200 hover:border-brand hover:bg-brand-soft"
                >
                  Source {i + 1} · {c.speaker_sender ?? 'unknown'}
                </button>
              ))}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}
