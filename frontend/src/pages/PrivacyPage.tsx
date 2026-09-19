import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconFile,
  IconFlag,
  IconFolder,
  IconLink,
  IconLock,
  IconSearch,
  IconShield,
  IconTrash,
  IconUsers,
} from '../components/icons'
import { Skeleton, Spinner, Tick } from '../components/ui'
import { go } from '../hooks/useRoute'
import { btnDanger, btnPrimary, btnSecondary, card } from '../lib'
import type { PersonSummary, PurgeResult } from '../types/api'

const SURFACES: Record<string, string> = {
  source_files: 'Canonical source files',
  database_rows: 'Database rows and search index',
  database_files: 'Database file, WAL and journal',
  artifacts_and_cache: 'Artifacts and cache',
  person_rows: 'Person, alias and link rows',
}

const STAGES = [
  'Locking the archive',
  'Sanitizing the canonical source',
  'Rebuilding from the sanitized source',
  'Purging database pages and derived files',
  'Verifying every surface',
]

const STEPS = [
  { label: 'Choose', hint: 'Find and select a person' },
  { label: 'Review', hint: 'See what will be affected' },
  { label: 'Confirm', hint: 'Type the name to proceed' },
  { label: 'Verified', hint: 'Removal completed' },
]

const VERIFIED_SURFACES = [
  { icon: <IconFile size={18} />, title: 'Canonical source files', body: 'Documents, emails, chats' },
  { icon: <IconLock size={18} />, title: 'Database rows and search index', body: 'Structured data and index' },
  { icon: <IconFolder size={18} />, title: 'Artifacts and cache', body: 'Embeddings, summaries, exports' },
  { icon: <IconUsers size={18} />, title: 'Person and alias rows', body: 'Known names, emails, and aliases' },
]

const AVATAR_TONES = ['bg-brand-soft text-brand-ink', 'bg-purple-soft text-purple', 'bg-ok-soft text-ok', 'bg-orange-soft text-orange', 'bg-bad-soft text-bad']

function Stepper({ current }: { current: number }) {
  return (
    <ol className="mx-auto flex max-w-2xl items-start justify-between" aria-label="Progress">
      {STEPS.map((step, i) => (
        <li key={step.label} className="flex flex-1 items-start last:flex-none">
          <span className="flex flex-col items-center gap-1 text-center" aria-current={i === current ? 'step' : undefined}>
            <span
              className={`grid size-9 place-items-center rounded-full text-sm font-extrabold transition-colors duration-300 ${
                i < current ? 'bg-ok text-white' : i === current ? 'bg-brand text-white ring-4 ring-brand/25' : 'bg-neutral-soft text-ink-3'
              }`}
            >
              {i < current ? <IconCheck size={16} strokeWidth={3} /> : i + 1}
            </span>
            <span className={`text-xs font-bold ${i <= current ? 'text-ink' : 'text-ink-3'}`}>{step.label}</span>
            <span className="hidden max-w-[9rem] text-xs text-ink-3 sm:block">{step.hint}</span>
          </span>
          {i < STEPS.length - 1 && <span className={`mx-2 mt-[18px] h-0.5 flex-1 ${i < current ? 'bg-ok' : 'bg-line'}`} aria-hidden="true" />}
        </li>
      ))}
    </ol>
  )
}

function Avatar({ name, tone = 0 }: { name: string; tone?: number }) {
  const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  return (
    <span className={`grid size-10 shrink-0 place-items-center rounded-full text-sm font-extrabold ${AVATAR_TONES[tone % AVATAR_TONES.length]}`}>
      {initials}
    </span>
  )
}

function Working({ stage }: { stage: number }) {
  return (
    <div className={`${card} mx-auto max-w-xl space-y-5 p-8 text-center`} role="status" aria-live="polite">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-warn-soft text-warn">
        <IconLock size={28} />
      </span>
      <div>
        <h2 className="shimmer-text text-2xl font-extrabold">{STAGES[stage]}…</h2>
        <p className="mt-1 text-sm text-ink-2">The archive is locked and cannot answer questions until this finishes.</p>
      </div>
      <ol className="mx-auto grid max-w-sm gap-2 text-left">
        {STAGES.map((s, i) => (
          <li key={s} className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold ${i === stage ? 'bg-brand-soft text-ink' : i < stage ? 'text-ink-2' : 'text-ink-3'}`}>
            <span className="grid size-5 place-items-center">{i < stage ? <Tick size={20} /> : i === stage ? <Spinner size={18} /> : <span className="size-2 rounded-full bg-line" />}</span>
            {s}
          </li>
        ))}
      </ol>
    </div>
  )
}

function Result({ result, questions }: { result: PurgeResult; questions: string[] }) {
  return (
    <div className="anim-fade-up mx-auto max-w-2xl space-y-6">
      <div className={`${card} space-y-5 overflow-hidden`}>
        <div className={`flex items-center gap-4 p-6 ${result.verified ? 'bg-ok-soft' : 'bg-bad-soft'}`}>
          <span className={`grid size-14 place-items-center rounded-2xl text-white ${result.verified ? 'bg-ok' : 'bg-bad'}`}>
            {result.verified ? <IconShield size={28} /> : <IconAlert size={28} />}
          </span>
          <div>
            <h2 className="text-2xl font-extrabold">{result.verified ? 'Removal verified' : 'Removal could not be verified'}</h2>
            <p className="text-sm font-semibold text-ink-2">Every surface below was scanned for the person's tracked identifiers.</p>
          </div>
        </div>
        <div className="grid gap-3 px-6 sm:grid-cols-2">
          {[
            [result.files_sanitized, 'source files sanitized'],
            [result.units_anonymized, 'evidence units anonymized'],
            [result.cases_invalidated + (result.findings_invalidated ?? 0), 'dependent Cases and findings invalidated'],
            [result.embeddings_regenerated, `embeddings regenerated${result.embeddings_pending ? `, ${result.embeddings_pending} pending` : ''}`],
          ].map(([n, label]) => (
            <div key={String(label)} className="rounded-xl bg-surface-2 p-3">
              <p className="text-2xl font-extrabold tabular-nums">{n}</p>
              <p className="text-xs font-bold text-ink-2">{label}</p>
            </div>
          ))}
        </div>
        <table className="w-full text-sm">
          <caption className="px-6 pb-2 text-left text-xs font-extrabold uppercase tracking-wide text-ink-3">Tracked identifiers found, per surface</caption>
          <tbody>
            {Object.entries(result.verification).map(([key, count]) => (
              <tr key={key} className="border-t border-line">
                <th scope="row" className="px-6 py-2.5 text-left font-semibold">{SURFACES[key] ?? key}</th>
                <td className={`px-6 py-2.5 text-right font-extrabold ${count === 0 ? 'text-ok' : 'text-bad'}`}>{count === 0 ? '0 · clean' : count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-line bg-surface-2 px-6 py-4 text-xs text-ink-2">
          This is an application-level check of the identifiers the system tracks (names, reviewed aliases, emails) across storage it owns. It is not cryptographic erasure, and it cannot rule out an untracked nickname.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" className={btnPrimary} onClick={() => go.ask()}>
          Ask a question again <IconArrowRight size={16} />
        </button>
        {questions.slice(0, 2).map((q) => (
          <button key={q} type="button" className={btnSecondary} onClick={() => go.ask(q)}>
            Re-ask: {q.length > 60 ? `${q.slice(0, 58)}…` : q}
          </button>
        ))}
      </div>
    </div>
  )
}

export function PrivacyPage() {
  const client = useQueryClient()
  const people = useQuery({ queryKey: ['people'], queryFn: api.people })
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<PersonSummary | null>(null)
  const [typed, setTyped] = useState('')
  const [stage, setStage] = useState(0)
  const [reask, setReask] = useState<string[]>([])

  const preview = useQuery({
    queryKey: ['preview', selected?.person_id],
    queryFn: () => api.preview(selected!.person_id),
    enabled: selected !== null,
  })

  const purge = useMutation({
    mutationFn: async (person: PersonSummary) => {
      // Capture recent questions first: the purge deletes Cases that mention the person.
      const recent = await api.recentCases().catch(() => [])
      const parts = person.canonical_name.toLowerCase().split(/\s+/).filter((p) => p.length >= 3)
      const safe = recent.map((c) => c.query).filter((q) => !parts.some((p) => q.toLowerCase().includes(p)))
      const result = await api.purge(person.person_id)
      return { result, safe }
    },
    onSuccess: ({ safe }) => {
      setReask(safe)
      client.clear()
      setSelected(null)
      setTyped('')
    },
  })

  useEffect(() => {
    if (!purge.isPending) return
    const timer = window.setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1500)
    return () => window.clearInterval(timer)
  }, [purge.isPending])

  const shown = useMemo(() => (people.data ?? []).filter((p) => p.canonical_name.toLowerCase().includes(filter.toLowerCase())), [people.data, filter])
  const confirmed = selected !== null && typed.trim().toLowerCase() === selected.canonical_name.toLowerCase()
  const step = purge.data ? 3 : selected && preview.data ? (typed ? 2 : 1) : 0
  const maxOwn = Math.max(1, ...(people.data ?? []).map((p) => p.author_units + p.speaker_units))

  return (
    <div>
      <section className="hero-bg">
        <div className="mx-auto max-w-4xl space-y-4 px-4 pb-10 pt-12 text-center">
          <span className="inline-flex items-center gap-2 rounded-full bg-surface/80 px-4 py-1.5 text-xs font-extrabold uppercase tracking-[0.14em] text-ink-3 shadow-card">
            Privacy console
          </span>
          <h1 className="text-balance text-4xl font-extrabold tracking-tight text-ink sm:text-5xl">Erase a person. Prove it held.</h1>
          <p className="mx-auto max-w-2xl text-lg text-ink-2">
            Irreversibly anonymize one person from the archive, search index, embeddings, and dependent Cases while
            preserving unrelated evidence.
          </p>
          <span className="mx-auto inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand-soft px-3 py-1.5 text-xs font-bold text-brand-ink">
            <IconFlag size={14} /> EU privacy controls
          </span>
          <div className="pt-4">
            <Stepper current={step} />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-5xl px-4 py-10">
        {purge.isPending && <Working stage={stage} />}
        {purge.isError && (
          <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl border border-bad/40 bg-bad-soft p-4 text-bad">
            <IconAlert size={20} className="mt-0.5 shrink-0" />
            <p className="font-semibold">{purge.error.message} The system stays locked for review; nothing was reported as removed.</p>
          </div>
        )}
        {purge.data && <Result result={purge.data.result} questions={reask} />}

        {!purge.isPending && !purge.data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <section className={`${card} p-5`} aria-labelledby="choose">
              <h2 id="choose" className="text-lg font-extrabold">Choose a person</h2>
              <p className="mb-3 text-sm text-ink-2">Search for a person to see their impact across your organization's memory.</p>
              <label htmlFor="filter" className="sr-only">Filter people</label>
              <div className="relative mb-3">
                <IconSearch size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" />
                <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search by name, email, or alias…" className="min-h-12 w-full rounded-full border border-line bg-surface-2 pl-11 pr-4 font-semibold" />
              </div>
              {people.isPending && <div className="space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>}
              {people.isError && <p role="alert" className="text-bad">{people.error.message}</p>}
              <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto pr-1">
                {shown.map((p, i) => {
                  const own = p.author_units + p.speaker_units
                  const on = selected?.person_id === p.person_id
                  return (
                    <li key={p.person_id}>
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => { setSelected(p); setTyped('') }}
                        className={`flex w-full cursor-pointer items-center gap-3 rounded-2xl border p-3 text-left transition-all duration-200 ${on ? 'border-brand bg-brand-soft shadow-card' : 'border-transparent hover:border-line hover:bg-surface-2'}`}
                      >
                        <span className={`grid size-4 shrink-0 place-items-center rounded-full border-2 ${on ? 'border-brand' : 'border-line'}`} aria-hidden="true">
                          {on && <span className="size-2 rounded-full bg-brand" />}
                        </span>
                        <Avatar name={p.canonical_name} tone={i} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-bold">{p.canonical_name}</span>
                          <span className="mt-1.5 block h-1.5 w-24 overflow-hidden rounded-full bg-line" aria-hidden="true">
                            <span className="anim-bar block h-full rounded-full bg-brand" style={{ width: `${Math.max(3, (own / maxOwn) * 100)}%` }} />
                          </span>
                        </span>
                        <span className="flex shrink-0 gap-4 text-right">
                          <span>
                            <span className="block text-base font-extrabold tabular-nums text-ink">{own}</span>
                            <span className="block text-[11px] font-semibold text-ink-3">authored/spoken</span>
                          </span>
                          <span>
                            <span className="block text-base font-extrabold tabular-nums text-ink">{p.mentioned_units}</span>
                            <span className="block text-[11px] font-semibold text-ink-3">mentioned</span>
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            <section className={`${card} p-5`} aria-labelledby="review">
              <h2 id="review" className="text-lg font-extrabold">Review the impact</h2>
              {!selected && (
                <>
                  <p className="mb-3 text-sm text-ink-2">Select a person to see exactly what would change.</p>
                  <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-line p-6 text-center text-ink-2">
                    <p>Nothing selected yet.</p>
                  </div>
                </>
              )}
              {selected && preview.isPending && <div role="status" className="mt-3 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
              {selected && preview.isError && <p role="alert" className="text-bad">{preview.error.message}</p>}
              {selected && preview.data && (
                <div className="anim-fade-up space-y-5">
                  <p className="mb-1 text-sm text-ink-2">Here's what will be anonymized for {selected.canonical_name}.</p>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { icon: <IconFile size={18} />, n: preview.data.author_units + preview.data.speaker_units, label: 'Units they wrote or spoke', hint: 'Emails, docs, chats, meetings' },
                      { icon: <IconUsers size={18} />, n: preview.data.mentioned_units, label: 'Units that mention them', hint: 'Conversations, docs, threads' },
                      { icon: <IconFolder size={18} />, n: preview.data.files_to_sanitize, label: 'Files to sanitize', hint: 'Source files will be updated' },
                      { icon: <IconLink size={18} />, n: preview.data.cases_to_invalidate + (preview.data.findings_to_invalidate ?? 0), label: 'Dependent Cases to invalidate', hint: 'Evidence references will be removed' },
                    ].map((s) => (
                      <div key={s.label} className="rounded-xl bg-surface-2 p-3">
                        <span className="mb-2 grid size-8 place-items-center rounded-lg bg-brand-soft text-brand-ink">{s.icon}</span>
                        <p className="text-2xl font-extrabold tabular-nums leading-tight">{s.n}</p>
                        <p className="text-xs font-bold text-ink">{s.label}</p>
                        <p className="text-xs text-ink-3">{s.hint}</p>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 rounded-2xl border border-bad/40 bg-bad-soft p-4">
                    <p className="flex items-center gap-2 font-extrabold text-bad"><IconAlert size={18} /> What will happen</p>
                    <p className="text-sm text-ink">
                      We will anonymize this person in source files, rebuild the search index and embeddings, purge
                      derived data, and verify that they no longer appear in any product surfaces. Unrelated evidence
                      will be preserved.
                    </p>
                  </div>

                  <div>
                    <label htmlFor="confirm" className="mb-1.5 block text-sm font-bold text-ink">
                      Type the full name to confirm
                    </label>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        id="confirm"
                        value={typed}
                        onChange={(e) => setTyped(e.target.value)}
                        autoComplete="off"
                        placeholder={selected.canonical_name}
                        className="min-h-12 w-full min-w-0 flex-1 rounded-full border border-line bg-surface px-5 font-semibold"
                      />
                      <button type="button" className={`${btnDanger} shrink-0`} disabled={!confirmed} onClick={() => { setStage(0); purge.mutate(selected) }}>
                        <IconTrash size={18} /> Remove this person
                      </button>
                    </div>
                  </div>

                  <div className="border-t border-line pt-4">
                    <h3 className="mb-3 flex items-center gap-2 text-sm font-extrabold text-ink">
                      <IconShield size={16} className="text-brand-ink" /> What gets verified
                    </h3>
                    <p className="mb-3 text-xs text-ink-2">We check these surfaces to make sure the person is fully removed.</p>
                    <ul className="grid grid-cols-2 gap-3">
                      {VERIFIED_SURFACES.map((v) => (
                        <li key={v.title} className="flex items-start gap-2">
                          <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-ok text-white">
                            <IconCheck size={12} strokeWidth={3.5} />
                          </span>
                          <span>
                            <span className="block text-xs font-bold text-ink">{v.title}</span>
                            <span className="block text-xs text-ink-3">{v.body}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
