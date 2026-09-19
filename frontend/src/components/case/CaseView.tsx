import { useEffect, useMemo, useState } from 'react'
import type { CaseReceipt, ReceiptClaim } from '../../types/api'
import { btnPrimary, btnSecondary, card, formatDate } from '../../lib'
import { SourceRow } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import {
  IconAlert,
  IconArrowLeft,
  IconArrowRight,
  IconBarChart,
  IconCalendar,
  IconCheck,
  IconDownload,
  IconEye,
  IconFile,
  IconGitBranch,
  IconLayers,
  IconLink,
  IconMessage,
  IconPrinter,
  IconScale,
  IconSearch,
  IconShield,
} from '../icons'
import { DecisionEvolution } from '../timeline/DecisionEvolution'
import { STATUS } from '../statusMap'
import { ConfidenceMeter, Section, StanceChip, StatusBadge } from '../ui'

// ------------------------------------------------------------------ claim

function claimVerdict(claim: ReceiptClaim) {
  if (claim.conflicts.length > 0) return { label: 'Partially supported', tone: 'bg-warn-soft text-warn', icon: <IconScale size={13} /> }
  if (claim.support.length > 0) return { label: 'Supported', tone: 'bg-ok-soft text-ok', icon: <IconCheck size={13} strokeWidth={3} /> }
  return { label: 'Unsupported', tone: 'bg-neutral-soft text-ink-2', icon: <IconEye size={13} /> }
}

function ClaimCard({ claim, index, onOpen }: { claim: ReceiptClaim; index: number; onOpen: (id: string) => void }) {
  const uncertain = claim.stance === 'UNCERTAIN'
  const v = claimVerdict(claim)
  return (
    <article
      className={`anim-fade-up flex h-full flex-col space-y-3 rounded-2xl border bg-surface p-5 shadow-card ${
        uncertain ? 'border-warn/40' : 'border-line'
      }`}
      style={{ animationDelay: `${Math.min(index, 6) * 60}ms` }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-extrabold uppercase tracking-wide text-ink-3">Claim {index + 1}</p>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-extrabold uppercase ${v.tone}`}>
          {v.icon}
          {v.label}
        </span>
      </div>
      <p className="text-base font-bold leading-snug text-ink">{claim.claim_text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <StanceChip stance={claim.stance} />
        <ConfidenceMeter confidence={claim.confidence} />
      </div>
      {claim.uncertainty && !claim.conflicts.length && (
        <p className="flex gap-2 rounded-xl bg-warn-soft p-3 text-sm text-warn">
          <IconAlert size={18} className="mt-0.5 shrink-0" />
          <span>
            <strong>Uncertainty:</strong> {claim.uncertainty}
          </span>
        </p>
      )}

      {claim.support.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-extrabold text-ink-3">
            Supporting source{claim.support.length === 1 ? '' : 's'} ({claim.support.length})
          </p>
          <div className="divide-y divide-line">
            {claim.support.map((c) => (
              <SourceRow key={c.evidence_id} citation={c} onOpen={onOpen} />
            ))}
          </div>
        </div>
      )}

      {claim.conflicts.length > 0 && (
        <div className="mt-auto space-y-1.5 border-t border-line pt-3">
          <p className="flex items-center gap-1.5 text-xs font-extrabold uppercase text-bad">
            <IconAlert size={14} /> Conflicting evidence ({claim.conflicts.length})
          </p>
          <div className="divide-y divide-line">
            {claim.conflicts.map((c) => (
              <SourceRow key={c.evidence_id} citation={c} onOpen={onOpen} />
            ))}
          </div>
          {claim.uncertainty && (
            <p className="rounded-lg bg-bad-soft p-2.5 text-xs text-ink">
              <strong>Notes:</strong> {claim.uncertainty}
            </p>
          )}
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

function CheckedMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value?: string; detail: string }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wide text-ink-3">
        {icon}
        {label}
      </p>
      {value && <p className="mt-1 text-base font-extrabold text-ink">{value}</p>}
      <p className="mt-0.5 text-xs leading-relaxed text-ink-2">{detail}</p>
    </div>
  )
}

const RISK_CAPTION: Record<string, string> = {
  LOW: 'Routine question, answered in a single pass.',
  MEDIUM: 'Commercial decision with multiple sources.',
  HIGH: 'High-stakes claim, checked thoroughly before showing.',
}

function HowChecked({ receipt, sources }: { receipt: CaseReceipt; sources: number }) {
  const [showTrace, setShowTrace] = useState(false)
  const r = receipt.review
  const rejected = receipt.validation.rejected_evidence_ids.length
  const counterDetail = !r.skeptic_ran
    ? 'Low risk: answered in a single pass.'
    : r.objections.length > 0
      ? `Found ${r.objections.length} item${r.objections.length === 1 ? '' : 's'} with an objection, addressed below.`
      : 'No contradicting evidence found.'
  const notesDetail = receipt.validation.notes.length > 0
    ? receipt.validation.notes.join(' ')
    : `Consistent across ${sources} source${sources === 1 ? '' : 's'} in the archive.`

  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 shadow-card">
      <h2 className="flex items-center gap-2 text-sm font-extrabold uppercase tracking-wide text-ink">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
          <IconShield size={14} />
        </span>
        How this was checked
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CheckedMetric icon={<IconAlert size={14} />} label="Risk level" value={r.risk_level.charAt(0) + r.risk_level.slice(1).toLowerCase()} detail={RISK_CAPTION[r.risk_level.toUpperCase()] ?? r.risk_triggers[0] ?? 'No elevated risk signals.'} />
        <CheckedMetric icon={<IconFile size={14} />} label="Skeptic ran" value={r.skeptic_ran ? 'Yes' : 'No'} detail="Checked for contradicting evidence and gaps." />
        <CheckedMetric icon={<IconSearch size={14} />} label="Counter evidence examined" value={r.skeptic_ran ? 'Yes' : 'No'} detail={counterDetail} />
        <CheckedMetric icon={<IconLayers size={14} />} label="Notes" detail={notesDetail} />
      </div>
      {rejected > 0 && (
        <p role="alert" className="flex items-center gap-2 rounded-xl bg-warn-soft p-3 text-sm font-bold text-warn">
          <IconAlert size={16} /> {rejected} citation(s) proposed by the model did not exist and were removed.
        </p>
      )}
      <button type="button" onClick={() => setShowTrace((v) => !v)} className="text-xs font-extrabold text-brand-ink">
        {showTrace ? 'Hide step-by-step trace' : 'Show step-by-step trace'}
      </button>
      {showTrace && (
        <ol className="border-t border-line pt-4">
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
          {r.risk_triggers.length > 0 && (
            <li className="rounded-xl bg-surface-2 p-3 text-sm">
              <p className="font-bold">Why it got this scrutiny</p>
              <ul className="ml-5 mt-2 list-disc space-y-1 text-ink-2">
                {r.risk_triggers.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </li>
          )}
        </ol>
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

  const { sources } = useMemo(() => {
    const all = receipt.claims.flatMap((c) => [...c.support, ...c.conflicts])
    return {
      sources: new Set(all.map((c) => c.evidence_id)).size,
      documents: new Set(all.map((c) => c.document_id)).size,
    }
  }, [receipt])

  const s = STATUS[receipt.status]
  const r = receipt.review

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

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
        <div className="mx-auto max-w-6xl space-y-4 px-4 pb-8 pt-6">
          <div className="no-print flex flex-wrap items-center justify-between gap-3">
            <a href="#/" className="inline-flex items-center gap-1.5 text-sm font-bold text-ink-2 hover:text-ink">
              <IconArrowLeft size={16} /> Case
            </a>
            <div className="flex gap-1">
              <button type="button" onClick={copyLink} title="Copy link" className="grid size-9 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-ink">
                {copied ? <IconCheck size={16} /> : <IconLink size={16} />}
              </button>
              <button type="button" onClick={() => window.print()} title="Print" className="grid size-9 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-ink">
                <IconPrinter size={16} />
              </button>
            </div>
          </div>

          <div className="anim-fade-up space-y-2">
            <h1 className="text-balance text-2xl font-extrabold leading-tight tracking-tight text-ink sm:text-3xl">{receipt.query}</h1>
            <StatusBadge status={receipt.status} />
            <p className="max-w-3xl text-base leading-relaxed text-ink">{receipt.answer_summary}</p>
            {!r.completed && (
              <p role="alert" className="flex items-center gap-2 rounded-xl bg-warn-soft p-3 text-sm font-bold text-warn">
                <IconAlert size={18} /> The contradiction check could not finish. Treat this answer as provisional.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------- body */}
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-10">
          <HowChecked receipt={receipt} sources={sources} />

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
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
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
            <section id="missing" className={`${card} scroll-mt-24 flex flex-col gap-4 p-5 sm:flex-row sm:items-start`}>
              <p className="flex shrink-0 items-center gap-2 text-sm font-extrabold text-ink sm:w-64">
                <IconEye size={18} className="text-ink-3" /> What the archive does not establish
              </p>
              <ul className="min-w-0 flex-1 list-disc space-y-1.5 pl-5 text-sm text-ink-2">
                {receipt.missing_information.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-xs text-ink-3">
            Opened {formatDate(receipt.created_at)}. Every citation above was re-checked against the archive when this page loaded.
          </p>
        </div>

        {/* ----------------------------------------------------- sticky rail */}
        <aside className="no-print space-y-5 lg:sticky lg:top-24 lg:max-h-[calc(100svh-7rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
          <div className={`${card} p-5`}>
            <h2 className="mb-3 flex items-center gap-2 text-base font-extrabold text-ink">
              <IconCalendar size={16} className="text-brand-ink" /> Case summary
            </h2>
            <dl className="space-y-2.5 text-sm">
              {[
                ['Case status', <StatusBadge key="s" status={receipt.status} />],
                ['Created', formatDate(receipt.created_at)],
                ['Claims', receipt.claims.length],
                ['Sources', sources],
                ['Case ID', `# ${receipt.case_id}`],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex items-center justify-between gap-3">
                  <dt className="text-ink-3">{label}</dt>
                  <dd className="truncate font-bold text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4 space-y-2 border-t border-line pt-4">
              <button type="button" onClick={() => scrollTo('claims')} className={`${btnPrimary} w-full`}>
                <IconLink size={16} /> View sources
              </button>
              <button type="button" onClick={() => scrollTo(receipt.timeline_events.length ? 'evolution' : 'claims')} className={`${btnSecondary} w-full`}>
                <IconBarChart size={16} /> Compare over time
              </button>
              <button type="button" onClick={() => onAsk('')} className={`${btnSecondary} w-full`}>
                <IconMessage size={16} /> Ask follow-up
              </button>
              <button type="button" onClick={() => window.print()} className={`${btnSecondary} w-full`}>
                <IconDownload size={16} /> Save / export
              </button>
            </div>
          </div>

          {receipt.related_questions.length > 0 && (
            <div className={`${card} p-5`}>
              <h2 className="mb-2 text-base font-extrabold text-ink">Related questions</h2>
              <ul className="divide-y divide-line">
                {receipt.related_questions.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => onAsk(q)}
                      className="group flex w-full cursor-pointer items-center justify-between gap-2 py-2.5 text-left text-sm font-semibold text-ink transition-colors duration-200 hover:text-brand-ink"
                    >
                      {q}
                      <IconArrowRight size={14} className="shrink-0 text-ink-3 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-brand-ink" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>

      {openId && <EvidenceDrawer evidenceId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
