import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCalendar,
  IconCheck,
  IconClock,
  IconFile,
  IconLayers,
  IconRadar,
  IconSearch,
  IconTrash,
  IconUsers,
} from '../components/icons'
import { Thinking } from '../components/Thinking'
import { Skeleton } from '../components/ui'
import { useCountUp } from '../hooks/useCountUp'
import { go } from '../hooks/useRoute'
import { card, formatMonth, timeAgo } from '../lib'

const HOW_IT_WORKS = [
  { icon: <IconSearch size={20} />, title: 'Provenance', body: 'See the exact sources for every answer.' },
  { icon: <IconUsers size={20} />, title: 'Attribution', body: 'Know who said what, and when.' },
  { icon: <IconClock size={20} />, title: 'Currency', body: "Understand what's changed since then." },
  { icon: <IconTrash size={20} />, title: 'Deletion', body: 'Respect removals and retention rules.', href: '#/privacy' },
  { icon: <IconRadar size={20} />, title: 'Initiative', body: 'Trace decisions across initiatives and projects.', href: '#/radar' },
] as const

const EXAMPLES = [
  { tag: 'Pricing', q: 'What did we decide about pricing?' },
  { tag: 'Vendor', q: 'Who approved the new vendor?' },
  { tag: 'Q2 plan', q: 'What changed in the Q2 plan?' },
  { tag: 'Risks', q: 'Show me open risks.' },
]

function Stat({ icon, value, label }: { icon: React.ReactNode; value: number; label: string }) {
  const n = useCountUp(value)
  return (
    <div className={`${card} flex h-[74px] items-center gap-[22px] px-[16px]`}>
      <span className="grid size-[46px] shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">{icon}</span>
      <span className="min-w-0">
        <p className="truncate text-xl font-bold tabular-nums leading-tight text-ink">{n.toLocaleString()}</p>
        <p className="text-[13px] leading-tight text-ink-2">{label}</p>
      </span>
    </div>
  )
}

function DateStat({ from, to }: { from: string | null; to: string | null }) {
  return (
    <div className={`${card} flex h-[74px] items-center gap-[22px] px-[16px]`}>
      <span className="grid size-[46px] shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
        <IconCalendar size={22} />
      </span>
      <span className="min-w-0">
        <p className="whitespace-nowrap text-[17px] font-bold leading-tight text-ink">
          {formatMonth(from)} – {formatMonth(to)}
        </p>
        <p className="text-[13px] leading-tight text-ink-2">Date range</p>
      </span>
    </div>
  )
}

export function HomePage({ prefill }: { prefill?: string }) {
  const [question, setQuestion] = useState(prefill ?? '')
  const box = useRef<HTMLTextAreaElement>(null)
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats })
  const [showAllCases, setShowAllCases] = useState(false)
  const recent = useQuery({ queryKey: ['recent', showAllCases], queryFn: () => api.recentCases(showAllCases ? 30 : 6) })

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
    <div className="mx-auto max-w-[1208px] px-4 pb-12">
      {/* ------------------------------------------------------------ hero */}
      <section className="mx-auto max-w-[900px] pt-[24px] text-center">
        <div className="anim-fade-up">
          <p className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-ink-3">Evidence-first organizational memory</p>
          <h1 className="mt-[9px] text-balance text-[40px] font-bold leading-[41px] tracking-tight text-ink">
            Ask anything.
            <br />
            <span className="text-brand">Get the receipt.</span>
          </h1>
          <p className="mx-auto mt-[6px] max-w-[500px] text-pretty text-sm leading-5 text-ink-2">
            Our AI answers questions about what was decided, who agreed, what changed, and what is true now — with exact
            sources and any disagreements shown.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit(question)
          }}
          className="anim-fade-up mx-auto mt-[21px] max-w-[848px]"
          style={{ animationDelay: '0.1s' }}
        >
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <div className="rounded-2xl border border-line bg-surface/90 p-3 shadow-card transition-colors duration-200 focus-within:border-brand/30">
            <div className="relative h-[72px] rounded-[10px] border border-line bg-surface">
              <IconSearch size={18} className="absolute left-3 top-[14px] text-brand" />
              <textarea
                id="question"
                ref={box}
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submit(question)
                  }
                }}
                maxLength={1000}
                placeholder="e.g. Did Acme sign off UAT, and what exactly was the scope?"
                className="absolute inset-y-0 left-10 right-[160px] resize-none bg-transparent pt-[15px] text-[13px] leading-[1.4] text-ink placeholder:text-ink-3 focus:outline-none"
              />
              <button
                type="submit"
                className="absolute right-0 top-[3px] inline-flex h-9 w-[126px] cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand text-[13px] font-semibold text-white transition-colors duration-200 hover:bg-brand-strong disabled:cursor-not-allowed"
                disabled={question.trim().length < 3}
              >
                Open a Case <IconArrowRight size={15} />
              </button>
              <p className="pointer-events-none absolute bottom-[7px] right-3 hidden text-[10px] text-ink-3 sm:block">Press ⌘ ↵ to submit</p>
            </div>
          </div>
          {ask.isError && (
            <div role="alert" className="mt-3 flex items-start gap-3 rounded-xl border border-bad/40 bg-bad-soft p-4 text-left text-bad">
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

        <div className="mx-auto mt-[15px] flex max-w-[900px] flex-wrap items-center justify-center gap-x-[7px] gap-y-2">
          <span className="mr-1 text-[10px] text-ink-2">Try an example question:</span>
          {EXAMPLES.map((e) => (
            <button
              key={e.q}
              type="button"
              onClick={() => fillExample(e.q)}
              className="h-[30px] cursor-pointer rounded-full border border-brand/40 bg-surface/80 px-[13px] text-[10px] font-medium text-brand-ink transition-colors duration-200 hover:bg-brand-soft"
            >
              {e.q}
            </button>
          ))}
        </div>
      </section>

      <div className="mt-[27px] grid grid-cols-2 gap-[14px] lg:grid-cols-4">
        {s ? (
          <>
            <Stat icon={<IconFile size={22} />} value={s.documents} label="Documents" />
            <Stat icon={<IconLayers size={22} />} value={s.evidence_units} label="Evidence units" />
            <Stat icon={<IconUsers size={22} />} value={s.people} label="People" />
            <DateStat from={s.first_date} to={s.last_date} />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[74px]" />)
        )}
      </div>

      <div className="mt-[22px] grid gap-[19px] lg:grid-cols-[minmax(0,1fr)_461px]">
        {/* ----------------------------------------------------- how it works */}
        <section aria-labelledby="how-title">
          <h2 id="how-title" className="mb-[8px] mt-[3px] text-base font-bold text-ink">
            How it works
          </h2>
          <ul className="grid grid-cols-2 gap-[9px] sm:grid-cols-3 lg:grid-cols-5">
            {HOW_IT_WORKS.map((c) => {
              const inner = (
                <>
                  <span className="grid size-[38px] shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">{c.icon}</span>
                  <h3 className="mt-[9px] text-[13px] font-bold leading-4 text-ink">{c.title}</h3>
                  <p className="mt-2 text-[11px] leading-[15px] text-ink-2">{c.body}</p>
                </>
              )
              const cls = `${card} flex h-[141px] cursor-pointer flex-col items-start px-[15px] pb-[11px] pt-[14px] text-left transition-shadow duration-200 hover:shadow-lift`
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
        <section className={`${card} self-start px-[15px] pb-[6px] pt-3`}>
          <div className="mb-1 flex h-5 items-center justify-between">
            <h2 className="text-[15px] font-bold text-ink">Recent Cases</h2>
            {recent.data && (showAllCases || recent.data.length > 3) && (
              <button
                type="button"
                aria-expanded={showAllCases}
                onClick={() => setShowAllCases((v) => !v)}
                className="inline-flex cursor-pointer items-center gap-1 text-[11px] font-semibold text-brand-ink hover:underline"
              >
                {showAllCases ? 'Show fewer' : 'View all'} <IconArrowRight size={13} />
              </button>
            )}
          </div>
          {recent.isPending && (
            <div className="space-y-2 pb-3">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          )}
          {recent.data?.length === 0 && (
            <p className="mb-3 rounded-lg border border-dashed border-line p-5 text-center text-sm text-ink-2">
              No Cases yet. Ask something above and it will appear here.
            </p>
          )}
          <ul className={`divide-y divide-line border-t border-line ${showAllCases ? "max-h-[330px] overflow-y-auto" : ""}`}>
            {recent.data?.slice(0, showAllCases ? 30 : 3).map((c) => (
              <li key={c.case_id}>
                <a href={`#/case/${c.case_id}`} className="group flex h-[44px] cursor-pointer items-center gap-3 transition-colors duration-200">
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 text-[11.5px] font-semibold leading-tight text-ink">{c.query}</span>
                    <span className="block text-[9.5px] leading-tight text-ink-3">
                      {c.claims} claim{c.claims === 1 ? '' : 's'}
                    </span>
                  </span>
                  <span
                    className={`inline-flex h-6 w-[83px] shrink-0 items-center justify-center gap-1 rounded-full border text-[10.5px] font-semibold ${
                      c.status ? 'border-[#b9e2cf] bg-[#eef9f3] text-ok' : 'border-brand/30 bg-brand-soft text-brand-ink'
                    }`}
                  >
                    {c.status ? <IconCheck size={11} strokeWidth={3} /> : <IconClock size={11} />}
                    {c.status ? 'Completed' : 'In progress'}
                  </span>
                  <span className="w-[42px] shrink-0 text-right text-[11px] text-ink-3">{timeAgo(c.created_at).replace(' ago', ' ago')}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
