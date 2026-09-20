import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconEye,
  IconFile,
  IconFolder,
  IconLink,
  IconLock,
  IconSearch,
  IconShield,
  IconUsers,
} from '../components/icons'
import { EuFlag } from '../components/Logo'
import { Skeleton, Spinner, Tick } from '../components/ui'
import { go } from '../hooks/useRoute'
import { btnPrimary, btnSecondary, card } from '../lib'
import type { PersonSummary, PseudonymisePreview, PseudonymiseResult, ReversalResult } from '../types/api'

const SURFACES: Record<string, string> = {
  source_files: 'Canonical source files',
  database_rows: 'Database rows and search index',
  database_files: 'Database file, WAL and journal',
  artifacts_and_cache: 'Artifacts and cache',
  vault_directory_plaintext: 'Vault directory (ciphertext only)',
  source_filenames: 'Source file names',
  artifact_filenames: 'Artifact file names',
  database_content: 'Database content',
}

const CHECKS: Record<string, string> = {
  subject_is_pseudonymised: 'Subject is marked PSEUDONYMISED',
  display_alias_matches: 'Display alias is stable',
  display_name_cleared: 'Original name cleared from the public row',
  no_original_aliases_remain: 'Original aliases removed',
  evidence_people_relationships_preserved: 'Every relationship preserved',
}

const PSEUDONYMISE_STAGES = [
  'Locking the archive',
  'Rewriting the canonical source to the alias',
  'Rebuilding from the alias-bearing source',
  'Refreshing embeddings and derived data',
  'Verifying every surface',
]

const REVERSE_STAGES = [
  'Locking the archive',
  'Decrypting the identity from the vault',
  'Restoring the original identity in the source',
  'Refreshing embeddings and derived data',
  'Verifying every surface',
]

const STEPS = [
  { label: 'Choose', hint: 'Find and select a participant' },
  { label: 'Review', hint: 'See what will be affected' },
  { label: 'Authorize', hint: 'Confirm with the admin token' },
  { label: 'Verified', hint: 'Operation completed' },
]

const VERIFIED_SURFACES = [
  { title: 'Canonical source files', body: 'Documents, emails, chats' },
  { title: 'Database rows and search index', body: 'Structured data and index' },
  { title: 'Artifacts and cache', body: 'Embeddings, summaries, exports' },
  { title: 'Relationships and history', body: 'Preserved under the alias' },
]

// Why a first name was deliberately left out of the rewrite (app/ingestion/name_resolution.py).
const UNASSIGNED_REASON: Record<string, string> = {
  shared: 'another participant has the same name, so a bare mention could be either of them',
  'ordinary-word': 'it is also an ordinary word in the archive, so a bare mention may not be a name',
  'too-short': 'it is too short to assign safely',
  reserved: 'it is a reserved label',
}

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

function Avatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-[12px] font-semibold text-brand-ink">
      {initials}
    </span>
  )
}

function Working({ stages, stage, title }: { stages: string[]; stage: number; title: string }) {
  return (
    <div className={`${card} mx-auto max-w-xl space-y-5 p-8 text-center`} role="status" aria-live="polite">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-warn-soft text-warn">
        <IconLock size={28} />
      </span>
      <div>
        <h2 className="shimmer-text text-2xl font-extrabold">{stages[stage]}…</h2>
        <p className="mt-1 text-sm text-ink-2">
          {title} The archive is locked and cannot answer questions until this finishes.
        </p>
      </div>
      <ol className="mx-auto grid max-w-sm gap-2 text-left">
        {stages.map((s, i) => (
          <li
            key={s}
            className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold ${i === stage ? 'bg-brand-soft text-ink' : i < stage ? 'text-ink-2' : 'text-ink-3'}`}
          >
            <span className="grid size-5 place-items-center">
              {i < stage ? <Tick size={20} /> : i === stage ? <Spinner size={18} /> : <span className="size-2 rounded-full bg-line" />}
            </span>
            {s}
          </li>
        ))}
      </ol>
    </div>
  )
}

function CountTiles({ tiles }: { tiles: [string | number, string][] }) {
  return (
    <div className="grid gap-3 px-6 sm:grid-cols-2">
      {tiles.map(([n, label]) => (
        <div key={String(label)} className="rounded-lg bg-surface-2 p-3">
          <p className="text-2xl font-extrabold tabular-nums">{n}</p>
          <p className="text-xs font-bold text-ink-2">{label}</p>
        </div>
      ))}
    </div>
  )
}

function ResultTable({ caption, rows, kind }: { caption: string; rows: [string, string, boolean][]; kind: 'count' | 'check' }) {
  if (rows.length === 0) return null
  return (
    <table className="w-full text-sm">
      <caption className="px-6 pb-2 text-left text-xs font-extrabold uppercase tracking-wide text-ink-3">{caption}</caption>
      <tbody>
        {rows.map(([key, label, ok]) => (
          <tr key={key} className="border-t border-line">
            <th scope="row" className="px-6 py-2.5 text-left font-semibold">
              {label}
            </th>
            <td className={`px-6 py-2.5 text-right font-extrabold ${ok ? 'text-ok' : 'text-bad'}`}>
              {kind === 'check' ? (ok ? 'Pass' : 'Fail') : ok ? '0 · clean' : label}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const humanize = (key: string) => {
  const text = key.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

const countRows = (verification: Record<string, number>): [string, string, boolean][] =>
  Object.entries(verification).map(([key, count]) => [key, count === 0 ? (SURFACES[key] ?? key) : `${SURFACES[key] ?? key}: ${count}`, count === 0])

function Result({
  kind,
  result,
  questions,
  onBack,
}: {
  kind: 'pseudonymise' | 'reverse'
  result: PseudonymiseResult | ReversalResult
  questions: string[]
  onBack: () => void
}) {
  const reversal = kind === 'reverse'
  const done = result as PseudonymiseResult & ReversalResult
  // The hard gate (every surface clean, identity state correct) is separate from embedding
  // regeneration, which is deliberately non-blocking: with no embedding service reachable the
  // operation is complete and verified but semantic search stays degraded until it catches up.
  const pending = done.embeddings_pending ?? 0
  const checkEntries = Object.entries(done.checks ?? {})
  const surfacesVerified =
    Object.values(result.verification).every((n) => n === 0) &&
    checkEntries.filter(([k]) => !k.includes('embedding')).every(([, ok]) => ok)
  const outcome: 'verified' | 'pending' | 'failed' = result.verified
    ? 'verified'
    : surfacesVerified && pending > 0
      ? 'pending'
      : 'failed'
  const tiles: [string | number, string][] = reversal
    ? [
        [done.files_restored, 'source files restored'],
        [
          done.embeddings_regenerated ?? 0,
          `embeddings regenerated${done.embeddings_pending ? `, ${done.embeddings_pending} pending` : ''}`,
        ],
      ]
    : [
        [done.files_rewritten, 'source files rewritten'],
        [done.units_rewritten, 'evidence units rewritten'],
        [done.cases_invalidated + (done.findings_invalidated ?? 0), 'dependent Cases and findings invalidated'],
        [
          done.embeddings_regenerated,
          `embeddings regenerated${done.embeddings_pending ? `, ${done.embeddings_pending} pending` : ''}`,
        ],
      ]
  return (
    <div className="anim-fade-up mx-auto max-w-2xl space-y-6">
      <div className={`${card} space-y-5 overflow-hidden pb-0`}>
        <div
          className={`flex items-center gap-4 p-6 ${outcome === 'verified' ? 'bg-ok-soft' : outcome === 'pending' ? 'bg-warn-soft' : 'bg-bad-soft'}`}
        >
          <span
            className={`grid size-14 place-items-center rounded-2xl text-white ${outcome === 'verified' ? 'bg-ok' : outcome === 'pending' ? 'bg-warn' : 'bg-bad'}`}
          >
            {outcome === 'verified' ? <IconShield size={28} /> : <IconAlert size={28} />}
          </span>
          <div>
            <h2 className="text-2xl font-extrabold">
              {outcome === 'verified'
                ? reversal
                  ? 'Reversal verified'
                  : 'Pseudonymisation verified'
                : outcome === 'pending'
                  ? reversal
                    ? 'Reversal complete: embeddings pending'
                    : 'Pseudonymisation complete: embeddings pending'
                  : 'Could not be verified'}
            </h2>
            <p className="text-sm font-semibold text-ink-2">
              {reversal ? (
                <>
                  The participant known as <span className="font-mono">{result.display_alias}</span> is attributable again. Every
                  surface below was scanned.
                </>
              ) : (
                <>
                  Now known as <span className="font-mono">{result.display_alias}</span>. Every surface below was scanned for the
                  original identifiers.
                </>
              )}
            </p>
          </div>
        </div>
        <CountTiles tiles={tiles} />
        <ResultTable
          caption={reversal ? 'Surfaces checked' : 'Original identifiers found, per surface'}
          rows={countRows(result.verification)}
          kind="count"
        />
        <ResultTable
          caption={reversal ? 'Restoration checks' : 'Preservation checks'}
          rows={checkEntries.map(([k, v]) => [k, CHECKS[k] ?? humanize(k), v])}
          kind="check"
        />
        {outcome === 'pending' && (
          <p role="status" className="mx-6 rounded-lg bg-warn-soft px-4 py-3 text-xs text-ink">
            Every surface is verified. {pending.toLocaleString()} embeddings could not be regenerated because no embedding service was
            reachable, so semantic search is degraded until they are. Keyword search and the archive itself are unaffected.
          </p>
        )}
        <p className="border-t border-line bg-surface-2 px-6 py-4 text-xs text-ink-2">
          {reversal
            ? 'Reversal restores the vault’s canonical name at every position; it cannot know which short form stood where. The alias stays assigned to this participant.'
            : 'This is an application-level check of the identifiers the system tracks (names, reviewed aliases, the safe first name, emails) across storage it owns. The record remains personal data: it is pseudonymised, not irreversibly anonymized, and the original identity is retained only in a separately encrypted vault, recoverable only through the authenticated admin reversal workflow.'}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" className={btnPrimary} onClick={() => go.person(result.subject_id)}>
          View profile <IconArrowRight size={16} />
        </button>
        <button type="button" className={btnSecondary} onClick={onBack}>
          Back to the console
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

function FirstNameNote({ preview }: { preview: PseudonymisePreview }) {
  if (preview.first_name) {
    return (
      <p className="mt-[8px] flex gap-2 rounded-lg bg-brand-soft px-[13px] py-[8px] text-[10px] leading-[14px] text-ink">
        <IconCheck size={13} strokeWidth={3} className="mt-px shrink-0 text-brand-ink" />
        <span>
          The bare first name <strong>“{preview.first_name}”</strong> belongs to this participant alone, so it is rewritten with
          the full name.
        </span>
      </p>
    )
  }
  if (preview.unassigned_first_name) {
    return (
      <p className="mt-[8px] flex gap-2 rounded-lg bg-warn-soft px-[13px] py-[8px] text-[10px] leading-[14px] text-ink">
        <IconAlert size={13} className="mt-px shrink-0 text-warn" />
        <span>
          The bare first name <strong>“{preview.unassigned_first_name}”</strong> is left unchanged:{' '}
          {UNASSIGNED_REASON[preview.unassigned_reason ?? ''] ?? 'it could not be assigned safely'}. Only full-name references are
          rewritten.
        </span>
      </p>
    )
  }
  return null
}

export function PrivacyPage() {
  const client = useQueryClient()
  const people = useQuery({ queryKey: ['people'], queryFn: api.people })
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<PersonSummary | null>(null)
  const [adminToken, setAdminToken] = useState('')
  const [confirmReversal, setConfirmReversal] = useState(false)
  const [stage, setStage] = useState(0)
  const [reask, setReask] = useState<string[]>([])

  const active = selected?.privacy_state === 'ACTIVE'
  const preview = useQuery({
    queryKey: ['preview', selected?.subject_id],
    queryFn: () => api.preview(selected!.subject_id),
    enabled: selected !== null && active,
  })

  const pseudonymise = useMutation({
    mutationFn: async (person: PersonSummary) => {
      // Capture recent questions first: pseudonymising invalidates Cases that mention the person.
      const recent = await api.recentCases().catch(() => [])
      const parts = (person.display_name ?? '').toLowerCase().split(/\s+/).filter((p) => p.length >= 3)
      const safe = recent.map((c) => c.query).filter((q) => !parts.some((p) => q.toLowerCase().includes(p)))
      const result = await api.pseudonymise(person.subject_id, adminToken)
      return { result, safe }
    },
    onSuccess: ({ safe }) => {
      setReask(safe)
      setAdminToken('')
      client.clear()
      setSelected(null)
    },
  })

  const reverse = useMutation({
    mutationFn: (person: PersonSummary) => api.reversePseudonymisation(person.subject_id, adminToken, confirmReversal),
    onSuccess: () => {
      setAdminToken('')
      setConfirmReversal(false)
      client.clear()
      setSelected(null)
    },
  })

  const busy = pseudonymise.isPending || reverse.isPending
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => setStage((s) => Math.min(s + 1, PSEUDONYMISE_STAGES.length - 1)), 1500)
    return () => window.clearInterval(timer)
  }, [busy])

  const back = () => {
    pseudonymise.reset()
    reverse.reset()
    setStage(0)
  }
  const choose = (person: PersonSummary) => {
    setSelected(person)
    setAdminToken('')
    setConfirmReversal(false)
    pseudonymise.reset()
    reverse.reset()
  }

  const shown = useMemo(
    () =>
      (people.data ?? []).filter((p) => (p.display_name ?? p.display_alias).toLowerCase().includes(filter.toLowerCase())),
    [people.data, filter]
  )
  const done = pseudonymise.data ?? reverse.data
  const step = done ? 3 : selected && (active ? preview.data : true) ? (adminToken ? 2 : 1) : 0
  const maxOwn = Math.max(1, ...(people.data ?? []).map((p) => p.author_units + p.speaker_units))
  const showConsole = !busy && !done
  const error = pseudonymise.error ?? reverse.error

  return (
    <div>
      <section className="hero-bg">
        <div className="mx-auto max-w-[900px] px-4 pb-[22px] pt-[14px] text-center">
          <p className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-ink-3">Privacy console</p>
          <h1 className="mt-[2px] text-balance text-[30px] font-bold leading-9 tracking-tight text-ink">
            Pseudonymise a person. Prove it held.
          </h1>
          <p className="mx-auto mt-[3px] max-w-[560px] text-[13.5px] leading-[19px] text-ink-2">
            Replace one participant’s identity everywhere with a stable alias, keeping their full history and relationships.
            Reversible only through an authenticated admin workflow.
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
        {pseudonymise.isPending && (
          <Working stages={PSEUDONYMISE_STAGES} stage={stage} title="Pseudonymising this participant." />
        )}
        {reverse.isPending && <Working stages={REVERSE_STAGES} stage={stage} title="Reversing this pseudonymisation." />}
        {error && !busy && (
          <div role="alert" className="mb-6 flex items-start gap-3 rounded-xl border border-bad/40 bg-bad-soft p-4 text-bad">
            <IconAlert size={20} className="mt-0.5 shrink-0" />
            <p className="font-semibold">
              {error.message}{' '}
              {error.message.toLowerCase().includes('admin')
                ? 'Nothing was changed.'
                : 'If the archive reports it is locked for review, nothing was reported as complete.'}
            </p>
          </div>
        )}
        {pseudonymise.data && <Result kind="pseudonymise" result={pseudonymise.data.result} questions={reask} onBack={back} />}
        {reverse.data && <Result kind="reverse" result={reverse.data} questions={[]} onBack={back} />}

        {showConsole && (
          <div className="grid gap-[15px] lg:grid-cols-2">
            <section className={`${card} px-[17px] pb-[14px] pt-[15px]`} aria-labelledby="choose">
              <h2 id="choose" className="text-[17px] font-bold leading-6">
                Choose a participant
              </h2>
              <p className="-mt-px mb-[13px] text-[11px] text-ink-2">
                Search for a participant to see their impact across your organization’s memory.
              </p>
              <label htmlFor="filter" className="sr-only">
                Filter people
              </label>
              <div className="relative mb-[17px]">
                <IconSearch size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-2" />
                <input
                  id="filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Search by name or alias…"
                  className="h-[31px] w-full rounded-full border border-line bg-surface pl-9 pr-4 text-[11px] placeholder:text-ink-3"
                />
              </div>
              {people.isPending && (
                <div className="space-y-2">
                  <Skeleton className="h-14" />
                  <Skeleton className="h-14" />
                  <Skeleton className="h-14" />
                </div>
              )}
              {people.isError && (
                <p role="alert" className="text-bad">
                  {people.error.message}
                </p>
              )}
              <ul className="max-h-[300px] overflow-y-auto pr-0.5">
                {shown.map((p) => {
                  const own = p.author_units + p.speaker_units
                  const on = selected?.subject_id === p.subject_id
                  const label = p.display_name ?? p.display_alias
                  return (
                    <li key={p.subject_id} className="flex items-center gap-1 py-[2px]">
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => choose(p)}
                        className={`grid h-[54px] min-w-0 flex-1 cursor-pointer grid-cols-[14px_36px_minmax(0,1fr)_88px_80px_68px] items-center gap-x-3 rounded-lg border px-[15px] text-left transition-colors duration-200 ${on ? 'border-brand bg-brand-soft/60' : 'border-transparent hover:bg-surface-2'}`}
                      >
                        <span
                          className={`grid size-[14px] place-items-center rounded-full border ${on ? 'border-brand bg-brand' : 'border-ink-3'}`}
                          aria-hidden="true"
                        >
                          {on && <span className="size-[5px] rounded-full bg-white" />}
                        </span>
                        <Avatar name={label} />
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5">
                            <span className={`block truncate text-[12px] font-bold text-ink ${p.display_name ? '' : 'font-mono'}`}>{label}</span>
                            {p.privacy_state === 'PSEUDONYMISED' && (
                              <span className="shrink-0 rounded-full bg-warn-soft px-1.5 py-0.5 text-[8px] font-extrabold uppercase text-warn">
                                Pseudonymised
                              </span>
                            )}
                          </span>
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
                      <button
                        type="button"
                        title="View full profile"
                        aria-label={`View ${label}’s profile`}
                        onClick={() => go.person(p.subject_id)}
                        className="grid size-8 shrink-0 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-brand-ink"
                      >
                        <IconEye size={16} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            <div className="space-y-2 self-start">
              <section className={`${card} px-[17px] pb-3 pt-[15px]`} aria-labelledby="review">
                <h2 id="review" className="text-[17px] font-bold leading-6">
                  {selected?.privacy_state === 'PSEUDONYMISED' ? 'Reverse pseudonymisation' : 'Review the impact'}
                </h2>

                {!selected && (
                  <>
                    <p className="-mt-px mb-[6px] text-[11px] text-ink-2">Select a participant to see exactly what would change.</p>
                    <div className="grid min-h-[230px] place-items-center rounded-[10px] border border-dashed border-line p-6 text-center text-[12px] text-ink-2">
                      <p>Nothing selected yet.</p>
                    </div>
                  </>
                )}

                {selected?.privacy_state === 'PSEUDONYMISED' && (
                  <div className="anim-fade-up">
                    <p className="-mt-px mb-[6px] text-[11px] text-ink-2">
                      This participant is known only as <span className="font-mono">{selected.display_alias}</span>. Their original
                      identity is held in the encrypted vault.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { icon: <IconFile size={18} />, n: selected.author_units + selected.speaker_units, label: 'Units they wrote or spoke', hint: 'History preserved under the alias' },
                        { icon: <IconUsers size={18} />, n: selected.mentioned_units, label: 'Units that mention them', hint: 'Relationships preserved' },
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

                    <div className="mt-[12px] rounded-lg border border-[#f4d9b0] bg-warn-soft px-[13px] py-[10px]">
                      <p className="flex items-center gap-2 text-[11px] font-bold text-warn">
                        <IconAlert size={15} /> What reversal does
                      </p>
                      <p className="mt-1 pl-[23px] text-[9.5px] leading-[13px] text-ink">
                        Decrypts this participant’s original identity from the vault and restores it in the source, search index and
                        embeddings, then verifies every surface. It is an admin-only workflow: the identity is never available to
                        ordinary profile, search or evidence views.
                      </p>
                    </div>

                    <label className="mt-[9px] flex cursor-pointer items-start gap-2 text-[10.5px] leading-[14px] text-ink">
                      <input
                        type="checkbox"
                        checked={confirmReversal}
                        onChange={(e) => setConfirmReversal(e.target.checked)}
                        className="mt-0.5 size-3.5 accent-[var(--brand)]"
                      />
                      I understand this makes the participant’s original identity visible again everywhere.
                    </label>

                    <div className="mt-[7px]">
                      <label htmlFor="admin-token" className="mb-0.5 block text-[10.5px] font-bold leading-[14px] text-ink">
                        Admin token
                      </label>
                      <div className="flex items-center gap-[11px]">
                        <input
                          id="admin-token"
                          type="password"
                          value={adminToken}
                          onChange={(e) => setAdminToken(e.target.value)}
                          autoComplete="off"
                          placeholder="Required to authorize this action"
                          className="h-8 w-full min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-[11px] placeholder:text-ink-3"
                        />
                        <button
                          type="button"
                          className="inline-flex h-[33px] w-[135px] shrink-0 cursor-pointer items-center justify-center rounded-full bg-warn text-[11px] font-bold text-white transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={!adminToken || !confirmReversal}
                          onClick={() => {
                            setStage(0)
                            reverse.mutate(selected)
                          }}
                        >
                          Reverse
                        </button>
                      </div>
                      <p className="mt-1 text-[9px] text-ink-3">Never stored; used only for this request’s Authorization header.</p>
                    </div>
                  </div>
                )}

                {selected?.privacy_state === 'ACTIVE' && preview.isPending && (
                  <div role="status" className="mt-3 space-y-3">
                    <Skeleton className="h-24" />
                    <Skeleton className="h-24" />
                  </div>
                )}
                {selected?.privacy_state === 'ACTIVE' && preview.isError && (
                  <p role="alert" className="text-bad">
                    {preview.error.message}
                  </p>
                )}
                {selected?.privacy_state === 'ACTIVE' && preview.data && (
                  <div className="anim-fade-up">
                    <p className="-mt-px mb-[6px] text-[11px] text-ink-2">
                      Here’s what will be rewritten for {selected.display_name}, replaced everywhere by the alias{' '}
                      <span className="font-mono">{preview.data.display_alias}</span>.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { icon: <IconFile size={18} />, n: preview.data.author_units + preview.data.speaker_units, label: 'Units they wrote or spoke', hint: 'Emails, docs, chats, meetings' },
                        { icon: <IconUsers size={18} />, n: preview.data.mentioned_units, label: 'Units that mention them', hint: 'Conversations, docs, threads' },
                        { icon: <IconFolder size={18} />, n: preview.data.files_to_rewrite, label: 'Files to rewrite', hint: 'Source files will be updated' },
                        { icon: <IconLink size={18} />, n: preview.data.cases_to_invalidate + (preview.data.findings_to_invalidate ?? 0), label: 'Dependent Cases to invalidate', hint: 'Recomputed from alias-bearing evidence' },
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

                    <FirstNameNote preview={preview.data} />

                    <div className="mt-[10px] rounded-lg border border-brand/30 bg-brand-soft px-[13px] py-[9px]">
                      <p className="flex items-center gap-2 text-[11px] font-bold text-brand-ink">
                        <IconShield size={15} /> What will happen
                      </p>
                      <p className="mt-1 pl-[23px] text-[9.5px] leading-[13px] text-ink">
                        We rewrite this person’s identity to their stable alias in source files, rebuild the search index and
                        embeddings, invalidate dependent Cases, and verify the original identity is absent from every public surface.
                        Their history, evidence and relationships are preserved under the alias.
                      </p>
                    </div>

                    <div className="mt-[7px]">
                      <label htmlFor="admin-token" className="mb-0.5 block text-[10.5px] font-bold leading-[14px] text-ink">
                        Admin token
                      </label>
                      <div className="flex items-center gap-[11px]">
                        <input
                          id="admin-token"
                          type="password"
                          value={adminToken}
                          onChange={(e) => setAdminToken(e.target.value)}
                          autoComplete="off"
                          placeholder="Required to authorize this action"
                          className="h-8 w-full min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-[11px] placeholder:text-ink-3"
                        />
                        <button
                          type="button"
                          className="inline-flex h-[33px] w-[135px] shrink-0 cursor-pointer items-center justify-center rounded-full bg-brand text-[11px] font-bold text-white transition-colors duration-200 hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={!adminToken}
                          onClick={() => {
                            setStage(0)
                            pseudonymise.mutate(selected)
                          }}
                        >
                          Pseudonymise
                        </button>
                      </div>
                      <p className="mt-1 text-[9px] text-ink-3">Never stored; used only for this request’s Authorization header.</p>
                    </div>
                  </div>
                )}
              </section>

              <section className={`${card} px-[17px] pb-4 pt-[12px]`} aria-labelledby="verified">
                <h2 id="verified" className="text-[15px] font-bold leading-[18px]">
                  What gets verified
                </h2>
                <p className="mb-[10px] text-[10px] leading-[14px] text-ink-2">
                  We check these surfaces for the person’s tracked identifiers. This is not cryptographic erasure.
                </p>
                <ul className="grid grid-cols-2 gap-x-3 gap-y-2 sm:flex sm:justify-between sm:gap-x-2.5">
                  {VERIFIED_SURFACES.map((v) => (
                    <li key={v.title} className="flex min-w-0 items-start gap-1.5 sm:shrink-0">
                      <span className="mt-px grid size-4 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
                        <IconCheck size={10} strokeWidth={3.5} />
                      </span>
                      <span className="leading-[12px]">
                        <span className="block whitespace-nowrap text-[8.5px] font-bold text-ink">{v.title}</span>
                        <span className="block max-w-[88px] truncate text-[8px] leading-[11px] text-ink-3" title={v.body}>
                          {v.body}
                        </span>
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
