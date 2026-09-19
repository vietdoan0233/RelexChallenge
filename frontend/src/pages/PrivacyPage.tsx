import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { IconAlert, IconArrowRight, IconCheck, IconLock, IconSearch, IconShield, IconTrash } from '../components/icons'
import { Eyebrow, Skeleton, Spinner, Tick } from '../components/ui'
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

const STEPS = ['Choose', 'Review', 'Confirm', 'Verified']

function Stepper({ current }: { current: number }) {
  return (
    <ol className="mx-auto flex max-w-xl items-center justify-between" aria-label="Progress">
      {STEPS.map((label, i) => (
        <li key={label} className="flex flex-1 items-center last:flex-none">
          <span className="flex flex-col items-center gap-1" aria-current={i === current ? 'step' : undefined}>
            <span
              className={`grid size-9 place-items-center rounded-full text-sm font-extrabold transition-colors duration-300 ${
                i < current ? 'bg-ok text-white' : i === current ? 'bg-brand text-white ring-4 ring-brand/25' : 'bg-neutral-soft text-ink-3'
              }`}
            >
              {i < current ? <IconCheck size={16} strokeWidth={3} /> : i + 1}
            </span>
            <span className={`text-xs font-bold ${i <= current ? 'text-ink' : 'text-ink-3'}`}>{label}</span>
          </span>
          {i < STEPS.length - 1 && <span className={`mx-2 mb-5 h-0.5 flex-1 ${i < current ? 'bg-ok' : 'bg-line'}`} aria-hidden="true" />}
        </li>
      ))}
    </ol>
  )
}

function Avatar({ name }: { name: string }) {
  const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  return <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-extrabold text-brand-ink">{initials}</span>
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
        <div className="mx-auto max-w-4xl space-y-5 px-4 pb-10 pt-14 text-center">
          <span className="mx-auto grid size-16 place-items-center rounded-3xl bg-deep text-white shadow-lift">
            <IconTrash size={30} />
          </span>
          <Eyebrow>Privacy console</Eyebrow>
          <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl">Erase a person. Prove it held.</h1>
          <p className="mx-auto max-w-2xl text-lg text-ink-2">
            Irreversibly anonymize one person out of the archive, its search index, its embeddings and every Case that
            depended on them. Unrelated organizational evidence is kept.
          </p>
          <Stepper current={step} />
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
              <h2 id="choose" className="mb-3 text-lg font-extrabold">1 · Choose a person</h2>
              <label htmlFor="filter" className="sr-only">Filter people</label>
              <div className="relative mb-3">
                <IconSearch size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" />
                <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name" className="min-h-12 w-full rounded-full border border-line bg-surface-2 pl-11 pr-4 font-semibold" />
              </div>
              {people.isPending && <div className="space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>}
              {people.isError && <p role="alert" className="text-bad">{people.error.message}</p>}
              <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto pr-1">
                {shown.map((p) => {
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
                        <Avatar name={p.canonical_name} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-bold">{p.canonical_name}</span>
                          <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-line" aria-hidden="true">
                            <span className="anim-bar block h-full rounded-full bg-brand" style={{ width: `${Math.max(3, (own / maxOwn) * 100)}%` }} />
                          </span>
                        </span>
                        <span className="text-right text-xs font-semibold text-ink-3">
                          {own} own<br />{p.mentioned_units} mentioned
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            <section className={`${card} p-5`} aria-labelledby="review">
              <h2 id="review" className="mb-3 text-lg font-extrabold">2 · Review the impact</h2>
              {!selected && (
                <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-line p-6 text-center text-ink-2">
                  <p>Select a person to see exactly what would change.</p>
                </div>
              )}
              {selected && preview.isPending && <div role="status" className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
              {selected && preview.isError && <p role="alert" className="text-bad">{preview.error.message}</p>}
              {selected && preview.data && (
                <div className="anim-fade-up space-y-5">
                  <div className="flex items-center gap-3">
                    <Avatar name={selected.canonical_name} />
                    <p className="text-lg font-extrabold">{selected.canonical_name}</p>
                  </div>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    {[
                      ['Units they wrote or spoke', preview.data.author_units + preview.data.speaker_units],
                      ['Units that mention them', preview.data.mentioned_units],
                      ['Units to anonymize', preview.data.units_to_anonymize],
                      ['Source files to sanitize', preview.data.files_to_sanitize],
                      ['Cases to invalidate', preview.data.cases_to_invalidate],
                      ['Radar findings to invalidate', preview.data.findings_to_invalidate ?? 0],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="rounded-xl bg-surface-2 p-3">
                        <dt className="text-xs font-bold text-ink-3">{label}</dt>
                        <dd className="text-2xl font-extrabold tabular-nums">{value}</dd>
                      </div>
                    ))}
                  </dl>

                  <div className="space-y-3 rounded-2xl border-2 border-bad/50 bg-bad-soft p-4">
                    <p className="flex items-center gap-2 font-extrabold text-bad"><IconAlert size={18} /> Danger zone: this cannot be undone</p>
                    <p className="text-sm text-ink">It rewrites the app-owned canonical source. Names become anonymous markers; unrelated evidence stays.</p>
                    <label htmlFor="confirm" className="block text-sm font-bold text-ink">
                      Type “{selected.canonical_name}” to confirm
                    </label>
                    <input id="confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" className="min-h-12 w-full rounded-full border border-bad/50 bg-surface px-5 font-semibold" />
                    <button type="button" className={`${btnDanger} w-full`} disabled={!confirmed} onClick={() => { setStage(0); purge.mutate(selected) }}>
                      <IconTrash size={18} /> Permanently remove this person
                    </button>
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
