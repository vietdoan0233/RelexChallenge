import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { Section } from '../components/ui'
import { btnDanger, btnPrimary, btnSecondary } from '../lib'
import { clearRecent, readRecent } from '../hooks/useRecentQuestions'
import { go } from '../hooks/useRoute'
import type { PersonSummary, PurgeResult } from '../types/api'

const SURFACES: Record<string, string> = {
  source_files: 'Canonical source files',
  database_rows: 'Database rows (incl. search index)',
  database_files: 'Database file, WAL and journal',
  artifacts_and_cache: 'Artifacts and cache',
  person_rows: 'Person / alias / link rows',
}

const STAGES = [
  'Locking the archive',
  'Sanitizing the canonical source',
  'Rebuilding from the sanitized source',
  'Purging database pages and derived files',
  'Verifying every surface',
]

function ResultPanel({ result, questions }: { result: PurgeResult; questions: string[] }) {
  return (
    <div className="space-y-4 rounded-xl border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/40">
      <h3 className="text-lg font-semibold">
        {result.verified ? 'Removal verified' : 'Removal could not be verified'}
      </h3>
      <ul className="grid gap-1 text-sm sm:grid-cols-2">
        <li>{result.files_sanitized} source files sanitized</li>
        <li>{result.units_anonymized} evidence units anonymized</li>
        <li>{result.cases_invalidated} dependent Cases invalidated</li>
        <li>
          {result.embeddings_regenerated} embeddings regenerated
          {result.embeddings_pending > 0 && `, ${result.embeddings_pending} pending`}
        </li>
      </ul>
      <table className="w-full text-sm">
        <caption className="mb-1 text-left font-semibold">Tracked identifiers found, per surface</caption>
        <tbody>
          {Object.entries(result.verification).map(([key, count]) => (
            <tr key={key} className="border-t border-emerald-200 dark:border-emerald-900">
              <th scope="row" className="py-1 pr-2 text-left font-normal">
                {SURFACES[key] ?? key}
              </th>
              <td className="py-1 text-right font-semibold">{count === 0 ? '0 — clean' : count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-zinc-700 dark:text-zinc-300">
        This is an application-level check of the identifiers the system tracks (names, reviewed
        aliases, emails) across storage it owns. It is not cryptographic erasure, and it cannot
        rule out an untracked nickname.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnPrimary} onClick={() => go.ask()}>
          Ask a question again
        </button>
        {questions.slice(0, 3).map((q) => (
          <button key={q} type="button" className={btnSecondary} onClick={() => go.ask(q)}>
            Re-ask: {q}
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
    mutationFn: (personId: string) => api.purge(personId),
    onSuccess: () => {
      // Questions that name the removed person are not offered back.
      const parts = (selected?.canonical_name ?? '').toLowerCase().split(/\s+/).filter((p) => p.length >= 3)
      setReask(readRecent().filter((q) => !parts.some((p) => q.toLowerCase().includes(p))))
      clearRecent()
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

  const shown = useMemo(
    () =>
      (people.data ?? []).filter((p) => p.canonical_name.toLowerCase().includes(filter.toLowerCase())),
    [people.data, filter],
  )
  const confirmed = selected !== null && typed.trim().toLowerCase() === selected.canonical_name.toLowerCase()

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="space-y-2 pt-6">
        <h1 className="text-3xl font-semibold">Privacy console</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Irreversibly anonymize one person out of the archive, its search index, its embeddings and
          every Case that depended on them. Unrelated organizational evidence is kept.
        </p>
      </div>

      {purge.isPending && (
        <p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-950 dark:bg-amber-950 dark:text-amber-100">
          {STAGES[stage]}… the archive is locked and cannot answer questions until this finishes.
        </p>
      )}
      {purge.isError && (
        <p role="alert" className="rounded-lg bg-rose-50 p-3 text-rose-900 dark:bg-rose-950 dark:text-rose-100">
          {purge.error.message} The system stays locked for review; nothing was reported as removed.
        </p>
      )}
      {purge.data && <ResultPanel result={purge.data} questions={reask} />}

      {!purge.isPending && !purge.data && (
        <div className="grid gap-6 md:grid-cols-2">
          <Section title="1. Choose a person">
            <label htmlFor="filter" className="sr-only">
              Filter people
            </label>
            <input
              id="filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name"
              className="w-full rounded-lg border border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900"
            />
            {people.isPending && <p role="status">Loading people…</p>}
            {people.isError && <p role="alert">{people.error.message}</p>}
            <ul className="max-h-96 space-y-1 overflow-y-auto">
              {shown.map((p) => (
                <li key={p.person_id}>
                  <button
                    type="button"
                    aria-pressed={selected?.person_id === p.person_id}
                    onClick={() => {
                      setSelected(p)
                      setTyped('')
                    }}
                    className={`flex min-h-11 w-full items-center justify-between rounded-lg border px-3 text-left text-sm ${
                      selected?.person_id === p.person_id
                        ? 'border-indigo-700 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-950'
                        : 'border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800'
                    }`}
                  >
                    <span className="font-medium">{p.canonical_name}</span>
                    <span className="text-xs opacity-70">
                      {p.author_units + p.speaker_units} own · {p.mentioned_units} mentioned
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="2. Review the impact">
            {!selected && <p className="text-zinc-600 dark:text-zinc-400">Select a person to preview.</p>}
            {selected && preview.isPending && <p role="status">Calculating impact…</p>}
            {selected && preview.isError && <p role="alert">{preview.error.message}</p>}
            {selected && preview.data && (
              <div className="space-y-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  {[
                    ['Units they authored or spoke', preview.data.author_units + preview.data.speaker_units],
                    ['Units that mention them', preview.data.mentioned_units],
                    ['Units to anonymize', preview.data.units_to_anonymize],
                    ['Source files to sanitize', preview.data.files_to_sanitize],
                    ['Cases to invalidate', preview.data.cases_to_invalidate],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                      <dt className="text-xs text-zinc-600 dark:text-zinc-400">{label}</dt>
                      <dd className="text-xl font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  This rewrites the app-owned canonical source. It cannot be undone.
                </p>
                <label htmlFor="confirm" className="block text-sm font-semibold">
                  Type “{selected.canonical_name}” to confirm
                </label>
                <input
                  id="confirm"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  autoComplete="off"
                  className="w-full rounded-lg border border-zinc-300 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900"
                />
                <button
                  type="button"
                  className={btnDanger}
                  disabled={!confirmed}
                  onClick={() => {
                    setStage(0)
                    purge.mutate(selected.person_id)
                  }}
                >
                  Permanently remove this person
                </button>
              </div>
            )}
          </Section>
        </div>
      )}
    </div>
  )
}
