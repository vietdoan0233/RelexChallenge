import { useEffect, useMemo, useState } from 'react'
import type { CaseReceipt, ReceiptClaim } from '../../types/api'
import { card, formatDate } from '../../lib'
import { SourceRow } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import {
  IconAlert,
  IconApprox,
  IconArrowLeft,
  IconBarChart,
  IconCalendar,
  IconCheck,
  IconCheckCircle,
  IconChevronDown,
  IconDownload,
  IconFile,
  IconGitBranch,
  IconHelp,
  IconLayers,
  IconLink,
  IconMessage,
  IconPrinter,
  IconSearch,
  IconShield,
  IconBulb,
} from '../icons'
import { DecisionEvolution } from '../timeline/DecisionEvolution'
import { ConfidenceMeter, Section, StanceChip, StatusBadge } from '../ui'

// ------------------------------------------------------------------ claim

function claimVerdict(claim: ReceiptClaim) {
  if (claim.conflicts.length > 0)
    return { label: 'Partially supported', tone: 'border-[#f4d9b0] bg-[#fdf3e2] text-[#a25f0c]', icon: <IconApprox size={11} /> }
  if (claim.support.length > 0)
    return { label: 'Supported', tone: 'border-[#b9e2cf] bg-[#eaf8f1] text-[#177049]', icon: <IconCheckCircle size={11} /> }
  return { label: 'Unsupported', tone: 'border-line bg-neutral-soft text-ink-2', icon: <IconHelp size={11} /> }
}

function SourceGroup({ title, tone, children }: { title: string; tone?: 'bad'; children: React.ReactNode }) {
  return (
    <details open className="group">
      <summary className={`flex cursor-pointer list-none items-center gap-1 text-[10px] font-bold ${tone === 'bad' ? 'text-bad' : 'text-ink'}`}>
        {tone === 'bad' && <IconAlert size={11} />}
        {title}
        <IconChevronDown size={12} className="text-ink-3 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="mt-1 divide-y divide-line">{children}</div>
    </details>
  )
}

function ClaimCard({ claim, index, onOpen }: { claim: ReceiptClaim; index: number; onOpen: (id: string) => void }) {
  const v = claimVerdict(claim)
  return (
    <article
      className={`anim-fade-up flex h-full flex-col gap-2.5 rounded-[10px] border bg-surface px-[13px] pb-[11px] pt-[11px] shadow-card ${
        claim.stance === 'UNCERTAIN' ? 'border-warn/40' : 'border-line'
      }`}
      style={{ animationDelay: `${Math.min(index, 6) * 60}ms` }}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11.5px] font-bold text-ink">Claim {index + 1}</p>
        <span className={`inline-flex h-5 items-center gap-1 rounded-full border px-2 text-[8.5px] font-bold uppercase tracking-wide ${v.tone}`}>
          {v.icon}
          {v.label}
        </span>
      </div>
      <p className="text-[11.5px] leading-[16px] text-ink">{claim.claim_text}</p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StanceChip stance={claim.stance} />
        <ConfidenceMeter confidence={claim.confidence} />
      </div>
      {claim.uncertainty && !claim.conflicts.length && (
        <p className="flex gap-1.5 rounded-lg bg-warn-soft p-2 text-[10px] leading-[14px] text-warn">
          <IconAlert size={13} className="mt-px shrink-0" />
          <span>
            <strong>Uncertainty:</strong> {claim.uncertainty}
          </span>
        </p>
      )}

      {claim.support.length > 0 && (
        <SourceGroup title={`Supporting source${claim.support.length === 1 ? '' : 's'} (${claim.support.length})`}>
          {claim.support.map((c) => (
            <SourceRow key={c.evidence_id} citation={c} onOpen={onOpen} />
          ))}
        </SourceGroup>
      )}

      {claim.conflicts.length > 0 && (
        <div className="mt-auto border-t border-line pt-2">
          <SourceGroup title={`Conflicting evidence (${claim.conflicts.length})`} tone="bad">
            {claim.conflicts.map((c) => (
              <SourceRow key={c.evidence_id} citation={c} onOpen={onOpen} />
            ))}
          </SourceGroup>
          {claim.uncertainty && (
            <p className="mt-1.5 rounded-md bg-bad-soft p-2 text-[9.5px] leading-[13px] text-ink">
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
        <p className="text-[11px] font-bold leading-tight">{title}</p>
        <p className="text-[10px] text-ink-2">{detail}</p>
      </div>
    </li>
  )
}

function CheckedMetric({
  icon,
  tone = 'bg-brand-soft text-brand-ink',
  label,
  value,
  detail,
}: {
  icon: React.ReactNode
  tone?: string
  label: string
  value?: string
  detail: string
}) {
  return (
    <div className="flex min-w-0 gap-2.5 lg:px-3 lg:first:pl-0 lg:last:pr-0">
      <span className={`grid size-[30px] shrink-0 place-items-center rounded-full ${tone}`}>{icon}</span>
      <div className="min-w-0">
        <p className="text-[10px] font-bold leading-tight text-ink">{label}</p>
        {value && <p className="text-[13px] font-bold leading-[18px] text-ink">{value}</p>}
        <p className="text-[9.5px] leading-[13px] text-ink-2">{detail}</p>
      </div>
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
    <div className={`${card} space-y-3 p-[15px]`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-[13px] font-bold text-ink">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">
            <IconShield size={13} />
          </span>
          How this was checked
        </h2>
        <button type="button" onClick={() => setShowTrace((v) => !v)} aria-expanded={showTrace} className="cursor-pointer text-[10px] font-bold text-brand-ink hover:underline">
          {showTrace ? 'Hide step-by-step trace' : 'Show step-by-step trace'}
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-0 lg:divide-x lg:divide-line">
        <CheckedMetric icon={<IconAlert size={15} />} tone="bg-orange-soft text-[#e0872e]" label="Risk level" value={r.risk_level.charAt(0) + r.risk_level.slice(1).toLowerCase()} detail={RISK_CAPTION[r.risk_level.toUpperCase()] ?? r.risk_triggers[0] ?? 'No elevated risk signals.'} />
        <CheckedMetric icon={<IconFile size={15} />} label="Skeptic ran" value={r.skeptic_ran ? 'Yes' : 'No'} detail="Checked for contradicting evidence and gaps." />
        <CheckedMetric icon={<IconSearch size={15} />} label="Counter evidence examined" value={r.skeptic_ran ? 'Yes' : 'No'} detail={counterDetail} />
        <CheckedMetric icon={<IconLayers size={15} />} label="Notes" detail={notesDetail} />
      </div>
      {rejected > 0 && (
        <p role="alert" className="flex items-center gap-2 rounded-xl bg-warn-soft p-3 text-sm font-bold text-warn">
          <IconAlert size={16} /> {rejected} citation(s) proposed by the model did not exist and were removed.
        </p>
      )}

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

function RailButton({ icon, children, primary, onClick }: { icon: React.ReactNode; children: string; primary?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-[34px] w-full cursor-pointer items-center justify-between rounded-full px-4 text-[11px] font-bold transition-colors duration-200 ${
        primary ? 'bg-brand text-white hover:bg-brand-strong' : 'border border-brand/50 bg-surface text-brand-ink hover:bg-brand-soft'
      }`}
    >
      <span className="flex items-center gap-2">
        {icon}
        {children}
      </span>
      <IconChevronDown size={13} className="-rotate-90" />
    </button>
  )
}

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
    return { sources: new Set(all.map((c) => c.evidence_id)).size }
  }, [receipt])

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
    <div className="mx-auto max-w-[1067px] px-4 pb-10 pt-[6px]">
      <div className="no-print flex h-5 items-center justify-between pl-[9px]">
        <a href="#/" className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-2 hover:text-ink">
          <IconArrowLeft size={13} /> Case
        </a>
        <div className="flex gap-1">
          <button type="button" onClick={copyLink} title="Copy link" className="grid size-6 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-ink">
            {copied ? <IconCheck size={14} /> : <IconLink size={14} />}
          </button>
          <button type="button" onClick={() => window.print()} title="Print" className="grid size-6 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-ink">
            <IconPrinter size={14} />
          </button>
        </div>
      </div>

      <div className="mt-[6px] grid gap-8 lg:grid-cols-[minmax(0,1fr)_236px]">
        {/* ------------------------------------------------------------ main */}
        <div className="min-w-0">
          <div className="anim-fade-up space-y-[9px] pl-[9px]">
            <h1 className="text-balance text-[22px] font-bold leading-7 tracking-tight text-ink">{receipt.query}</h1>
            <StatusBadge status={receipt.status} />
            <p className="max-w-[660px] text-[13.5px] leading-[21px] text-ink">{receipt.answer_summary}</p>
            {!r.completed && (
              <p role="alert" className="flex items-center gap-2 rounded-lg bg-warn-soft p-2.5 text-xs font-bold text-warn">
                <IconAlert size={16} /> The contradiction check could not finish. Treat this answer as provisional.
              </p>
            )}
          </div>

          <div className="mt-[14px] space-y-3">
            <HowChecked receipt={receipt} sources={sources} />

            {r.objections.length > 0 && (
              <Section id="objections" title="Objections raised by the check" hint="What the contradiction search argued against this answer." icon={<IconAlert size={16} />}>
                <ul className="space-y-2">
                  {r.objections.map((o) => (
                    <li key={o.text} className="rounded-[10px] border border-bad/40 bg-bad-soft p-3 text-[11px] text-bad">
                      <span className="mr-2 rounded-full bg-bad px-2 py-0.5 text-[9px] font-bold uppercase text-white">{o.severity.toLowerCase()}</span>
                      <span className="font-semibold text-ink">{o.text}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {receipt.claims.length > 0 && (
              <section id="claims" className="scroll-mt-24">
                <h2 className="sr-only">Claims and evidence</h2>
                <div className="grid gap-2 md:grid-cols-3">
                  {receipt.claims.map((claim, i) => (
                    <ClaimCard key={i} claim={claim} index={i} onOpen={setOpenId} />
                  ))}
                </div>
              </section>
            )}

            {receipt.conflict_resolution && (
              <section id="resolution" className={`${card} scroll-mt-24 border-l-4 border-l-bad p-[15px]`}>
                <h2 className="mb-1 text-[13px] font-bold text-ink">How conflicting evidence was weighed</h2>
                <p className="text-[12px] leading-[18px] text-ink">{receipt.conflict_resolution}</p>
              </section>
            )}

            {receipt.timeline_events.length > 0 && (
              <section id="evolution" className={`${card} scroll-mt-24 p-[15px]`}>
                <h2 className="flex items-center gap-2 text-[13px] font-bold text-ink">
                  <IconGitBranch size={15} className="text-brand-ink" /> Decision Evolution
                </h2>
                <p className="mb-3 text-[10px] text-ink-2">Key events from proposal to now. Only states the evidence supports, in date order.</p>
                <DecisionEvolution events={receipt.timeline_events} onOpen={setOpenId} />
              </section>
            )}

            {receipt.missing_information.length > 0 && (
              <section id="missing" className={`${card} flex scroll-mt-24 flex-col gap-3 px-[14px] py-[11px] sm:flex-row sm:items-start`}>
                <p className="flex shrink-0 items-center gap-2 text-[12px] font-bold text-ink sm:w-60">
                  <span className="grid size-6 place-items-center rounded-full bg-brand-soft text-brand-ink">
                    <IconBulb size={13} />
                  </span>
                  What the archive does not establish
                </p>
                <ul className="min-w-0 flex-1 list-disc space-y-1 pl-4 text-[10px] leading-[14px] text-ink-2">
                  {receipt.missing_information.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </section>
            )}

            <p className="pl-1 text-[10px] text-ink-3">
              Opened {formatDate(receipt.created_at)}. Every citation above was re-checked against the archive when this page loaded.
            </p>
          </div>
        </div>

        {/* ----------------------------------------------------------- rail */}
        <aside className="no-print space-y-[15px] lg:sticky lg:top-[68px] lg:self-start">
          <div className={`${card} p-[15px]`}>
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-bold text-ink">
              <IconCalendar size={15} className="text-brand-ink" /> Case summary
            </h2>
            <dl className="space-y-[9px] text-[10.5px]">
              {[
                ['Case status', <StatusBadge key="s" status={receipt.status} />],
                ['Created', <span key="c" className="inline-flex items-center gap-1.5"><IconCalendar size={12} className="text-ink-3" />{formatDate(receipt.created_at)}</span>],
                ['Claims', <span key="cl" className="inline-flex items-center gap-1.5"><IconLayers size={12} className="text-ink-3" />{receipt.claims.length}</span>],
                ['Sources', <span key="so" className="inline-flex items-center gap-1.5"><IconFile size={12} className="text-ink-3" />{sources}</span>],
                ['Case ID', <span key="id" title={receipt.case_id}># {receipt.case_id.slice(0, 8)}</span>],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex min-h-[19px] items-center justify-between gap-3">
                  <dt className="text-ink-2">{label}</dt>
                  <dd className="truncate font-semibold text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-[14px] space-y-[7px]">
              <RailButton primary icon={<IconLink size={13} />} onClick={() => scrollTo('claims')}>View sources</RailButton>
              <RailButton icon={<IconBarChart size={13} />} onClick={() => scrollTo(receipt.timeline_events.length ? 'evolution' : 'claims')}>Compare over time</RailButton>
              <RailButton icon={<IconMessage size={13} />} onClick={() => onAsk('')}>Ask follow-up</RailButton>
              <RailButton icon={<IconDownload size={13} />} onClick={() => window.print()}>Save / export</RailButton>
            </div>
          </div>

          {receipt.related_questions.length > 0 && (
            <div className={`${card} p-[15px]`}>
              <h2 className="mb-1 flex items-center gap-2 text-[13px] font-bold text-ink">
                <IconBulb size={15} className="text-brand-ink" /> Related questions
              </h2>
              <ul className="divide-y divide-line">
                {receipt.related_questions.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => onAsk(q)}
                      className="group flex w-full cursor-pointer items-center justify-between gap-2 py-[9px] text-left text-[10.5px] font-semibold leading-[14px] text-ink transition-colors duration-200 hover:text-brand-ink"
                    >
                      {q}
                      <IconChevronDown size={13} className="shrink-0 -rotate-90 text-ink-3 transition-transform duration-200 group-hover:translate-x-0.5" />
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
