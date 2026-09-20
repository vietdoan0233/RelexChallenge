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

function CountChip({ a, n, wide }: { a: (typeof ASSESSMENT)[RadarAssessment]; n: number; wide?: boolean }) {
  return (
    <span className={`inline-flex h-[34px] items-center justify-between gap-2 whitespace-nowrap rounded-[10px] border px-2.5 text-[8px] font-bold uppercase ${wide ? "min-w-[157px]" : "min-w-[131px]"} ${a.chip}`}>
      <span className="inline-flex items-center gap-1.5">
        <span className={a.ink}>{a.icon}</span>
        {a.label}
      </span>
      <span className="text-[11px] font-bold tabular-nums">{n}</span>
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
        <div className="mx-auto max-w-[900px] px-4 pb-[19px] pt-1 text-center">
          <p className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-ink-3">Find opportunities in past decisions</p>
          <h1 className="mt-[6px] text-balance text-[30px] font-bold leading-9 tracking-tight text-title">Reconsideration Radar</h1>
          <p className="mx-auto mt-[2px] max-w-[430px] text-[12px] leading-[17px] text-ink-2">
            Surfaces ideas the organization rejected or deferred where the original blocker may have changed. Turn past
            decisions into new possibilities.
          </p>
          <div className="mt-[13px] flex flex-wrap items-center justify-center gap-[33px] gap-y-2">
            <CountChip a={ASSESSMENT.STILL_BLOCKED} n={counts.STILL_BLOCKED} />
            <CountChip a={ASSESSMENT.PARTIALLY_CHANGED} n={counts.PARTIALLY_CHANGED} />
            <CountChip a={ASSESSMENT.WORTH_REASSESSING} n={counts.WORTH_REASSESSING} />
            <CountChip a={ASSESSMENT.INSUFFICIENT_EVIDENCE} n={counts.INSUFFICIENT_EVIDENCE} wide />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1174px] px-4 pb-10">
        <div className="grid gap-[17px] lg:grid-cols-[minmax(0,1fr)_248px]">
          <div className="min-w-0 space-y-[7px]">
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

          <aside className="space-y-[10px] lg:self-start">
            <div className={`${card} space-y-1 px-[14px] py-[12px]`}>
              <p className="flex items-center gap-2 text-[12px] font-bold text-ink">
                <IconSpark size={15} className="text-brand" /> Found before you asked
              </p>
              <p className="text-[10px] leading-[14px] text-ink-2">
                The Reconsideration Radar analyses past decisions across your organization ahead of time (findings are precomputed) to find
                opportunities that may be worth a fresh look — so valuable ideas don't stay buried.
              </p>
            </div>

            <div className={`${card} px-[14px] py-[12px]`}>
              <p className="mb-[17px] text-[12px] font-bold text-ink">Assessment types</p>
              <ul className="space-y-[21px]">
                {[ASSESSMENT.WORTH_REASSESSING, ASSESSMENT.PARTIALLY_CHANGED, ASSESSMENT.STILL_BLOCKED, ASSESSMENT.INSUFFICIENT_EVIDENCE].map((a) => (
                  <li key={a.label} className="flex items-start gap-3">
                    <span className={`mt-px shrink-0 [&>svg]:size-5 ${a.ink}`}>{a.icon}</span>
                    <span className="leading-tight">
                      <span className="block text-[8.5px] font-bold uppercase tracking-wide text-ink">{a.label}</span>
                      <span className="block text-[9.5px] leading-[13px] text-ink-2">{a.meaning}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-[10px] border border-brand/20 bg-brand-soft px-[14px] pb-[14px] pt-[13px]">
              <p className="flex items-center gap-2 text-[12px] font-bold text-ink">
                <IconBulb size={15} className="text-brand-ink" /> Turn hindsight into progress
              </p>
              <p className="mt-1 text-[10px] leading-[14px] text-ink-2">
                Combine Radar findings with Ask to dive deeper, validate changes, and build a new business case.
              </p>
              <button
                type="button"
                onClick={() => go.ask('Which rejected or deferred proposals are worth reassessing given what has changed?')}
                className="mt-2 inline-flex cursor-pointer items-center gap-1 text-[10px] font-bold text-brand-ink"
              >
                Try an example question <IconArrowRight size={12} />
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
