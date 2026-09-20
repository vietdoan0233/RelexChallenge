import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconFile,
  IconFolder,
  IconLink,
  IconLock,
  IconSearch,
  IconShield,
  IconUsers,
} from '../components/icons'
import { Skeleton, Spinner, Tick } from '../components/ui'
import { EuFlag } from '../components/Logo'
import { go } from '../hooks/useRoute'
import { btnPrimary, btnSecondary, card } from '../lib'
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

const AVATAR_TONES = ['bg-brand-soft text-brand-ink']

function Stepper({ current }: { current: number }) {
  return (
    <ol className="mx-auto flex max-w-[812px] items-center" aria-label="Progress">
      {STEPS.map((step, i) => (
        <li key={step.label} className="flex flex-1 items-center last:flex-none">
          <span className="flex items-center gap-[10px] text-left" aria-current={i === current ? 'step' : undefined}>
            <span
              className={`grid size-[30px] shrink-0 place-items-center rounded-full text-[13px] font-bold transition-colors duration-300 ${
                i < current ? 'bg-ok text-white' : i === current ? 'bg-brand text-white' : 'bg-brand-soft text-ink-2'
              }`}
            >
              {i < current ? <IconCheck size={14} strokeWidth={3} /> : i + 1}
            </span>
            <span className="hidden leading-tight sm:block">
              <span className="block text-[12px] font-bold text-ink">{step.label}</span>
              <span className="block text-[10px] text-ink-3">{step.hint}</span>
            </span>
          </span>
          {i < STEPS.length - 1 && <span className="mx-[10px] h-px flex-1 bg-line" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  )
}

function Avatar({ name, tone = 0 }: { name: string; tone?: number }) {
  const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  return (
    <span className={`grid size-9 shrink-0 place-items-center rounded-full text-[12px] font-semibold ${AVATAR_TONES[tone % AVATAR_TONES.length]}`}>
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
        <div className="mx-auto max-w-[900px] px-4 pb-[22px] pt-[14px] text-center">
          <p className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-ink-3">Privacy console</p>
          <h1 className="mt-[2px] text-balance text-[30px] font-bold leading-9 tracking-tight text-ink">Erase a person. Prove it held.</h1>
          <p className="mx-auto mt-[3px] max-w-[560px] text-[13.5px] leading-[19px] text-ink-2">
            Irreversibly anonymize one person's tracked names, aliases and emails across the archive, search index, embeddings, and dependent Cases while
            preserving unrelated evidence.
          </p>
          <span className="mt-[6px] inline-flex h-[21px] items-center gap-2 rounded-full border border-line bg-surface/80 px-3 text-[10px] font-medium text-ink-2">
            <EuFlag width={18} /> EU privacy controls
          </span>
          <div className="mt-[19px]">
            <Stepper current={step} />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1129px] px-4 pb-10 pt-[6px]">
        {purge.isPending && <Working stage={stage} />}
        {purge.isError && (
          <div role="alert" className="mb-6 flex items-start gap-3 rounded-xl border border-bad/40 bg-bad-soft p-4 text-bad">
            <IconAlert size={20} className="mt-0.5 shrink-0" />
            <p className="font-semibold">{purge.error.message} The system stays locked for review; nothing was reported as removed.</p>
          </div>
        )}
        {purge.data && <Result result={purge.data.result} questions={reask} />}

        {!purge.isPending && !purge.data && (
          <div className="grid gap-[15px] lg:grid-cols-2">
            <section className={`${card} px-[17px] pb-[14px] pt-[15px]`} aria-labelledby="choose">
              <h2 id="choose" className="text-[17px] font-bold leading-6">Choose a person</h2>
              <p className="mb-[13px] -mt-px text-[11px] text-ink-2">Search for a person to see their impact across your organization's memory.</p>
              <label htmlFor="filter" className="sr-only">Filter people</label>
              <div className="relative mb-[17px]">
                <IconSearch size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-2" />
                <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search by name, email, or alias…" className="h-[31px] w-full rounded-full border border-line bg-surface pl-9 pr-4 text-[11px] placeholder:text-ink-3" />
              </div>
              {people.isPending && <div className="space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>}
              {people.isError && <p role="alert" className="text-bad">{people.error.message}</p>}
              <ul className="max-h-[300px] overflow-y-auto pr-0.5">
                {shown.map((p, i) => {
                  const own = p.author_units + p.speaker_units
                  const on = selected?.person_id === p.person_id
                  return (
                    <li key={p.person_id} className="py-[2px]">
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => { setSelected(p); setTyped('') }}
                        className={`grid h-[54px] w-full cursor-pointer grid-cols-[14px_36px_minmax(0,1fr)_88px_80px_68px] items-center gap-x-3 rounded-lg border px-[15px] text-left transition-colors duration-200 ${on ? 'border-brand bg-brand-soft/60' : 'border-transparent hover:bg-surface-2'}`}
                      >
                        <span className={`grid size-[14px] place-items-center rounded-full border ${on ? 'border-brand bg-brand' : 'border-ink-3'}`} aria-hidden="true">
                          {on && <span className="size-[5px] rounded-full bg-white" />}
                        </span>
                        <Avatar name={p.canonical_name} tone={i} />
                        <span className="min-w-0">
                          <span className="block truncate text-[12px] font-bold text-ink">{p.canonical_name}</span>
                          <span className="block truncate text-[10.5px] text-ink-3">{(own + p.mentioned_units).toLocaleString()} units</span>
                        </span>
                        <span className="block h-2 w-[88px] overflow-hidden rounded-full bg-[#dfe8f3]" aria-hidden="true">
                          <span className="anim-bar block h-full rounded-full bg-[#4a9be0]" style={{ width: `${Math.max(4, (own / maxOwn) * 100)}%` }} />
                        </span>
                        <span className="text-center">
                          <span className="block text-[13px] font-bold tabular-nums leading-tight text-ink">{own.toLocaleString()}</span>
                          <span className="block text-[9px] leading-tight text-ink-3">authored/spoken</span>
                        </span>
                        <span className="text-center">
                          <span className="block text-[13px] font-bold tabular-nums leading-tight text-ink">{p.mentioned_units.toLocaleString()}</span>
                          <span className="block text-[9px] leading-tight text-ink-3">mentioned</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            <div className="space-y-2 self-start">
              <section className={`${card} px-[17px] pb-3 pt-[15px]`} aria-labelledby="review">
                <h2 id="review" className="text-[17px] font-bold leading-6">Review the impact</h2>
                {!selected && (
                  <>
                    <p className="mb-[6px] -mt-px text-[11px] text-ink-2">Select a person to see exactly what would change.</p>
                    <div className="grid min-h-[230px] place-items-center rounded-[10px] border border-dashed border-line p-6 text-center text-[12px] text-ink-2">
                      <p>Nothing selected yet.</p>
                    </div>
                  </>
                )}
                {selected && preview.isPending && <div role="status" className="mt-3 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
                {selected && preview.isError && <p role="alert" className="text-bad">{preview.error.message}</p>}
                {selected && preview.data && (
                  <div className="anim-fade-up">
                    <p className="mb-[6px] -mt-px text-[11px] text-ink-2">Here's what will be anonymized for {selected.canonical_name}.</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { icon: <IconFile size={18} />, n: preview.data.author_units + preview.data.speaker_units, label: 'Units they wrote or spoke', hint: 'Emails, docs, chats, meetings' },
                        { icon: <IconUsers size={18} />, n: preview.data.mentioned_units, label: 'Units that mention them', hint: 'Conversations, docs, threads' },
                        { icon: <IconFolder size={18} />, n: preview.data.files_to_sanitize, label: 'Files to sanitize', hint: 'Source files will be updated' },
                        { icon: <IconLink size={18} />, n: preview.data.cases_to_invalidate + (preview.data.findings_to_invalidate ?? 0), label: 'Dependent Cases to invalidate', hint: 'Evidence references will be removed' },
                      ].map((t) => (
                        <div key={t.label} className="flex h-[56px] items-center gap-3 rounded-lg border border-line bg-surface px-[13px]">
                          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">{t.icon}</span>
                          <span className="min-w-0 leading-tight">
                            <span className="block text-[15px] font-bold tabular-nums text-ink">{t.n.toLocaleString()}</span>
                            <span className="block truncate text-[10px] text-ink-2">{t.label}</span>
                            <span className="block truncate text-[9px] text-ink-3">{t.hint}</span>
                          </span>
                        </div>
                      ))}
                    </div>

                    <div className="mt-[12px] rounded-lg border border-[#f3c9c6] bg-bad-soft px-[13px] py-[10px]">
                      <p className="flex items-center gap-2 text-[11px] font-bold text-bad"><IconAlert size={15} /> What will happen</p>
                      <p className="mt-1 pl-[23px] text-[9.5px] leading-[13px] text-ink">
                        We will anonymize this person in source files, rebuild the search index and embeddings, purge
                        derived data, and verify that they no longer appear in any product surfaces. Unrelated evidence
                        will be preserved.
                      </p>
                    </div>

                    <div className="mt-[7px]">
                      <label htmlFor="confirm" className="mb-0.5 block text-[10.5px] font-bold leading-[14px] text-ink">
                        Type the full name to confirm
                      </label>
                      <div className="flex items-center gap-[11px]">
                        <input
                          id="confirm"
                          value={typed}
                          onChange={(e) => setTyped(e.target.value)}
                          autoComplete="off"
                          placeholder={selected.canonical_name}
                          className="h-8 w-full min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-[11px] placeholder:text-ink-3"
                        />
                        <button type="button" className="inline-flex h-[33px] w-[135px] shrink-0 cursor-pointer items-center justify-center rounded-full bg-bad text-[11px] font-bold text-white transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed" disabled={!confirmed} onClick={() => { setStage(0); purge.mutate(selected) }}>
                          Remove this person
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </section>

              <section className={`${card} px-[17px] pb-4 pt-[12px]`} aria-labelledby="verified">
                <h2 id="verified" className="text-[15px] font-bold leading-[18px]">What gets verified</h2>
                <p className="mb-[10px] text-[10px] leading-[14px] text-ink-2">We check these surfaces for the person's tracked identifiers. This is not cryptographic erasure.</p>
                <ul className="grid grid-cols-2 gap-x-3 gap-y-2 sm:flex sm:justify-between sm:gap-x-2.5">
                  {VERIFIED_SURFACES.map((v) => (
                    <li key={v.title} className="flex min-w-0 items-start gap-1.5 sm:shrink-0">
                      <span className="mt-px grid size-4 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
                        <IconCheck size={10} strokeWidth={3.5} />
                      </span>
                      <span className="leading-[12px]">
                        <span className="block whitespace-nowrap text-[8.5px] font-bold text-ink">{v.title}</span>
                        <span className="block max-w-[88px] truncate text-[8px] leading-[11px] text-ink-3" title={v.body}>{v.body}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
