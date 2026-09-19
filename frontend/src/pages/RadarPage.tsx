import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { FindingCard } from '../components/radar/FindingCard'

export function RadarPage() {
  const query = useQuery({ queryKey: ['radar'], queryFn: api.radar })
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2 pt-6">
        <h1 className="text-3xl font-semibold">Reconsideration Radar</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Ideas the organization rejected or deferred, where the reason for saying no may have
          changed. These were found before you asked. Each card only says whether a blocker may
          have changed — it never says what to do; that stays with you.
        </p>
      </div>
      {query.isPending && <p role="status">Loading candidates…</p>}
      {query.isError && (
        <p role="alert" className="rounded-lg bg-rose-50 p-3 text-rose-900 dark:bg-rose-950 dark:text-rose-100">
          {query.error.message}
        </p>
      )}
      {query.data?.length === 0 && (
        <p className="rounded-lg border border-dashed border-zinc-400 p-4">
          No candidates have been surfaced yet. Findings are precomputed with{' '}
          <code>python scripts/radar.py</code>.
        </p>
      )}
      <div className="space-y-6">
        {query.data?.map((card) => <FindingCard key={card.finding_id} card={card} />)}
      </div>
    </div>
  )
}
