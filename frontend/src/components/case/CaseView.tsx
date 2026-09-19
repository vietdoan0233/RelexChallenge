import { useState } from 'react'
import type { CaseReceipt, ReceiptClaim } from '../../types/api'
import { CitationList } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import { DecisionEvolution } from '../timeline/DecisionEvolution'
import { ConfidenceChip, Section, StanceChip, StatusBadge } from '../ui'
import { btnSecondary } from '../../lib'

function ClaimCard({ claim, onOpen }: { claim: ReceiptClaim; onOpen: (id: string) => void }) {
  return (
    <article className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center gap-2">
        <StanceChip stance={claim.stance} />
        <ConfidenceChip confidence={claim.confidence} />
      </div>
      <p className="text-base font-medium text-zinc-900 dark:text-zinc-100">{claim.claim_text}</p>
      {claim.uncertainty && (
        <p className="text-sm text-amber-900 dark:text-amber-200">
          <span className="font-semibold">Uncertainty:</span> {claim.uncertainty}
        </p>
      )}
      <CitationList citations={claim.support} tone="support" onOpen={onOpen} />
      <CitationList citations={claim.conflicts} tone="conflict" onOpen={onOpen} />
    </article>
  )
}

function ReviewPanel({ review }: { review: CaseReceipt['review'] }) {
  return (
    <div className="space-y-2 rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <p>
        <span className="font-semibold">Risk level:</span> {review.risk_level.toLowerCase()}
        {review.skeptic_ran
          ? ` · checked for contradictions with ${review.counter_queries} targeted searches (${review.counter_units_examined} new passages examined)`
          : ' · answered in a single pass'}
        {review.reconciled && ' · reconciled after the check'}
      </p>
      {!review.completed && (
        <p role="alert" className="font-semibold text-amber-900 dark:text-amber-200">
          The contradiction check could not finish. Treat this answer as provisional.
        </p>
      )}
      {review.risk_triggers.length > 0 && (
        <details>
          <summary className="cursor-pointer font-semibold">Why this was checked</summary>
          <ul className="ml-5 mt-1 list-disc">
            {review.risk_triggers.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </details>
      )}
      {review.objections.length > 0 && (
        <div>
          <p className="font-semibold">Objections raised by the check</p>
          <ul className="ml-5 list-disc">
            {review.objections.map((o) => (
              <li key={o.text}>
                {o.text} <span className="opacity-70">({o.severity.toLowerCase()})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function CaseView({
  receipt,
  onAsk,
}: {
  receipt: CaseReceipt
  onAsk: (question: string) => void
}) {
  const [openId, setOpenId] = useState<string | null>(null)
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-400">
          Question
        </p>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{receipt.query}</h1>
        <StatusBadge status={receipt.status} />
        <p className="text-lg leading-relaxed text-zinc-900 dark:text-zinc-100">
          {receipt.answer_summary}
        </p>
      </header>

      <ReviewPanel review={receipt.review} />

      {receipt.claims.length > 0 && (
        <Section title="Claims and evidence" hint="Open any source to read it in context.">
          <div className="space-y-4">
            {receipt.claims.map((claim, i) => (
              <ClaimCard key={i} claim={claim} onOpen={setOpenId} />
            ))}
          </div>
        </Section>
      )}

      {receipt.conflict_resolution && (
        <Section title="How conflicting evidence was resolved">
          <div className="rounded-xl border-l-4 border-rose-600 bg-rose-50 p-4 text-zinc-900 dark:bg-rose-950/40 dark:text-zinc-100">
            <p>{receipt.conflict_resolution}</p>
          </div>
        </Section>
      )}

      {receipt.timeline_events.length > 0 && (
        <Section title="Decision evolution" hint="Only states the evidence supports, in date order.">
          <DecisionEvolution events={receipt.timeline_events} onOpen={setOpenId} />
        </Section>
      )}

      {receipt.missing_information.length > 0 && (
        <Section title="What the archive does not establish">
          <ul className="ml-5 list-disc space-y-1">
            {receipt.missing_information.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </Section>
      )}

      {receipt.validation.rejected_evidence_ids.length > 0 && (
        <p role="note" className="text-sm text-zinc-600 dark:text-zinc-400">
          {receipt.validation.rejected_evidence_ids.length} citation(s) proposed by the model were
          rejected because they did not exist in the archive.
        </p>
      )}

      {receipt.related_questions.length > 0 && (
        <Section title="Related questions">
          <div className="flex flex-wrap gap-2">
            {receipt.related_questions.map((q) => (
              <button key={q} type="button" className={btnSecondary} onClick={() => onAsk(q)}>
                {q}
              </button>
            ))}
          </div>
        </Section>
      )}

      {openId && <EvidenceDrawer evidenceId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
