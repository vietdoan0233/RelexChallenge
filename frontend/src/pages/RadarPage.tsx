import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { IconArrowRight, IconBulb, IconRadar, IconSpark } from '../components/icons'
import { ASSESSMENT } from '../components/radar/assessments'
import { FindingCard } from '../components/radar/FindingCard'
import { go } from '../hooks/useRoute'
import { card } from '../lib'
import { Skeleton } from '../components/ui'
import type { RadarAssessment } from '../types/api'

function CountChip({ tone, icon, label, n }: { tone: string; icon: React.ReactNode; label: string; n: number }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-extrabold uppercase tracking-wide ${tone}`}>
      {icon}
      {label}
      <span className="rounded-full bg-white/60 px-1.5 py-0.5 text-xs dark:bg-black/20">{n}</span>
    </span>
  )
}

export function RadarPage() {
  const query = useQuery({ queryKey: ['radar'], queryFn: api.radar })

  const counts = useMemo(() => {
    const c: Record<RadarAssessment, number> = { STILL_BLOCKED: 0, PARTIALLY_CHANGED: 0, WORTH_REASSESSING: 0, INSUFFICIENT_EVIDENCE: 0 }
    for (const f of query.data ?? []) c[f.assessment]++
    return c
  }, [query.data])

  return (
    <div>
      <section className="hero-bg relative overflow-hidden">
        <div className="mx-auto max-w-4xl space-y-4 px-4 pb-10 pt-12 text-center">
          <span className="inline-flex items-center gap-2 rounded-full bg-surface/80 px-4 py-1.5 text-xs font-extrabold uppercase tracking-[0.14em] text-ink-3 shadow-card">
            Find opportunities in past decisions
          </span>
          <h1 className="text-balance text-4xl font-extrabold tracking-tight text-brand-ink sm:text-5xl">Reconsideration Radar</h1>
          <p className="mx-auto max-w-2xl text-lg text-ink-2">
            Surfaces ideas the organization rejected or deferred where the original blocker may have changed. Turn
            past decisions into new possibilities.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <CountChip tone={ASSESSMENT.STILL_BLOCKED.tone} icon={ASSESSMENT.STILL_BLOCKED.icon} label={ASSESSMENT.STILL_BLOCKED.label} n={counts.STILL_BLOCKED} />
            <CountChip tone={ASSESSMENT.PARTIALLY_CHANGED.tone} icon={ASSESSMENT.PARTIALLY_CHANGED.icon} label={ASSESSMENT.PARTIALLY_CHANGED.label} n={counts.PARTIALLY_CHANGED} />
            <CountChip tone={ASSESSMENT.WORTH_REASSESSING.tone} icon={ASSESSMENT.WORTH_REASSESSING.icon} label={ASSESSMENT.WORTH_REASSESSING.label} n={counts.WORTH_REASSESSING} />
            <CountChip tone={ASSESSMENT.INSUFFICIENT_EVIDENCE.tone} icon={ASSESSMENT.INSUFFICIENT_EVIDENCE.icon} label={ASSESSMENT.INSUFFICIENT_EVIDENCE.label} n={counts.INSUFFICIENT_EVIDENCE} />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-5">
            {query.isPending && (
              <div role="status" className="space-y-4" aria-label="Loading candidates">
                <Skeleton className="h-56" />
                <Skeleton className="h-56" />
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
            {query.data?.map((f) => <FindingCard key={f.finding_id} card={f} />)}
          </div>

          <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
            <div className={`${card} space-y-2 p-5`}>
              <p className="flex items-center gap-2 font-extrabold text-ink">
                <IconSpark size={18} className="text-brand-ink" /> Found before you asked
              </p>
              <p className="text-sm text-ink-2">
                The Reconsideration Radar continuously analyses past decisions across your organization to find
                opportunities that may be worth a fresh look — so valuable ideas don't stay buried.
              </p>
            </div>

            <div className={`${card} space-y-3 p-5`}>
              <p className="font-extrabold text-ink">Assessment types</p>
              <ul className="space-y-3">
                {Object.entries(ASSESSMENT).map(([key, a]) => (
                  <li key={key} className="flex items-start gap-2.5">
                    <span className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-extrabold uppercase ${a.tone}`}>
                      {a.icon}
                      {a.label}
                    </span>
                    <span className="text-xs leading-relaxed text-ink-2">{a.meaning}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-2 rounded-2xl border border-brand/20 bg-brand-soft p-5">
              <p className="flex items-center gap-2 font-extrabold text-ink">
                <IconBulb size={18} className="text-brand-ink" /> Turn hindsight into progress
              </p>
              <p className="text-sm text-ink-2">
                Combine Radar findings with Ask to dive deeper, validate changes, and build a new business case.
              </p>
              <button
                type="button"
                onClick={() => go.ask('Which rejected or deferred proposals are worth reassessing given what has changed?')}
                className="inline-flex items-center gap-1 text-sm font-bold text-brand-ink"
              >
                Try an example question <IconArrowRight size={14} />
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
