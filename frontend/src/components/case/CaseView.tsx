import { useEffect, useMemo, useState } from 'react'
import type { CaseReceipt, ReceiptClaim } from '../../types/api'
import { btnSecondary, formatDate } from '../../lib'
import { CitationList } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import {
  IconAlert,
  IconArrowRight,
  IconCheck,
  IconEye,
  IconGitBranch,
  IconLayers,
  IconLink,
  IconPrinter,
  IconScale,
  IconShield,
} from '../icons'
import { DecisionEvolution } from '../timeline/DecisionEvolution'
import { STATUS } from '../statusMap'
import { ConfidenceMeter, Section, StanceChip, StatusBadge } from '../ui'

// ------------------------------------------------------------------ claim

function ClaimCard({ claim, index, onOpen }: { claim: ReceiptClaim; index: number; onOpen: (id: string) => void }) {
  const uncertain = claim.stance === 'UNCERTAIN'
  return (
    <article
      className={`anim-fade-up space-y-3 rounded-2xl border bg-surface p-5 shadow-card ${
        uncertain ? 'border-warn/40' : 'border-line'
      }`}
      style={{ animationDelay: `${Math.min(index, 6) * 60}ms` }}
    >
      <div className="flex flex-wrap items-center gap-3">
        <StanceChip stance={claim.stance} />
        <ConfidenceMeter confidence={claim.confidence} />
      </div>
      <p className="text-lg font-bold leading-snug text-ink">{claim.claim_text}</p>
      {claim.uncertainty && (
        <p className="flex gap-2 rounded-xl bg-warn-soft p-3 text-sm text-warn">
          <IconAlert size={18} className="mt-0.5 shrink-0" />
          <span>
            <strong>Uncertainty:</strong> {claim.uncertainty}
          </span>
        </p>
      )}
      <CitationList citations={claim.support} tone="support" onOpen={onOpen} />
      {claim.conflicts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-extrabold uppercase tracking-wide text-bad">Evidence that disagrees</p>
          <CitationList citations={claim.conflicts} tone="conflict" onOpen={onOpen} collapseAfter={2} />
        </div>
      )}
    </article>
  )
}

// --------------------------------------------------------------- pipeline

function Step({ state, title, detail }: { state: 'done' | 'skipped' | 'warn'; title: string; detail: string }) {
  const tone =
    state === 'done' ? 'bg-ok text-white' : state === 'warn' ? 'bg-warn text-white' : 'bg-neutral-soft text-ink-3'
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      <span className="absolute left-[13px] top-7 h-[calc(100%-1.5rem)] w-0.5 bg-line last:hidden" aria-hidden="true" />
      <span className={`relative z-10 grid size-7 shrink-0 place-items-center rounded-full ${tone}`}>
        {state === 'warn' ? <IconAlert size={14} /> : state === 'done' ? <IconCheck size={14} strokeWidth={3} /> : <span className="size-1.5 rounded-full bg-current" />}
      </span>
      <div>
        <p className="text-sm font-extrabold leading-tight">{title}</p>
        <p className="text-xs text-ink-2">{detail}</p>
      </div>
    </li>
  )
}

function HowChecked({ receipt, sources }: { receipt: CaseReceipt; sources: number }) {
  const r = receipt.review
  const rejected = receipt.validation.rejected_evidence_ids.length
  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-extrabold uppercase tracking-wide text-ink">How this was checked</h2>
        <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-extrabold uppercase text-brand-ink">
          {r.risk_level.toLowerCase()} scrutiny
        </span>
      </div>
      <ol>
        <Step state="done" title="Searched the archive" detail="Keyword and semantic search, with surrounding context." />
        <Step state="done" title="Drafted the answer" detail={`${receipt.claims.length} claim${receipt.claims.length === 1 ? '' : 's'}, each tied to evidence by ID.`} />
        {r.skeptic_ran ? (
          <Step
            state={r.completed ? 'done' : 'warn'}
            title={r.completed ? 'Searched for contradictions' : 'Contradiction check incomplete'}
            detail={`${r.counter_queries} targeted searches · ${r.counter_units_examined} new passages examined${r.objections.length ? ` · ${r.objections.length} objection${r.objections.length === 1 ? '' : 's'}` : ''}.`}
          />
        ) : (
          <Step state="skipped" title="Contradiction search skipped" detail="Low risk: answered in a single pass." />
        )}
        <Step
          state={r.reconciled ? 'done' : 'skipped'}
          title={r.reconciled ? 'Reconciled after the challenge' : 'No reconciliation needed'}
          detail={r.reconciled ? 'The answer was revised against the objections.' : 'Nothing found that changed the answer.'}
        />
        <Step
          state={rejected ? 'warn' : 'done'}
          title="Verified every citation"
          detail={rejected ? `${rejected} citation(s) proposed by the model did not exist and were removed.` : `All ${sources} sources confirmed in the archive.`}
        />
      </ol>
      {r.risk_triggers.length > 0 && (
        <details open className="rounded-xl bg-surface-2 p-3 text-sm">
          <summary className="cursor-pointer font-bold">Why it got this scrutiny</summary>
          <ul className="ml-5 mt-2 list-disc space-y-1 text-ink-2">
            {r.risk_triggers.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ main

export function CaseView({ receipt, onAsk }: { receipt: CaseReceipt; onAsk: (question: string) => void }) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = window.setTimeout(() => setCopied(false), 1800)
    return () => window.clearTimeout(t)
  }, [copied])

  const { sources, documents } = useMemo(() => {
    const all = receipt.claims.flatMap((c) => [...c.support, ...c.conflicts])
    return {
      sources: new Set(all.map((c) => c.evidence_id)).size,
      documents: new Set(all.map((c) => c.document_id)).size,
    }
  }, [receipt])

  const s = STATUS[receipt.status]
  const r = receipt.review
  const sections = [
    receipt.review.objections.length > 0 && { id: 'objections', label: 'Objections raised' },
    receipt.claims.length > 0 && { id: 'claims', label: 'Claims & evidence' },
    receipt.conflict_resolution && { id: 'resolution', label: 'How conflicts were weighed' },
    receipt.timeline_events.length > 0 && { id: 'evolution', label: 'Decision evolution' },
    receipt.missing_information.length > 0 && { id: 'missing', label: 'What is not established' },
    receipt.related_questions.length > 0 && { id: 'related', label: 'Follow-up questions' },
  ].filter(Boolean) as { id: string; label: string }[]

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
    } catch {
      /* clipboard unavailable: the URL is still in the address bar */
    }
  }

  return (
    <div>
      {/* ------------------------------------------------------ verdict hero */}
      <section className={`bg-gradient-to-b ${s.band} to-transparent`}>
        <div className="mx-auto max-w-6xl space-y-5 px-4 pb-8 pt-8">
          <div className="no-print flex flex-wrap items-center justify-between gap-3">
            <a href="#/" className={btnSecondary}>
              ← New question
            </a>
            <div className="flex gap-2">
              <button type="button" onClick={copyLink} className={btnSecondary}>
                {copied ? <IconCheck size={16} /> : <IconLink size={16} />}
                {copied ? 'Link copied' : 'Copy link'}
              </button>
              <button type="button" onClick={() => window.print()} className={btnSecondary}>
                <IconPrinter size={16} /> Print
              </button>
            </div>
          </div>

          <div className="anim-fade-up space-y-4">
            <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-ink-3">Your question</p>
            <h1 className="text-balance text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">{receipt.query}</h1>
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={receipt.status} large />
              <span className="text-sm font-semibold text-ink-2">{s.blurb}</span>
            </div>
            {!r.completed && (
              <p role="alert" className="flex items-center gap-2 rounded-xl bg-warn-soft p-3 text-sm font-bold text-warn">
                <IconAlert size={18} /> The contradiction check could not finish. Treat this answer as provisional.
              </p>
            )}
            <div className="rounded-3xl border border-line bg-surface p-6 shadow-lift sm:p-8">
              <p className="mb-2 flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.14em] text-brand-ink">
                <IconShield size={14} /> The answer
              </p>
              <p className="text-pretty text-xl font-semibold leading-relaxed text-ink sm:text-2xl">{receipt.answer_summary}</p>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { k: 'Claims', v: receipt.claims.length, icon: <IconLayers size={16} /> },
              { k: 'Sources cited', v: sources, icon: <IconEye size={16} /> },
              { k: 'Documents', v: documents, icon: <IconScale size={16} /> },
              {
                k: 'Contradiction check',
                v: r.skeptic_ran ? `${r.counter_queries} searches` : 'Single pass',
                icon: <IconGitBranch size={16} />,
              },
            ].map((m) => (
              <div key={m.k} className="rounded-2xl border border-line bg-surface p-4 shadow-card">
                <dt className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-ink-3">
                  {m.icon}
                  {m.k}
                </dt>
                <dd className="mt-1 text-2xl font-extrabold tabular-nums tracking-tight">{m.v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* --------------------------------------------------------------- body */}
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-12">
          {r.objections.length > 0 && (
            <Section id="objections" title="Objections raised by the check" hint="What the contradiction search argued against this answer." icon={<IconAlert size={20} />}>
              <ul className="space-y-2">
                {r.objections.map((o) => (
                  <li key={o.text} className="rounded-2xl border border-bad/40 bg-bad-soft p-4 text-bad">
                    <span className="mr-2 rounded-full bg-bad px-2 py-0.5 text-xs font-extrabold uppercase text-white">{o.severity.toLowerCase()}</span>
                    <span className="font-semibold text-ink">{o.text}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {receipt.claims.length > 0 && (
            <Section id="claims" title="Claims and evidence" hint="Open any source to read it in context." icon={<IconLayers size={20} />}>
              <div className="space-y-4">
                {receipt.claims.map((claim, i) => (
                  <ClaimCard key={i} claim={claim} index={i} onOpen={setOpenId} />
                ))}
              </div>
            </Section>
          )}

          {receipt.conflict_resolution && (
            <Section id="resolution" title="How conflicting evidence was weighed" icon={<IconScale size={20} />}>
              <div className="rounded-2xl border-l-4 border-bad bg-bad-soft p-5">
                <p className="text-base font-semibold leading-relaxed text-ink">{receipt.conflict_resolution}</p>
              </div>
            </Section>
          )}

          {receipt.timeline_events.length > 0 && (
            <Section id="evolution" title="Decision evolution" hint="Only states the evidence supports, in date order. Nothing is invented to fill a gap." icon={<IconGitBranch size={20} />}>
              <DecisionEvolution events={receipt.timeline_events} onOpen={setOpenId} />
            </Section>
          )}

          {receipt.missing_information.length > 0 && (
            <Section id="missing" title="What the archive does not establish" hint="Knowing the limits is part of the answer." icon={<IconEye size={20} />}>
              <ul className="space-y-2">
                {receipt.missing_information.map((m) => (
                  <li key={m} className="flex gap-3 rounded-xl border border-warn/30 bg-warn-soft p-3 text-sm font-semibold text-ink">
                    <IconAlert size={18} className="mt-0.5 shrink-0 text-warn" />
                    {m}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {receipt.related_questions.length > 0 && (
            <Section id="related" title="Ask a follow-up" icon={<IconArrowRight size={20} />}>
              <ul className="grid gap-2 sm:grid-cols-2">
                {receipt.related_questions.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => onAsk(q)}
                      className="group flex h-full w-full cursor-pointer items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-4 text-left font-semibold shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand"
                    >
                      {q}
                      <IconArrowRight size={18} className="shrink-0 text-brand-ink transition-transform duration-200 group-hover:translate-x-1" />
                    </button>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          <p className="text-xs text-ink-3">
            Opened {formatDate(receipt.created_at)}. Every citation above was re-checked against the archive when this page loaded.
          </p>
        </div>

        {/* ----------------------------------------------------- sticky rail */}
        <aside className="no-print space-y-5 lg:sticky lg:top-24 lg:max-h-[calc(100svh-7rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
          <HowChecked receipt={receipt} sources={sources} />
          {sections.length > 1 && (
            <nav aria-label="On this page" className="rounded-2xl border border-line bg-surface p-4 shadow-card">
              <h2 className="mb-2 text-sm font-extrabold uppercase tracking-wide">On this page</h2>
              <ul className="space-y-0.5">
                {sections.map((sec) => (
                  <li key={sec.id}>
                    <a href={`#${sec.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(sec.id)?.scrollIntoView({ behavior: 'smooth' }) }} className="block cursor-pointer rounded-lg px-3 py-2 text-sm font-semibold text-ink-2 transition-colors duration-200 hover:bg-brand-soft hover:text-ink">
                      {sec.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </aside>
      </div>

      {openId && <EvidenceDrawer evidenceId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
