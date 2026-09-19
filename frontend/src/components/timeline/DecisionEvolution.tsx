import type { ReceiptTimelineEvent, Stance } from '../../types/api'
import { formatDate } from '../../lib'
import { ConfidenceMeter, StanceChip } from '../ui'

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
 *  it; nothing is inferred to smooth the story. */
export function DecisionEvolution({
  events,
  onOpen,
}: {
  events: ReceiptTimelineEvent[]
  onOpen: (evidenceId: string) => void
}) {
  if (events.length === 0) return null
  return (
    <ol className="relative space-y-4 pl-8 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-0.5 before:bg-line">
      {events.map((event, index) => (
        <li key={`${event.event_date}-${index}`} className="anim-fade-up relative" style={{ animationDelay: `${index * 70}ms` }}>
          <span
            aria-hidden="true"
            className={`absolute -left-8 top-4 grid size-6 place-items-center rounded-full ring-4 ring-bg ${DOT[event.state]}`}
          >
            <span className="size-2 rounded-full bg-white" />
          </span>
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-card">
            <div className="flex flex-wrap items-center gap-2">
              <time className="rounded-full bg-deep px-3 py-1 text-xs font-extrabold text-white">
                {formatDate(event.event_date)}
              </time>
              <StanceChip stance={event.state} />
              <ConfidenceMeter confidence={event.confidence} />
            </div>
            <p className="mt-2 text-base font-semibold leading-snug text-ink">{event.event_text}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {event.citations.map((c, i) => (
                <button
                  key={c.evidence_id}
                  type="button"
                  onClick={() => onOpen(c.evidence_id)}
                  className="min-h-11 cursor-pointer rounded-full border border-line px-4 text-sm font-semibold text-brand-ink transition-colors duration-200 hover:border-brand hover:bg-brand-soft"
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
