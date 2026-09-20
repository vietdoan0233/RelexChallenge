import type { ReceiptTimelineEvent, Stance } from '../../types/api'
import { formatDate } from '../../lib'
import { IconCheck } from '../icons'

const pretty = (v: Stance) => v.replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())

/** "UAT plan agreed. Detailed test plan defined." reads as a short label plus a
 *  description. The full sentence is always kept: nothing is dropped, only re-laid out. */
function splitEvent(text: string): [string, string] {
  const match = text.match(/^(.+?[.!?])\s+(.+)$/s)
  return match ? [match[1].replace(/[.]$/, ''), match[2]] : [text, '']
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
    <ol className="grid gap-x-4 gap-y-5 sm:grid-cols-2 lg:flex lg:items-start lg:gap-0">
      {events.map((event, index) => {
        const [label, detail] = splitEvent(event.event_text)
        const first = event.citations[0]
        return (
          <li key={`${event.event_date}-${index}`} className="anim-fade-up relative min-w-0 lg:flex-1 lg:pr-3" style={{ animationDelay: `${index * 70}ms` }}>
            <div className="flex items-center" aria-hidden="true">
              <span className="grid size-[18px] shrink-0 place-items-center rounded-full bg-brand text-white">
                <IconCheck size={11} strokeWidth={3.5} />
              </span>
              <span className={`hidden h-px flex-1 lg:block ${index < events.length - 1 ? 'bg-brand/40' : 'bg-transparent'}`} />
            </div>
            <div className="mt-0.5 pr-1">
              <time className="block text-[9px] leading-[13px] text-ink-3">
                {formatDate(event.event_date)} · {pretty(event.state)}
              </time>
              <button
                type="button"
                disabled={!first}
                onClick={() => first && onOpen(first.evidence_id)}
                className="block cursor-pointer text-left hover:underline disabled:cursor-default"
                title={event.event_text}
              >
                <span className="block text-[10.5px] font-bold leading-[14px] text-ink">{label}</span>
                {detail && <span className="line-clamp-2 block text-[9px] leading-[12px] text-ink-2">{detail}</span>}
              </button>
              {event.citations.length > 1 && (
                <span className="mt-0.5 flex flex-wrap gap-1">
                  {event.citations.slice(1).map((c, i) => (
                    <button
                      key={c.evidence_id}
                      type="button"
                      onClick={() => onOpen(c.evidence_id)}
                      className="cursor-pointer rounded-full border border-line px-1.5 text-[8.5px] font-semibold text-brand-ink transition-colors duration-200 hover:border-brand hover:bg-brand-soft"
                    >
                      Source {i + 2}
                    </button>
                  ))}
                </span>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
