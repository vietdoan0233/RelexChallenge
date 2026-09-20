import { useState } from 'react'
import type { Citation, FindingCard as Card, RadarCheck } from '../../types/api'
import { card as cardClass, formatDate } from '../../lib'
import { CitationList } from '../evidence/CitationList'
import { EvidenceDrawer } from '../evidence/EvidenceDrawer'
import { IconAlert, IconArrowRight, IconBulb, IconCheck, IconDotsVertical, IconFile, IconFolder, IconLink, IconX } from '../icons'
import { go } from '../../hooks/useRoute'
import { ASSESSMENT } from './assessments'

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
      ? 'border-ok/40 bg-surface'
      : tone === 'external'
        ? 'border-brand/40 bg-brand-soft'
        : 'border-dashed border-purple bg-purple-soft'
  const tag = tone === 'internal' ? 'text-ok' : tone === 'external' ? 'text-brand-ink' : 'text-purple'
  return (
    <div className={`space-y-2 rounded-2xl border p-4 ${cls}`}>
      <p className={`text-xs font-extrabold uppercase tracking-wide ${tag}`}>{label}</p>
      {children}
    </div>
  )
}

function CheckPill({ index, result }: { index: number; result?: RadarCheck }) {
  const state = !result ? 'none' : !result.answered ? 'open' : result.passed ? 'pass' : 'fail'
  const style = {
    pass: 'border-ok/40 bg-ok-soft text-ok',
    fail: 'border-bad/40 bg-bad-soft text-bad',
    open: 'border-warn/40 bg-warn-soft text-warn',
    none: 'border-line bg-surface-2 text-ink-3',
  }[state]
  const word = { pass: 'Survives', fail: 'Counts against', open: 'Cannot be answered', none: 'Not run' }[state]
  return (
    <li className={`flex items-center gap-3 rounded-xl border p-3 text-sm ${style}`}>
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-current/15">
        {state === 'pass' ? <IconCheck size={14} strokeWidth={3} /> : state === 'fail' ? <IconX size={14} strokeWidth={3} /> : <IconAlert size={14} />}
      </span>
      <span className="flex-1 font-semibold text-ink">
        {index + 1}. {CHECKS[index]}
      </span>
      <span className="text-xs font-extrabold uppercase">{word}</span>
    </li>
  )
}

function MiniLink({ citation, onOpen }: { citation?: Citation; onOpen: (id: string) => void }) {
  if (!citation) return null
  return (
    <button
      type="button"
      onClick={() => onOpen(citation.evidence_id)}
      className="mt-1 inline-flex max-w-full cursor-pointer items-center gap-1 text-left text-[10px] font-medium text-brand-ink hover:underline"
    >
      <IconLink size={11} className="shrink-0" />
      <span className="truncate underline decoration-brand/30 underline-offset-2">
        {citation.document_title ?? citation.filename} · {formatDate(citation.event_date)}
      </span>
    </button>
  )
}

function MiniColumn({
  icon,
  label,
  body,
  citation,
  onOpen,
  muted,
}: {
  icon: React.ReactNode
  label: string
  body: string
  citation?: Citation
  onOpen: (id: string) => void
  muted?: boolean
}) {
  return (
    <div className={`flex min-w-0 gap-2 ${muted ? 'rounded-lg bg-surface-2 px-3 py-2.5' : 'px-1'}`}>
      <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink">{icon}</span>
      <div className="min-w-0">
        <p className="text-[10.5px] font-bold leading-[16px] text-ink">{label}</p>
        <p className="line-clamp-3 text-[10px] leading-[13px] text-ink-2">{body}</p>
        <MiniLink citation={citation} onOpen={onOpen} />
      </div>
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[2rem_1fr] gap-3">
      <span className="grid size-8 place-items-center rounded-full bg-deep text-sm font-extrabold text-white">{n}</span>
      <div className="min-w-0 space-y-2">
        <h3 className="text-sm font-extrabold uppercase tracking-wide text-ink-2">{title}</h3>
        {children}
      </div>
    </div>
  )
}

export function FindingCard({ card }: { card: Card }) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const a = ASSESSMENT[card.assessment]
  const changedBody = card.changed_condition ?? card.assessment_rationale
  const changedCitation = card.internal_change_citations[0] ?? card.current_state_citations[0]

  return (
    <article className={`${cardClass} anim-fade-up overflow-hidden`}>
      <div className="px-3 pb-[8px] pt-[13px]">
        <div className="flex items-start gap-[17px]">
          <span className={`inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[9px] font-bold uppercase tracking-wide ${a.tone}`}>
            {a.icon}
            {a.label}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="line-clamp-1 text-[17px] font-bold leading-[19px] text-ink">{card.proposal}</h2>
            <p className="text-[11px] leading-[13px] text-ink-2">
              {card.outcome === 'REJECTED' ? 'Rejected' : 'Deferred'} · {card.blocker_category}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              className="inline-flex h-[30px] cursor-pointer items-center gap-1.5 rounded-full bg-brand px-[18px] text-[11px] font-bold text-white transition-colors duration-200 hover:bg-brand-strong"
              onClick={() => go.caseView(card.case_id)}
            >
              Open Case <IconArrowRight size={14} />
            </button>
            <button
              type="button"
              aria-expanded={expanded}
              aria-label={expanded ? 'Hide full analysis' : 'Show full analysis'}
              onClick={() => setExpanded((v) => !v)}
              className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-full text-ink-3 transition-colors duration-200 hover:bg-surface-2 hover:text-ink"
            >
              <IconDotsVertical size={16} />
            </button>
          </div>
        </div>

        <div className="mt-3 grid gap-y-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_170px] lg:divide-x lg:divide-line">
          <MiniColumn icon={<IconFile size={11} />} label="Original proposal" body={card.proposal} citation={card.proposal_citations[0]} onOpen={setOpenId} />
          <div className="lg:pl-3">
            <MiniColumn icon={<IconX size={11} />} label="Why it was stopped" body={card.blocker} citation={card.blocker_citations[0]} onOpen={setOpenId} />
          </div>
          <div className="lg:pl-3">
            <MiniColumn icon={<IconArrowRight size={11} className="-rotate-45" />} label="What may have changed" body={changedBody} citation={changedCitation} onOpen={setOpenId} />
          </div>
          <div className="lg:ml-3">
            <MiniColumn icon={<IconBulb size={11} />} label="Still unknown" body={card.unestablished[0] ?? 'Nothing flagged.'} onOpen={setOpenId} muted />
          </div>
        </div>

        <div className="mt-2 flex items-center justify-between border-t border-line pt-[7px] text-[10px] text-ink-3">
          <span className="inline-flex items-center gap-1.5">
            <IconFolder size={12} /> Case {card.case_id} · Last updated {formatDate(card.created_at)}
          </span>
          <button type="button" onClick={() => setExpanded((v) => !v)} className="cursor-pointer font-bold text-brand-ink">
            {expanded ? 'Show less' : 'Show full analysis'}
          </button>
        </div>
      </div>

      {expanded && (
      <div className="space-y-7 border-t border-line p-6">
        <p className="rounded-xl bg-surface-2 p-3 text-sm font-semibold text-ink-2">{a.meaning} This is a prompt to look again, not a recommendation.</p>

        <Step n={1} title="Original proposal">
          <CitationList citations={card.proposal_citations} tone="neutral" onOpen={setOpenId} collapseAfter={2} />
        </Step>
        <Step n={2} title={`Outcome: ${card.outcome === 'REJECTED' ? 'Rejected' : 'Deferred'}`}>
          <CitationList citations={card.outcome_citations} tone="neutral" onOpen={setOpenId} collapseAfter={2} />
        </Step>
        <Step n={3} title="Why it was stopped">
          <p className="text-base font-semibold text-ink">{card.blocker}</p>
          <CitationList citations={card.blocker_citations} tone="neutral" onOpen={setOpenId} collapseAfter={2} />
          <p className="text-sm text-ink-2">
            <strong>Would need to change:</strong> {card.monitorable_condition}
          </p>
        </Step>
        <Step n={4} title="What may have changed">
          <div className="space-y-3">
            <Lens label="Internal evidence · from the archive" tone="internal">
              {card.internal_change_citations.length > 0 ? (
                <CitationList citations={card.internal_change_citations} tone="support" onOpen={setOpenId} collapseAfter={2} />
              ) : (
                <p className="text-sm text-ink-2">No internal evidence of a change was found.</p>
              )}
              {card.current_state_citations.length > 0 && (
                <>
                  <p className="pt-1 text-xs font-extrabold uppercase text-ink-3">Recent internal state</p>
                  <CitationList citations={card.current_state_citations} tone="neutral" onOpen={setOpenId} collapseAfter={2} />
                </>
              )}
            </Lens>
            <Lens label="External signals · outside the organization, not internal facts" tone="external">
              {card.external_signals.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {card.external_signals.map((s) => (
                    <li key={s.signal_id}>
                      <strong>{s.title}</strong> · {s.source} · {formatDate(s.published)}{' '}
                      {s.url && (
                        <a href={s.url} rel="noreferrer noopener" target="_blank" className="font-bold text-brand-ink underline">
                          source
                        </a>
                      )}
                      <br />
                      {s.summary}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-2">No curated external signal applies.</p>
              )}
            </Lens>
            <Lens label="Assessment · an interpretation, not evidence" tone="assessment">
              {card.changed_condition && <p className="text-sm italic text-ink">{card.changed_condition}</p>}
              <p className="text-sm italic text-ink">{card.assessment_rationale}</p>
            </Lens>
          </div>
        </Step>

        <div className="space-y-2 rounded-2xl border border-warn/40 bg-warn-soft p-4">
          <h3 className="flex items-center gap-2 text-sm font-extrabold uppercase tracking-wide text-warn">
            <IconAlert size={16} /> Unestablished
          </h3>
          <ul className="ml-5 list-disc space-y-1 text-sm font-semibold text-ink">
            {card.unestablished.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>

        <p className="rounded-2xl bg-brand-soft p-4 text-sm">
          <strong className="text-brand-ink">Next useful check:</strong> {card.next_check}
        </p>

        <details className="rounded-2xl border border-line p-4">
          <summary className="cursor-pointer text-sm font-extrabold">The Skeptic's seven checks</summary>
          <ol className="mt-3 grid gap-2 md:grid-cols-2">
            {CHECKS.map((_, i) => (
              <CheckPill key={i} index={i} result={card.checks.find((c) => c.check === i + 1)} />
            ))}
          </ol>
        </details>
      </div>
      )}
      {openId && <EvidenceDrawer evidenceId={openId} onClose={() => setOpenId(null)} />}
    </article>
  )
}
