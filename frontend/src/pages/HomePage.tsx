import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCalendar,
  IconClock,
  IconFile,
  IconLayers,
  IconRadar,
  IconSearch,
  IconTrash,
  IconUsers,
} from '../components/icons'
import { Thinking } from '../components/Thinking'
import { Skeleton, StatusBadge } from '../components/ui'
import { useCountUp } from '../hooks/useCountUp'
import { go } from '../hooks/useRoute'
import { btnPrimary, card, formatMonth, timeAgo } from '../lib'

const HOW_IT_WORKS = [
  { icon: <IconSearch size={22} />, title: 'Provenance', body: 'See the exact sources for every answer.' },
  { icon: <IconUsers size={22} />, title: 'Attribution', body: 'Know who said what, and when.' },
  { icon: <IconClock size={22} />, title: 'Currency', body: "Understand what's changed since then." },
  { icon: <IconTrash size={22} />, title: 'Deletion', body: 'Respect removals and retention rules.', href: '#/privacy' },
  { icon: <IconRadar size={22} />, title: 'Initiative', body: 'Trace decisions across initiatives and projects.', href: '#/radar' },
] as const

const EXAMPLES = [
  { tag: 'Pricing', q: 'What did we decide about pricing?' },
  { tag: 'Vendor', q: 'Who approved the new vendor?' },
  { tag: 'Q2 plan', q: 'What changed in the Q2 plan?' },
  { tag: 'Risks', q: 'Show me open risks.' },
]

function Stat({ icon, value, label, suffix }: { icon: React.ReactNode; value: number; label: string; suffix?: string }) {
  const n = useCountUp(value)
  return (
    <div className={`${card} flex items-center gap-3 p-4`}>
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">{icon}</span>
      <span className="min-w-0">
        <p className="truncate text-2xl font-extrabold tabular-nums leading-tight tracking-tight text-ink">
          {n.toLocaleString()}
          {suffix}
        </p>
        <p className="text-xs font-semibold text-ink-2">{label}</p>
      </span>
    </div>
  )
}

function DateStat({ from, to }: { from: string | null; to: string | null }) {
  return (
    <div className={`${card} flex items-center gap-3 p-4`}>
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">
        <IconCalendar size={22} />
      </span>
      <span className="min-w-0">
        <p className="whitespace-nowrap text-base font-extrabold leading-tight tracking-tight text-ink sm:text-lg">
          {formatMonth(from)} – {formatMonth(to)}
        </p>
        <p className="text-xs font-semibold text-ink-2">Date range</p>
      </span>
    </div>
  )
}

function Blobs() {
  // Soft pale-blue shapes plus a light dot grid, echoing the reference hero art. Decorative only.
  return (
    <>
      <svg className="pointer-events-none absolute -left-32 -top-24 hidden w-[440px] opacity-40 blur-[2px] md:block dark:opacity-10" viewBox="0 0 400 400" aria-hidden="true">
        <path d="M311 82c46 40 60 112 29 165s-105 87-166 74S52 253 62 187 137 60 200 50s65-8 111 32Z" fill="#bcdcfb" />
      </svg>
      <svg className="pointer-events-none absolute -right-28 -top-16 hidden w-[480px] opacity-40 blur-[2px] md:block dark:opacity-10" viewBox="0 0 400 400" aria-hidden="true">
        <path d="M296 130c30 30 32 84 2 119s-82 46-122 27-64-63-50-105 62-78 105-83 35-8 65 42Z" fill="#bcdcfb" />
      </svg>
      <svg className="pointer-events-none absolute bottom-6 right-8 hidden h-32 w-44 opacity-40 md:block dark:opacity-20" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, row) =>
          Array.from({ length: 8 }).map((_, col) => (
            <circle key={`${row}-${col}`} cx={10 + col * 15} cy={10 + row * 15} r="1.6" fill="#177abf" />
          )),
        )}
      </svg>
    </>
  )
}

export function HomePage({ prefill }: { prefill?: string }) {
  const [question, setQuestion] = useState(prefill ?? '')
  const box = useRef<HTMLInputElement>(null)
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })
  const recent = useQuery({ queryKey: ['recent'], queryFn: api.recentCases })

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(q),
    onSuccess: (receipt) => go.caseView(receipt.case_id),
  })

  useEffect(() => {
    box.current?.focus()
  }, [])

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 3 || ask.isPending) return
    ask.mutate(trimmed)
  }
  const fillExample = (q: string) => {
    setQuestion(q)
    box.current?.focus()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (ask.isPending) return <Thinking question={question.trim()} />

  const s = stats.data
  return (
    <div>
      {/* ------------------------------------------------------------ hero */}
      <section className="hero-bg relative overflow-hidden">
        <Blobs />
        <div className="relative mx-auto max-w-4xl px-4 pb-14 pt-12 text-center">
          <div className="anim-fade-up space-y-4">
            <span className="inline-flex items-center gap-2 rounded-full bg-surface/80 px-4 py-1.5 text-xs font-extrabold uppercase tracking-[0.14em] text-ink-3 shadow-card">
              Evidence-first organizational memory
            </span>
            <h1 className="text-balance text-4xl font-extrabold leading-[1.1] tracking-tight text-ink sm:text-5xl">
              Ask anything.
              <br />
              <span className="text-brand">Get the receipt.</span>
            </h1>
            <p className="mx-auto max-w-2xl text-pretty text-lg text-ink-2">
              Our AI answers questions about what was decided, who agreed, what changed, and what is true now — with
              exact sources and any disagreements shown.
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit(question)
            }}
            className="anim-fade-up mx-auto mt-8 max-w-3xl"
            style={{ animationDelay: '0.1s' }}
          >
            <label htmlFor="question" className="sr-only">
              Your question
            </label>
            <div className="flex flex-col gap-2 rounded-[28px] border border-line bg-surface p-2 shadow-lift transition-shadow duration-200 focus-within:ring-4 focus-within:ring-brand/25 sm:flex-row sm:items-center sm:gap-3 sm:rounded-full sm:py-2 sm:pl-5 sm:pr-2">
              <div className="flex min-w-0 flex-1 items-center gap-3 px-3 pt-1 sm:p-0">
                <IconSearch size={20} className="shrink-0 text-ink-3" />
                <input
                  id="question"
                  ref={box}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      submit(question)
                    }
                  }}
                  maxLength={1000}
                  placeholder="e.g. Did Acme sign off UAT, and what exactly was the scope?"
                  className="min-w-0 flex-1 bg-transparent py-2 text-base text-ink placeholder:text-ink-3 focus:outline-none sm:text-lg"
                />
              </div>
              <button type="submit" className={`${btnPrimary} min-h-11 shrink-0 px-5`} disabled={question.trim().length < 3}>
                Open a Case <IconArrowRight size={18} />
              </button>
            </div>
            <p className="mt-2 hidden pr-3 text-right text-xs font-semibold text-ink-3 sm:block">Press ⌘ + ↵ to submit</p>
            {ask.isError && (
              <div role="alert" className="mt-3 flex items-start gap-3 rounded-2xl border border-bad/40 bg-bad-soft p-4 text-left text-bad">
                <IconAlert size={20} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-bold">
                    {ask.error instanceof ApiError && ask.error.status === 503 ? 'The archive is busy or the reasoning service is down.' : 'That did not work.'}
                  </p>
                  <p className="text-sm">{ask.error.message} Your question is still here, so you can try again.</p>
                </div>
              </div>
            )}
          </form>

          <div className="mx-auto mt-5 flex max-w-3xl flex-wrap items-center justify-center gap-2">
            <span className="text-sm font-semibold text-ink-2">Try an example question:</span>
            {EXAMPLES.map((e) => (
              <button
                key={e.q}
                type="button"
                onClick={() => fillExample(e.q)}
                className="min-h-9 cursor-pointer rounded-full border border-brand/30 bg-surface px-4 py-1.5 text-sm font-semibold text-brand-ink transition-colors duration-200 hover:bg-brand-soft"
              >
                {e.q}
              </button>
            ))}
          </div>

          <div className="mx-auto mt-8 grid max-w-4xl grid-cols-2 gap-4 sm:grid-cols-4">
            {s ? (
              <>
                <Stat icon={<IconFile size={22} />} value={s.documents} label="Documents" />
                <Stat icon={<IconLayers size={22} />} value={s.evidence_units} label="Evidence units" />
                <Stat icon={<IconUsers size={22} />} value={s.people} label="People" />
                <DateStat from={s.first_date} to={s.last_date} />
              </>
            ) : (
              [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[72px]" />)
            )}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-12 px-4 py-12">
        {/* ----------------------------------------------------- how it works */}
        <section aria-labelledby="how-title" className="space-y-6">
          <h2 id="how-title" className="text-2xl font-extrabold tracking-tight text-ink">
            How it works
          </h2>
          <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
            {HOW_IT_WORKS.map((c) => {
              const inner = (
                <>
                  <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand-ink">{c.icon}</span>
                  <h3 className="mt-3 text-base font-extrabold text-ink">{c.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">{c.body}</p>
                </>
              )
              const cls = 'group flex h-full cursor-pointer flex-col items-center text-center'
              return (
                <li key={c.title}>
                  {'href' in c ? (
                    <a href={c.href} className={cls}>
                      {inner}
                    </a>
                  ) : (
                    <span className={cls}>{inner}</span>
                  )}
                </li>
              )
            })}
          </ul>
        </section>

        {/* ------------------------------------------------------ recent cases */}
        <section className={`${card} p-6`}>
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-xl font-extrabold text-ink">Recent Cases</h2>
            {recent.data && recent.data.length > 0 && (
              <a href="#/case" className="inline-flex items-center gap-1 text-sm font-bold text-brand-ink" onClick={(e) => e.preventDefault()}>
                View all <IconArrowRight size={14} />
              </a>
            )}
          </div>
          {recent.isPending && (
            <div className="mt-3 space-y-2">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          )}
          {recent.data?.length === 0 && (
            <p className="mt-4 rounded-xl border border-dashed border-line p-6 text-center text-ink-2">
              No Cases yet. Ask something above and it will appear here.
            </p>
          )}
          <ul className="mt-2 divide-y divide-line">
            {recent.data?.map((c) => (
              <li key={c.case_id}>
                <a href={`#/case/${c.case_id}`} className="group flex cursor-pointer items-center gap-3 py-3.5 transition-colors duration-200 hover:bg-surface-2">
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 font-bold text-ink">{c.query}</span>
                    <span className="text-xs font-semibold text-ink-3">{c.claims} claim{c.claims === 1 ? '' : 's'}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    {c.status ? <StatusBadge status={c.status} /> : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand-ink">
                        <IconClock size={12} /> In progress
                      </span>
                    )}
                    <span className="text-xs font-semibold text-ink-3">{timeAgo(c.created_at)}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
