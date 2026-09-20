import type { ReceiptTimelineEvent } from '../../types/api'
import { formatDate } from '../../lib'
import { StanceChip } from '../ui'
import { IconCheck } from '../icons'

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
    <ol className="grid gap-x-4 gap-y-6 sm:grid-cols-2 lg:flex lg:items-start lg:gap-0">
      {events.map((event, index) => (
        <li key={`${event.event_date}-${index}`} className="anim-fade-up relative min-w-0 lg:flex-1 lg:pr-3" style={{ animationDelay: `${index * 70}ms` }}>
          <div className="flex items-center" aria-hidden="true">
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand text-white">
              <IconCheck size={11} strokeWidth={3.5} />
            </span>
            <span className={`hidden h-px flex-1 lg:block ${index < events.length - 1 ? 'bg-brand/40' : 'bg-transparent'}`} />
          </div>
          <div className="mt-1.5 space-y-0.5 pr-1">
            <time className="block text-[9px] text-ink-3">{formatDate(event.event_date)}</time>
            <p className="text-[10.5px] font-bold leading-[14px] text-ink">{event.event_text}</p>
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              <StanceChip stance={event.state} />
              {event.citations.map((c, i) => (
                <button
                  key={c.evidence_id}
                  type="button"
                  onClick={() => onOpen(c.evidence_id)}
                  className="cursor-pointer rounded-full border border-line px-2 py-0.5 text-[9px] font-semibold text-brand-ink transition-colors duration-200 hover:border-brand hover:bg-brand-soft"
                >
                  Source {i + 1}
                </button>
              ))}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}
