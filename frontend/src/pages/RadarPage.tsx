import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { IconRadar } from '../components/icons'
import { ASSESSMENT } from '../components/radar/assessments'
import { FindingCard } from '../components/radar/FindingCard'
import { Eyebrow, Skeleton } from '../components/ui'

export function RadarPage() {
  const query = useQuery({ queryKey: ['radar'], queryFn: api.radar })
  return (
    <div>
      <section className="hero-bg relative overflow-hidden">
        <div className="mx-auto max-w-4xl space-y-4 px-4 pb-12 pt-14 text-center">
          <span className="anim-float mx-auto grid size-16 place-items-center rounded-3xl bg-gradient-to-br from-brand to-purple text-white shadow-lift">
            <IconRadar size={32} />
          </span>
          <Eyebrow>Reconsideration Radar</Eyebrow>
          <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">
            Ideas that were told <span className="text-brand-ink">no</span>, worth a second look?
          </h1>
          <p className="mx-auto max-w-2xl text-lg text-ink-2">
            Found before you asked. Each card shows what was proposed, why it was stopped, and whether that reason may
            have changed. It never tells you what to do; that stays with you.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-4xl space-y-8 px-4 py-10">
        <section aria-label="What each assessment means">
          <ul className="grid gap-3 sm:grid-cols-2">
            {Object.entries(ASSESSMENT).map(([key, a]) => (
              <li key={key} className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 shadow-card">
                <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-extrabold ${a.tone}`}>
                  {a.icon}
                  {a.label}
                </span>
                <span className="text-sm text-ink-2">{a.meaning}</span>
              </li>
            ))}
          </ul>
        </section>

        {query.isPending && (
          <div role="status" className="space-y-4" aria-label="Loading candidates">
            <Skeleton className="h-72" />
          </div>
        )}
        {query.isError && (
          <p role="alert" className="rounded-2xl bg-bad-soft p-4 font-semibold text-bad">
            {query.error.message}
          </p>
        )}
        {query.data?.length === 0 && (
          <div className="space-y-3 rounded-3xl border border-dashed border-line bg-surface p-10 text-center">
            <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-soft text-brand-ink">
              <IconRadar size={28} />
            </span>
            <h2 className="text-xl font-extrabold">No candidates surfaced yet</h2>
            <p className="text-ink-2">
              Findings are precomputed so this page opens with answers waiting. Generate them with{' '}
              <code className="rounded bg-surface-2 px-2 py-0.5 font-mono text-sm">python scripts/radar.py</code>.
            </p>
          </div>
        )}
        <div className="space-y-8">{query.data?.map((card) => <FindingCard key={card.finding_id} card={card} />)}</div>
      </div>
    </div>
  )
}
