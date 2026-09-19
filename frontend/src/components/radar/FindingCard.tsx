import { useState } from 'react'
import type { FindingCard as Card, RadarAssessment, RadarCheck } from '../../types/api'
import { btnSecondary, formatDate } from '../../lib'
import { CitationList } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import { go } from '../../hooks/useRoute'

// The Radar may say only these four things, and never that an idea should be
// pursued: the labels are deliberately hedged.
const ASSESSMENT: Record<RadarAssessment, { label: string; cls: string }> = {
  STILL_BLOCKED: {
    label: 'Still blocked',
    cls: 'bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100',
  },
  PARTIALLY_CHANGED: {
    label: 'Partially changed',
    cls: 'bg-amber-100 text-amber-950 dark:bg-amber-950 dark:text-amber-100',
  },
  WORTH_REASSESSING: {
    label: 'Worth reassessing',
    cls: 'bg-indigo-100 text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100',
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    cls: 'bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100',
  },
}

const CHECKS = [
  'Genuinely rejected or deferred',
  'Blocker actually stated',
  'Hidden or secondary blocker',
  'Change addresses the blocker',
  'External source credible',
  'Recent evidence against reopening',
  'Obsolete for another reason',
]

function Lens({ label, tone, children }: { label: string; tone: 'internal' | 'external' | 'assessment'; children: React.ReactNode }) {
  const cls =
    tone === 'internal'
      ? 'border-emerald-600/60 bg-white dark:bg-zinc-900'
      : tone === 'external'
        ? 'border-sky-600/60 bg-sky-50 dark:bg-sky-950/40'
        : 'border-dashed border-indigo-500 bg-indigo-50/60 dark:bg-indigo-950/30'
  return (
    <div className={`space-y-2 rounded-lg border p-3 ${cls}`}>
      <p className="text-xs font-bold uppercase tracking-wide text-zinc-700 dark:text-zinc-300">{label}</p>
      {children}
    </div>
  )
}

function CheckRow({ result }: { result?: RadarCheck }) {
  if (!result) return <span className="text-zinc-600 dark:text-zinc-400">Not run</span>
  if (!result.answered) return <span className="font-semibold text-amber-900 dark:text-amber-200">Cannot be answered</span>
  return result.passed ? (
    <span className="font-semibold text-emerald-800 dark:text-emerald-300">Survives</span>
  ) : (
    <span className="font-semibold text-rose-800 dark:text-rose-300">Counts against</span>
  )
}

export function FindingCard({ card }: { card: Card }) {
  const [openId, setOpenId] = useState<string | null>(null)
  const a = ASSESSMENT[card.assessment]
  return (
    <article className="space-y-5 rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-widest text-indigo-800 dark:text-indigo-300">
          Reconsideration candidate
        </p>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${a.cls}`}>{a.label}</span>
      </header>

      <div className="space-y-1">
        <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-400">Original proposal</p>
        <h2 className="text-xl font-semibold">{card.proposal}</h2>
        <CitationList citations={card.proposal_citations} tone="neutral" onOpen={setOpenId} />
      </div>

      <div className="space-y-1">
        <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-400">
          Original outcome:{' '}
          <span className="rounded border border-zinc-400 px-2 py-0.5 text-xs">{card.outcome === 'REJECTED' ? 'Rejected' : 'Deferred'}</span>
        </p>
        <CitationList citations={card.outcome_citations} tone="neutral" onOpen={setOpenId} />
      </div>

      <div className="space-y-1">
        <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-400">Why it was stopped</p>
        <p>{card.blocker}</p>
        <CitationList citations={card.blocker_citations} tone="neutral" onOpen={setOpenId} />
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          <span className="font-semibold">Would need to change:</span> {card.monitorable_condition}
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-semibold text-zinc-600 dark:text-zinc-400">What may have changed</p>
        <Lens label="Internal evidence — from the archive" tone="internal">
          {card.internal_change_citations.length > 0 ? (
            <CitationList citations={card.internal_change_citations} tone="support" onOpen={setOpenId} />
          ) : (
            <p className="text-sm text-zinc-700 dark:text-zinc-300">No internal evidence of a change was found.</p>
          )}
          {card.current_state_citations.length > 0 && (
            <>
              <p className="pt-1 text-xs font-semibold">Recent internal state</p>
              <CitationList citations={card.current_state_citations} tone="neutral" onOpen={setOpenId} />
            </>
          )}
        </Lens>
        <Lens label="External signals — outside the organization; not internal facts" tone="external">
          {card.external_signals.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {card.external_signals.map((s) => (
                <li key={s.signal_id}>
                  <span className="font-semibold">{s.title}</span> · {s.source} · {formatDate(s.published)}
                  {s.url && (
                    <>
                      {' '}
                      <a href={s.url} rel="noreferrer noopener" target="_blank" className="text-sky-800 underline dark:text-sky-300">
                        source
                      </a>
                    </>
                  )}
                  <br />
                  {s.summary}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-700 dark:text-zinc-300">No curated external signal applies.</p>
          )}
        </Lens>
        <Lens label="Assessment — an interpretation, not evidence" tone="assessment">
          {card.changed_condition && <p className="text-sm italic">{card.changed_condition}</p>}
          <p className="text-sm italic">{card.assessment_rationale}</p>
        </Lens>
      </div>

      <div className="space-y-1 rounded-lg bg-amber-50 p-3 dark:bg-amber-950/30">
        <p className="text-sm font-bold">Unestablished</p>
        <ul className="ml-5 list-disc text-sm">
          {card.unestablished.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </div>

      <p className="text-sm">
        <span className="font-semibold">Next useful check:</span> {card.next_check}
      </p>

      <details className="text-sm">
        <summary className="cursor-pointer font-semibold">Skeptic checks (seven)</summary>
        <ol className="mt-2 space-y-1">
          {CHECKS.map((label, i) => {
            const result = card.checks.find((c) => c.check === i + 1)
            return (
              <li key={label} className="flex flex-wrap justify-between gap-2 border-t border-zinc-200 py-1 dark:border-zinc-800">
                <span>
                  {i + 1}. {label}
                </span>
                <CheckRow result={result} />
              </li>
            )
          })}
        </ol>
      </details>

      <button type="button" className={btnSecondary} onClick={() => go.caseView(card.case_id)}>
        Open the validated Case
      </button>
      {openId && <EvidenceDrawer evidenceId={openId} onClose={() => setOpenId(null)} />}
    </article>
  )
}
