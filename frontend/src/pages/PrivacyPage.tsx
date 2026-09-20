import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconEye,
  IconFile,
  IconFlag,
  IconFolder,
  IconLink,
  IconLock,
  IconSearch,
  IconShield,
  IconUsers,
} from '../components/icons'
import { Skeleton, Spinner, Tick } from '../components/ui'
import { go } from '../hooks/useRoute'
import { btnPrimary, btnSecondary, card } from '../lib'
import type { PersonSummary, PseudonymiseResult } from '../types/api'

const SURFACES: Record<string, string> = {
  source_files: 'Canonical source files',
  database_rows: 'Database rows and search index',
  database_files: 'Database file, WAL and journal',
  artifacts_and_cache: 'Artifacts and cache',
  vault_directory_plaintext: 'Vault directory (ciphertext only)',
}

const CHECKS: Record<string, string> = {
  subject_is_pseudonymised: 'Subject is marked PSEUDONYMISED',
  display_alias_matches: 'Display alias is stable',
  display_name_cleared: 'Original name cleared from the public row',
  no_original_aliases_remain: 'Original aliases removed',
  evidence_people_relationships_preserved: 'Every relationship preserved',
}

const STAGES = [
  'Locking the archive',
  'Rewriting the canonical source to the alias',
  'Rebuilding from the alias-bearing source',
  'Refreshing embeddings and derived data',
  'Verifying every surface',
]

const STEPS = [
  { label: 'Choose', hint: 'Find and select a participant' },
  { label: 'Review', hint: 'See what will be affected' },
  { label: 'Authorize', hint: 'Confirm with the admin token' },
  { label: 'Verified', hint: 'Pseudonymisation completed' },
]

const VERIFIED_SURFACES = [
  { icon: <IconFile size={18} />, title: 'Canonical source files', body: 'Documents, emails, chats' },
  { icon: <IconLock size={18} />, title: 'Database rows and search index', body: 'Structured data and index' },
  { icon: <IconFolder size={18} />, title: 'Artifacts and cache', body: 'Embeddings, summaries, exports' },
  { icon: <IconUsers size={18} />, title: 'Relationships and history', body: 'Preserved under the new alias' },
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

function Result({ result, questions }: { result: PseudonymiseResult; questions: string[] }) {
  return (
    <div className="anim-fade-up mx-auto max-w-2xl space-y-6">
      <div className={`${card} space-y-5 overflow-hidden`}>
        <div className={`flex items-center gap-4 p-6 ${result.verified ? 'bg-ok-soft' : 'bg-bad-soft'}`}>
          <span className={`grid size-14 place-items-center rounded-2xl text-white ${result.verified ? 'bg-ok' : 'bg-bad'}`}>
            {result.verified ? <IconShield size={28} /> : <IconAlert size={28} />}
          </span>
          <div>
            <h2 className="text-2xl font-extrabold">{result.verified ? 'Pseudonymisation verified' : 'Could not be verified'}</h2>
            <p className="text-sm font-semibold text-ink-2">
              Now known as <span className="font-mono">{result.display_alias}</span>. Every surface below was scanned for the original identifiers.
            </p>
          </div>
        </div>
        <div className="grid gap-3 px-6 sm:grid-cols-2">
          {[
            [result.files_rewritten, 'source files rewritten'],
            [result.units_rewritten, 'evidence units rewritten'],
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
          <caption className="px-6 pb-2 text-left text-xs font-extrabold uppercase tracking-wide text-ink-3">Original identifiers found, per surface</caption>
          <tbody>
            {Object.entries(result.verification).map(([key, count]) => (
              <tr key={key} className="border-t border-line">
                <th scope="row" className="px-6 py-2.5 text-left font-semibold">{SURFACES[key] ?? key}</th>
                <td className={`px-6 py-2.5 text-right font-extrabold ${count === 0 ? 'text-ok' : 'text-bad'}`}>{count === 0 ? '0 · clean' : count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="w-full text-sm">
          <caption className="px-6 pb-2 text-left text-xs font-extrabold uppercase tracking-wide text-ink-3">Preservation checks</caption>
          <tbody>
            {Object.entries(result.checks).map(([key, passed]) => (
              <tr key={key} className="border-t border-line">
                <th scope="row" className="px-6 py-2.5 text-left font-semibold">{CHECKS[key] ?? key}</th>
                <td className={`px-6 py-2.5 text-right font-extrabold ${passed ? 'text-ok' : 'text-bad'}`}>{passed ? 'Pass' : 'Fail'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-line bg-surface-2 px-6 py-4 text-xs text-ink-2">
          This is an application-level check of the identifiers the system tracks (names, reviewed aliases, emails) across storage it owns. The record remains personal data: it is pseudonymised, not irreversibly anonymized, and the original identity is retained only in a separately encrypted vault, recoverable only through the authenticated admin reversal workflow.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" className={btnPrimary} onClick={() => go.person(result.subject_id)}>
          View profile <IconArrowRight size={16} />
        </button>
        <button type="button" className={btnSecondary} onClick={() => go.ask()}>
          Ask a question again
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
  const [adminToken, setAdminToken] = useState('')
  const [stage, setStage] = useState(0)
  const [reask, setReask] = useState<string[]>([])

  const preview = useQuery({
    queryKey: ['preview', selected?.subject_id],
    queryFn: () => api.preview(selected!.subject_id),
    enabled: selected !== null,
  })

  const pseudonymise = useMutation({
    mutationFn: async (person: PersonSummary) => {
      // Capture recent questions first: pseudonymising invalidates Cases that mention the person.
      const recent = await api.recentCases().catch(() => [])
      const name = person.display_name ?? ''
      const parts = name.toLowerCase().split(/\s+/).filter((p) => p.length >= 3)
      const safe = recent.map((c) => c.query).filter((q) => !parts.some((p) => q.toLowerCase().includes(p)))
      const result = await api.pseudonymise(person.subject_id, adminToken)
      return { result, safe }
    },
    onSuccess: ({ safe }) => {
      setReask(safe)
      client.clear()
      setSelected(null)
    },
  })

  useEffect(() => {
    if (!pseudonymise.isPending) return
    const timer = window.setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1500)
    return () => window.clearInterval(timer)
  }, [pseudonymise.isPending])

  const shown = useMemo(
    () =>
      (people.data ?? []).filter((p) =>
        (p.display_name ?? p.display_alias).toLowerCase().includes(filter.toLowerCase())
      ),
    [people.data, filter]
  )
  const step = pseudonymise.data ? 3 : selected && preview.data ? (adminToken ? 2 : 1) : 0
  const maxOwn = Math.max(1, ...(people.data ?? []).map((p) => p.author_units + p.speaker_units))

  return (
    <div>
      <section className="hero-bg">
        <div className="mx-auto max-w-4xl space-y-4 px-4 pb-10 pt-12 text-center">
          <span className="inline-flex items-center gap-2 rounded-full bg-surface/80 px-4 py-1.5 text-xs font-extrabold uppercase tracking-[0.14em] text-ink-3 shadow-card">
            Privacy console
          </span>
          <h1 className="text-balance text-4xl font-extrabold tracking-tight text-ink sm:text-5xl">Pseudonymise a person. Prove it held.</h1>
          <p className="mx-auto max-w-2xl text-lg text-ink-2">
            Replace one participant's identity everywhere in the archive with a stable alias, while
            preserving their complete history and relationships. Reversible only through an
            authenticated admin workflow.
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
        {pseudonymise.isPending && <Working stage={stage} />}
        {pseudonymise.isError && (
          <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl border border-bad/40 bg-bad-soft p-4 text-bad">
            <IconAlert size={20} className="mt-0.5 shrink-0" />
            <p className="font-semibold">{pseudonymise.error.message} The system stays locked for review; nothing was reported as pseudonymised.</p>
          </div>
        )}
        {pseudonymise.data && <Result result={pseudonymise.data.result} questions={reask} />}

        {!pseudonymise.isPending && !pseudonymise.data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <section className={`${card} p-5`} aria-labelledby="choose">
              <h2 id="choose" className="text-lg font-extrabold">Choose a participant</h2>
              <p className="mb-3 text-sm text-ink-2">Search for a participant to see their impact across your organization's memory.</p>
              <label htmlFor="filter" className="sr-only">Filter people</label>
              <div className="relative mb-3">
                <IconSearch size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" />
                <input id="filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search by name or alias…" className="min-h-12 w-full rounded-full border border-line bg-surface-2 pl-11 pr-4 font-semibold" />
              </div>
              {people.isPending && <div className="space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>}
              {people.isError && <p role="alert" className="text-bad">{people.error.message}</p>}
              <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto pr-1">
                {shown.map((p, i) => {
                  const own = p.author_units + p.speaker_units
                  const on = selected?.subject_id === p.subject_id
                  const label = p.display_name ?? p.display_alias
                  return (
                    <li key={p.subject_id}>
                      <div
                        className={`flex w-full items-center gap-3 rounded-2xl border p-3 text-left transition-all duration-200 ${on ? 'border-brand bg-brand-soft shadow-card' : 'border-transparent hover:border-line hover:bg-surface-2'}`}
                      >
                        <button
                          type="button"
                          aria-pressed={on}
                          onClick={() => setSelected(p)}
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
                        >
                          <span className={`grid size-4 shrink-0 place-items-center rounded-full border-2 ${on ? 'border-brand' : 'border-line'}`} aria-hidden="true">
                            {on && <span className="size-2 rounded-full bg-brand" />}
                          </span>
                          <Avatar name={label} tone={i} />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-1.5">
                              <span className="block truncate font-bold">{label}</span>
                              {p.privacy_state === 'PSEUDONYMISED' && (
                                <span className="shrink-0 rounded-full bg-warn-soft px-1.5 py-0.5 text-[10px] font-extrabold uppercase text-warn">Pseudonymised</span>
                              )}
                            </span>
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
                        <button
                          type="button"
                          title="View full profile"
                          aria-label={`View ${label}'s profile`}
                          onClick={() => go.person(p.subject_id)}
                          className="shrink-0 rounded-full p-2 text-ink-3 transition-colors duration-200 hover:bg-surface hover:text-brand-ink"
                        >
                          <IconEye size={18} />
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>

            <section className={`${card} p-5`} aria-labelledby="review">
              <h2 id="review" className="text-lg font-extrabold">Review the impact</h2>
              {!selected && (
                <>
                  <p className="mb-3 text-sm text-ink-2">Select a participant to see exactly what would change.</p>
                  <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-line p-6 text-center text-ink-2">
                    <p>Nothing selected yet.</p>
                  </div>
                </>
              )}
              {selected && selected.privacy_state === 'PSEUDONYMISED' && (
                <div className="space-y-3 rounded-2xl border border-warn/40 bg-warn-soft p-4 text-sm text-ink">
                  <p className="font-bold">Already pseudonymised.</p>
                  <p>This participant is already known only as {selected.display_alias}.</p>
                  <button type="button" className={btnSecondary} onClick={() => go.person(selected.subject_id)}>
                    View profile
                  </button>
                </div>
              )}
              {selected && selected.privacy_state === 'ACTIVE' && preview.isPending && <div role="status" className="mt-3 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
              {selected && selected.privacy_state === 'ACTIVE' && preview.isError && <p role="alert" className="text-bad">{preview.error.message}</p>}
              {selected && selected.privacy_state === 'ACTIVE' && preview.data && (
                <div className="anim-fade-up space-y-5">
                  <p className="mb-1 text-sm text-ink-2">
                    Here's what will be rewritten for {selected.display_name}, replaced everywhere by the alias{' '}
                    <span className="font-mono">{preview.data.display_alias}</span>.
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { icon: <IconFile size={18} />, n: preview.data.author_units + preview.data.speaker_units, label: 'Units they wrote or spoke', hint: 'Emails, docs, chats, meetings' },
                      { icon: <IconUsers size={18} />, n: preview.data.mentioned_units, label: 'Units that mention them', hint: 'Conversations, docs, threads' },
                      { icon: <IconFolder size={18} />, n: preview.data.files_to_rewrite, label: 'Files to rewrite', hint: 'Source files will be updated' },
                      { icon: <IconLink size={18} />, n: preview.data.cases_to_invalidate + (preview.data.findings_to_invalidate ?? 0), label: 'Dependent Cases to invalidate', hint: 'Recomputed from alias-bearing evidence' },
                    ].map((s) => (
                      <div key={s.label} className="rounded-xl bg-surface-2 p-3">
                        <span className="mb-2 grid size-8 place-items-center rounded-lg bg-brand-soft text-brand-ink">{s.icon}</span>
                        <p className="text-2xl font-extrabold tabular-nums leading-tight">{s.n}</p>
                        <p className="text-xs font-bold text-ink">{s.label}</p>
                        <p className="text-xs text-ink-3">{s.hint}</p>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 rounded-2xl border border-brand/30 bg-brand-soft p-4">
                    <p className="flex items-center gap-2 font-extrabold text-brand-ink"><IconShield size={18} /> What will happen</p>
                    <p className="text-sm text-ink">
                      We will rewrite this person's identity to their stable alias in source files, rebuild the
                      search index and embeddings, invalidate dependent Cases, and verify the original identity
                      is absent from every public surface. Their complete history, evidence, and relationships
                      are preserved and remain fully inspectable under the alias.
                    </p>
                  </div>

                  <div>
                    <label htmlFor="admin-token" className="mb-1.5 block text-sm font-bold text-ink">
                      Admin token
                    </label>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        id="admin-token"
                        type="password"
                        value={adminToken}
                        onChange={(e) => setAdminToken(e.target.value)}
                        autoComplete="off"
                        placeholder="Required to authorize this action"
                        className="min-h-12 w-full min-w-0 flex-1 rounded-full border border-line bg-surface px-5 font-semibold"
                      />
                      <button type="button" className={`${btnPrimary} shrink-0`} disabled={!adminToken} onClick={() => { setStage(0); pseudonymise.mutate(selected) }}>
                        <IconShield size={18} /> Pseudonymise
                      </button>
                    </div>
                    <p className="mt-1.5 text-xs text-ink-3">Never stored; used only for this request's Authorization header.</p>
                  </div>

                  <div className="border-t border-line pt-4">
                    <h3 className="mb-3 flex items-center gap-2 text-sm font-extrabold text-ink">
                      <IconShield size={16} className="text-brand-ink" /> What gets verified
                    </h3>
                    <p className="mb-3 text-xs text-ink-2">We check these surfaces to make sure the original identity is fully replaced.</p>
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
