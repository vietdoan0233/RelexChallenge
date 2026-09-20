import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { DocIcon } from '../components/evidence/CitationList'
import { EvidenceDrawer } from '../components/evidence/EvidenceDrawer'
import {
  IconAlert,
  IconArrowLeft,
  IconCheck,
  IconLock,
  IconShield,
  IconUser,
} from '../components/icons'
import { Skeleton } from '../components/ui'
import { go } from '../hooks/useRoute'
import { btnDanger, btnSecondary, card, formatDate } from '../lib'
import type { ContributionEntry } from '../types/api'

const RELATION_LABEL: Record<ContributionEntry['relation'], string> = {
  AUTHOR: 'Wrote',
  SPEAKER: 'Said',
  MENTIONED: 'Mentioned in',
}

function ContributionRow({
  entry,
  onOpen,
}: {
  entry: ContributionEntry
  onOpen: (evidenceId: string) => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(entry.evidence_id)}
        className="group flex w-full items-start gap-3 rounded-xl border border-line bg-surface p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-brand hover:shadow-card"
      >
        <span className="mt-0.5 shrink-0 text-ink-3">
          <DocIcon type={entry.document_type} size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs font-bold text-ink-3">
            <span className="text-brand-ink">{RELATION_LABEL[entry.relation]}</span>
            <span className="text-ink-2">{entry.document_title ?? entry.filename}</span>
            <span>· {formatDate(entry.event_date)}</span>
            {entry.thread_context && <span>· {entry.thread_context}</span>}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink">
            {entry.raw_text}
            {entry.is_truncated && (
              <span className="ml-1.5 text-xs font-bold text-warn">(cut off in the source)</span>
            )}
          </p>
          <span className="mt-1 flex items-center justify-between text-xs font-bold text-brand-ink">
            <span>Open in context</span>
            <span className="opacity-0 transition-opacity duration-200 group-hover:opacity-100">→</span>
          </span>
        </div>
      </button>
    </li>
  )
}

export function PersonPage({ subjectId }: { subjectId: string }) {
  const client = useQueryClient()
  const profile = useQuery({ queryKey: ['person', subjectId], queryFn: () => api.getPerson(subjectId) })
  const history = useQuery({
    queryKey: ['person-history', subjectId],
    queryFn: () => api.getPersonHistory(subjectId),
  })
  const [adminToken, setAdminToken] = useState('')
  const [showAdmin, setShowAdmin] = useState(false)
  const [confirmReversal, setConfirmReversal] = useState(false)
  const [openEvidenceId, setOpenEvidenceId] = useState<string | null>(null)

  const reverse = useMutation({
    mutationFn: () => api.reversePseudonymisation(subjectId, adminToken, confirmReversal),
    onSuccess: () => {
      // Every cached page (this profile, the people list, any Case that
      // cited or named this subject, archive stats) can have gone stale in
      // one step -- a full clear, not a few targeted invalidations, is
      // what pseudonymise already does in PrivacyPage and what reversal
      // must match (CLAUDE.md 18.0.4: derived surfaces are invalidated or
      // rebuilt, and a stale client cache is one of those surfaces too).
      client.clear()
      setConfirmReversal(false)
      setAdminToken('')
    },
  })

  if (profile.isPending) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-10">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (profile.isError || !profile.data) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-10 text-center">
        <p role="alert" className="text-bad">
          {profile.isError ? profile.error.message : 'Subject not found.'}
        </p>
        <button type="button" className={btnSecondary} onClick={() => go.privacy()}>
          <IconArrowLeft size={16} /> Back to Privacy console
        </button>
      </div>
    )
  }

  const p = profile.data
  const isPseudonymised = p.privacy_state === 'PSEUDONYMISED'

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <button type="button" className={btnSecondary} onClick={() => go.privacy()}>
        <IconArrowLeft size={16} /> Back to Privacy console
      </button>

      <div className={`${card} space-y-4 p-6`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
              <IconUser size={22} />
            </span>
            <div>
              <h1 className="text-2xl font-extrabold">{p.display_name ?? p.display_alias}</h1>
              {isPseudonymised && <p className="text-sm text-ink-2">Alias: {p.display_alias}</p>}
            </div>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold ${
              isPseudonymised ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'
            }`}
          >
            {isPseudonymised ? <IconLock size={14} /> : <IconCheck size={14} />}
            {isPseudonymised ? 'Pseudonymised' : 'Active'}
          </span>
        </div>
        {isPseudonymised && (
          <p className="rounded-xl bg-surface-2 p-3 text-xs text-ink-2">
            This participant's original identity has been replaced everywhere in the archive with
            this stable alias. Their full history and every relationship below are preserved; only
            the original name, email, and reviewed aliases were removed from ordinary storage. The
            original identity exists only in a separately encrypted vault.
            {p.pseudonymised_at && <> Pseudonymised {formatDate(p.pseudonymised_at)}.</>}
          </p>
        )}
        <div className="grid grid-cols-3 gap-3">
          {[
            [p.author_units, 'authored'],
            [p.speaker_units, 'spoken'],
            [p.mentioned_units, 'mentioned'],
          ].map(([n, label]) => (
            <div key={String(label)} className="rounded-xl bg-surface-2 p-3 text-center">
              <p className="text-xl font-extrabold tabular-nums">{n}</p>
              <p className="text-xs font-bold text-ink-2">{label}</p>
            </div>
          ))}
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-extrabold">Full history</h2>
        {history.isPending && <Skeleton className="h-40 w-full" />}
        {history.isError && <p role="alert" className="text-bad">{history.error.message}</p>}
        {history.data && history.data.length === 0 && (
          <p className="text-sm text-ink-2">No linked evidence.</p>
        )}
        {history.data && history.data.length > 0 && (
          <ul className="space-y-2">
            {history.data.map((entry) => (
              <ContributionRow
                key={`${entry.evidence_id}-${entry.relation}`}
                entry={entry}
                onOpen={setOpenEvidenceId}
              />
            ))}
          </ul>
        )}
      </section>

      {openEvidenceId && (
        <EvidenceDrawer evidenceId={openEvidenceId} onClose={() => setOpenEvidenceId(null)} />
      )}

      {isPseudonymised && (
        <section className={`${card} space-y-3 p-5`}>
          <button
            type="button"
            onClick={() => setShowAdmin((v) => !v)}
            className="flex w-full items-center justify-between text-left text-sm font-bold text-ink-2"
          >
            <span className="flex items-center gap-2">
              <IconShield size={16} /> Admin: reverse pseudonymisation
            </span>
            <span>{showAdmin ? '−' : '+'}</span>
          </button>
          {showAdmin && (
            <div className="space-y-3 border-t border-line pt-3">
              <p className="text-xs text-ink-2">
                Restores the active identity from the isolated reversal vault. This is a
                separately authenticated administrative action, not a normal profile capability.
              </p>
              <label htmlFor="admin-token" className="block text-xs font-bold text-ink">
                Admin token
              </label>
              <input
                id="admin-token"
                type="password"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                autoComplete="off"
                className="min-h-11 w-full rounded-full border border-line bg-surface-2 px-4 text-sm"
              />
              <label className="flex cursor-pointer items-start gap-2 text-xs text-ink">
                <input
                  type="checkbox"
                  checked={confirmReversal}
                  onChange={(e) => setConfirmReversal(e.target.checked)}
                  className="mt-0.5"
                />
                I understand this restores {p.display_alias}'s original name, email, and aliases
                everywhere in the archive.
              </label>
              {reverse.isError && (
                <p role="alert" className="flex items-center gap-2 text-sm text-bad">
                  <IconAlert size={16} /> {reverse.error.message}
                </p>
              )}
              {reverse.isSuccess && (
                <p className="flex items-center gap-2 text-sm text-ok">
                  <IconCheck size={16} /> Identity restored and verified.
                </p>
              )}
              <button
                type="button"
                className={btnDanger}
                disabled={!adminToken || !confirmReversal || reverse.isPending}
                onClick={() => reverse.mutate()}
              >
                {reverse.isPending ? 'Reversing…' : 'Reverse pseudonymisation'}
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
