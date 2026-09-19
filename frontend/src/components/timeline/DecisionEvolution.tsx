import type { ReceiptTimelineEvent } from '../../types/api'
import { ConfidenceChip, StanceChip } from '../ui'
import { formatDate } from '../../lib'

/** How evidence-supported state changed over time. Every node has evidence and
 *  opens it; nothing is inferred to smooth the story, and ambiguity stays
 *  visible as low confidence or an uncertain stance. */
export function DecisionEvolution({
  events,
  onOpen,
}: {
  events: ReceiptTimelineEvent[]
  onOpen: (evidenceId: string) => void
}) {
  if (events.length === 0) return null
  return (
    <ol className="relative ml-3 border-l-2 border-zinc-300 dark:border-zinc-700">
      {events.map((event, index) => (
        <li key={`${event.event_date}-${index}`} className="mb-6 ml-6 last:mb-0">
          <span
            aria-hidden="true"
            className="absolute -left-[9px] mt-1.5 size-4 rounded-full border-2 border-indigo-700 bg-white dark:border-indigo-400 dark:bg-zinc-950"
          />
          <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
            {formatDate(event.event_date)}
          </p>
          <div className="my-1 flex flex-wrap items-center gap-2">
            <StanceChip stance={event.state} />
            <ConfidenceChip confidence={event.confidence} />
          </div>
          <p className="text-zinc-900 dark:text-zinc-100">{event.event_text}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {event.citations.map((c, i) => (
              <button
                key={c.evidence_id}
                type="button"
                onClick={() => onOpen(c.evidence_id)}
                className="min-h-11 rounded-md border border-zinc-300 px-3 text-sm text-indigo-800 underline-offset-2 hover:bg-zinc-50 hover:underline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-zinc-700 dark:text-indigo-300 dark:hover:bg-zinc-800"
              >
                Source {i + 1}: {c.speaker_sender ?? 'unknown'}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ol>
  )
}
