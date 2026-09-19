import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconClock,
  IconFile,
  IconGitBranch,
  IconLayers,
  IconRadar,
  IconScale,
  IconSearch,
  IconShield,
  IconTrash,
  IconUsers,
} from '../components/icons'
import { Thinking } from '../components/Thinking'
import { Eyebrow, Skeleton, StatusBadge } from '../components/ui'
import { useCountUp } from '../hooks/useCountUp'
import { go } from '../hooks/useRoute'
import { btnPrimary, btnSecondary, card, formatMonth, timeAgo } from '../lib'

const CAPABILITIES = [
  {
    icon: <IconFile size={22} />,
    tone: 'bg-brand-soft text-brand-ink',
    title: 'Provenance',
    body: 'Every figure and claim points to the exact source, in context.',
    ask: 'What did the master-data assessment report as complete in September 2024? Give every figure and the document each comes from.',
  },
  {
    icon: <IconUsers size={22} />,
    tone: 'bg-purple-soft text-purple',
    title: 'Attribution',
    body: 'Proposal, agreement or objection? It tells them apart, and says who.',
    ask: 'Who proposed removing the operator ID field from the data extract, who agreed, and had it already been sent anywhere by then?',
  },
  {
    icon: <IconClock size={22} />,
    tone: 'bg-orange-soft text-orange',
    title: 'Currency',
    body: 'What is true now, which is not always what is newest.',
    ask: 'Is bakery inside the fresh workstream? Show how the answer changed over time and what it is now.',
  },
  {
    icon: <IconTrash size={22} />,
    tone: 'bg-bad-soft text-bad',
    title: 'Deletion',
    body: 'Erase a person from the archive and everything derived from it, verifiably.',
    href: '#/privacy',
  },
  {
    icon: <IconRadar size={22} />,
    tone: 'bg-ok-soft text-ok',
    title: 'Initiative',
    body: 'Ideas the organization said no to, where the reason may have changed.',
    href: '#/radar',
  },
] as const

const EXAMPLES = [
  { tag: 'Sign-off', q: 'Did Acme sign off UAT for the programme, and what was the scope?' },
  { tag: 'Status vs reality', q: 'The weekly reports say the nightly extract completed with no errors. Is that true?' },
  { tag: 'Figures', q: 'What proportion of articles had shelf-life data populated? Give every figure with its date and source, and say which is current.' },
  { tag: 'Agreements', q: 'What service levels were agreed for ordering, and in which meeting?' },
]

const STEPS = [
  { icon: <IconSearch size={20} />, title: 'Retrieve', body: 'Hybrid keyword and semantic search across every meeting, email and report.' },
  { icon: <IconLayers size={20} />, title: 'Answer', body: 'Structured claims, each tied to evidence by ID. Never a guess.' },
  { icon: <IconGitBranch size={20} />, title: 'Challenge', body: 'A skeptic searches for what would make the answer wrong.' },
  { icon: <IconShield size={20} />, title: 'Verify', body: 'Every citation is checked against the archive before you see it.' },
]

function Stat({ value, label, suffix }: { value: number; label: string; suffix?: string }) {
  const n = useCountUp(value)
  return (
    <div className="rounded-2xl border border-line bg-surface/80 p-4 text-center shadow-card backdrop-blur">
      <p className="text-3xl font-extrabold tabular-nums tracking-tight text-ink">
        {n.toLocaleString()}
        {suffix}
      </p>
      <p className="mt-0.5 text-xs font-bold uppercase tracking-wide text-ink-3">{label}</p>
    </div>
  )
}

function Blobs() {
  // Soft organic shapes echoing RELEX's hero art. Decorative only.
  return (
    <svg className="anim-float pointer-events-none absolute -right-24 -top-16 hidden w-[520px] opacity-70 md:block dark:opacity-15" viewBox="0 0 400 400" aria-hidden="true">
      <path d="M311 82c46 40 60 112 29 165s-105 87-166 74S52 253 62 187 137 60 200 50s65-8 111 32Z" fill="#c2dfff" opacity=".55" />
      <path d="M296 130c30 30 32 84 2 119s-82 46-122 27-64-63-50-105 62-78 105-83 35-8 65 42Z" fill="#80c5ef" opacity=".35" />
      <circle cx="300" cy="300" r="34" fill="#ac8bc2" opacity=".3" />
      <circle cx="90" cy="110" r="18" fill="#ef8638" opacity=".28" />
    </svg>
  )
}

export function HomePage({ prefill }: { prefill?: string }) {
  const [question, setQuestion] = useState(prefill ?? '')
  const box = useRef<HTMLTextAreaElement>(null)
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
        <div className="relative mx-auto max-w-4xl px-4 pb-14 pt-14 text-center sm:pt-20">
          <div className="anim-fade-up space-y-5">
            <span className="inline-flex items-center gap-2 rounded-full bg-surface/80 px-4 py-1.5 text-xs font-extrabold uppercase tracking-[0.14em] text-brand-ink shadow-card">
              <IconShield size={14} /> Evidence-first organizational memory
            </span>
            <h1 className="text-balance text-4xl font-extrabold leading-[1.05] tracking-tight text-ink sm:text-6xl">
              Ask anything.
              <br />
              <span className="bg-gradient-to-r from-brand to-purple bg-clip-text text-transparent">
                Get the receipt.
              </span>
            </h1>
            <p className="mx-auto max-w-2xl text-pretty text-lg text-ink-2">
              What was decided, who agreed, what changed and what is true now. Every answer shows the exact
              sources, the evidence that disagrees, and what nobody can establish.
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
            <div className="rounded-[28px] border border-line bg-surface p-2 shadow-lift transition-shadow duration-200 focus-within:ring-4 focus-within:ring-brand/25">
              <textarea
                id="question"
                ref={box}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submit(question)
                  }
                }}
                rows={2}
                maxLength={1000}
                placeholder="e.g. Did Acme sign off UAT, and what exactly was the scope?"
                className="block w-full resize-none rounded-3xl bg-transparent px-5 pb-1 pt-4 text-lg text-ink placeholder:text-ink-3 focus:outline-none"
                style={{ outline: 'none' }}
              />
              <div className="flex items-center justify-between gap-3 px-3 pb-2">
                <span className="hidden text-xs font-semibold text-ink-3 sm:block">
                  Enter to ask · Shift+Enter for a new line
                </span>
                <button type="submit" className={`${btnPrimary} ml-auto min-h-12 px-6 text-base`} disabled={question.trim().length < 3}>
                  Open a Case <IconArrowRight size={18} />
                </button>
              </div>
            </div>
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

          <div className="mx-auto mt-6 flex max-w-3xl flex-wrap justify-center gap-2">
            {EXAMPLES.map((e) => (
              <button
                key={e.q}
                type="button"
                onClick={() => fillExample(e.q)}
                className="group min-h-11 cursor-pointer rounded-full border border-line bg-surface/80 px-4 py-2 text-sm font-semibold text-ink-2 backdrop-blur transition-all duration-200 hover:border-brand hover:bg-surface hover:text-ink"
              >
                <span className="mr-2 text-xs font-extrabold uppercase text-brand-ink">{e.tag}</span>
                <span className="sr-only sm:not-sr-only">{e.q.length > 58 ? `${e.q.slice(0, 56)}…` : e.q}</span>
              </button>
            ))}
          </div>

          <div className="mx-auto mt-10 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4">
            {s ? (
              <>
                <Stat value={s.documents} label="Documents" />
                <Stat value={s.evidence_units} label="Evidence units" />
                <Stat value={s.people} label="People" />
                <div className="rounded-2xl border border-line bg-surface/80 p-4 text-center shadow-card backdrop-blur">
                  <p className="whitespace-nowrap text-base font-extrabold leading-9 tracking-tight text-ink sm:text-lg">
                    {formatMonth(s.first_date)} – {formatMonth(s.last_date)}
                  </p>
                  <p className="mt-0.5 text-xs font-bold uppercase tracking-wide text-ink-3">Time span</p>
                </div>
              </>
            ) : (
              [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[88px]" />)
            )}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-16 px-4 py-14">
        {/* ------------------------------------------------- capabilities */}
        <section aria-labelledby="cap-title" className="space-y-6">
          <div className="space-y-2 text-center">
            <Eyebrow>What it does well</Eyebrow>
            <h2 id="cap-title" className="text-balance text-3xl font-extrabold tracking-tight">
              Built for the questions that go wrong
            </h2>
          </div>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {CAPABILITIES.map((c) => {
              const inner = (
                <>
                  <span className={`grid size-11 place-items-center rounded-2xl ${c.tone}`}>{c.icon}</span>
                  <h3 className="mt-4 text-lg font-extrabold">{c.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">{c.body}</p>
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-brand-ink">
                    {'href' in c ? 'Open' : 'Try it'} <IconArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-1" />
                  </span>
                </>
              )
              const cls = `${card} group flex h-full cursor-pointer flex-col p-5 text-left transition-all duration-200 hover:-translate-y-1 hover:border-brand hover:shadow-lift`
              return (
                <li key={c.title}>
                  {'href' in c ? (
                    <a href={c.href} className={cls}>
                      {inner}
                    </a>
                  ) : (
                    <button type="button" className={`${cls} w-full`} onClick={() => fillExample(c.ask)}>
                      {inner}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        </section>

        {/* ----------------------------------------------------- how it works */}
        <section aria-labelledby="how-title" className="space-y-6">
          <div className="space-y-2 text-center">
            <Eyebrow>How an answer is made</Eyebrow>
            <h2 id="how-title" className="text-3xl font-extrabold tracking-tight">
              The model interprets. The archive decides.
            </h2>
          </div>
          <ol className="grid gap-4 md:grid-cols-4">
            {STEPS.map((step, i) => (
              <li key={step.title} className={`${card} relative p-5`}>
                <span className="absolute right-4 top-3 text-5xl font-extrabold text-brand-soft" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="grid size-10 place-items-center rounded-xl bg-deep text-white">{step.icon}</span>
                <h3 className="mt-3 text-lg font-extrabold">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-ink-2">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ------------------------------------------- recent cases + radar */}
        <section className="grid gap-6 lg:grid-cols-5">
          <div className={`${card} p-6 lg:col-span-3`}>
            <h2 className="text-xl font-extrabold">Recent Cases</h2>
            <p className="mb-4 text-sm text-ink-2">Pick up where you left off.</p>
            {recent.isPending && (
              <div className="space-y-2">
                <Skeleton className="h-14" />
                <Skeleton className="h-14" />
              </div>
            )}
            {recent.data?.length === 0 && (
              <p className="rounded-xl border border-dashed border-line p-6 text-center text-ink-2">
                No Cases yet. Ask something above and it will appear here.
              </p>
            )}
            <ul className="space-y-2">
              {recent.data?.map((c) => (
                <li key={c.case_id}>
                  <a
                    href={`#/case/${c.case_id}`}
                    className="group flex cursor-pointer items-center gap-3 rounded-xl border border-transparent p-3 transition-colors duration-200 hover:border-line hover:bg-surface-2"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 font-bold text-ink">{c.query}</span>
                      <span className="text-xs font-semibold text-ink-3">
                        {timeAgo(c.created_at)} · {c.claims} claim{c.claims === 1 ? '' : 's'}
                      </span>
                    </span>
                    {c.status && <StatusBadge status={c.status} />}
                    <IconArrowRight size={18} className="shrink-0 text-ink-3 transition-transform duration-200 group-hover:translate-x-1" />
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <a
            href="#/radar"
            className="group relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-2xl bg-gradient-to-br from-deep to-[#1884c5] p-6 text-white shadow-lift transition-transform duration-200 hover:-translate-y-1 lg:col-span-2"
          >
            <span className="anim-float pointer-events-none absolute -right-10 -top-10 size-44 rounded-full bg-white/10" aria-hidden="true" />
            <div className="relative space-y-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-white/15">
                <IconRadar size={24} />
              </span>
              <h2 className="text-2xl font-extrabold leading-tight">Reconsideration Radar</h2>
              <p className="text-white/85">
                Ideas that were rejected or deferred, where the reason for saying no may have changed. Found before you asked.
              </p>
            </div>
            <span className="relative mt-6 inline-flex items-center gap-2 text-sm font-bold">
              {s ? `${s.radar_findings} candidate${s.radar_findings === 1 ? '' : 's'} surfaced` : 'View candidates'}
              <IconArrowRight size={18} className="transition-transform duration-200 group-hover:translate-x-1" />
            </span>
          </a>
        </section>

        {/* ------------------------------------------------------ trust band */}
        <section className="rounded-3xl bg-deep p-8 text-white shadow-lift sm:p-10">
          <div className="grid gap-6 md:grid-cols-3">
            {[
              { icon: <IconShield size={22} />, t: 'Nothing invented', b: 'A citation the archive cannot confirm is rejected before you see it.' },
              { icon: <IconScale size={22} />, t: 'Newer is not truer', b: 'Conflicts are shown and weighed, not averaged away.' },
              { icon: <IconTrash size={22} />, t: 'Erasure that holds', b: 'A removed person stays removed, even after a full rebuild.' },
            ].map((x) => (
              <div key={x.t} className="flex gap-4">
                <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white/12">{x.icon}</span>
                <div>
                  <h3 className="text-lg font-extrabold">{x.t}</h3>
                  <p className="text-sm text-white/80">{x.b}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" className={`${btnPrimary} bg-white !text-deep hover:!bg-brand-soft`} onClick={() => { box.current?.focus(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>
              Ask a question
            </button>
            <a href="#/privacy" className={`${btnSecondary} border-white/30 bg-transparent !text-white hover:bg-white/10`}>
              Open the Privacy console
            </a>
          </div>
        </section>
      </div>
    </div>
  )
}
