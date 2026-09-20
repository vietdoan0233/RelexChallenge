import type { ReactNode } from 'react'
import type { CaseStatus, Confidence, Stance } from '../types/api'
import { IconCheck } from './icons'
import { STATUS } from './statusMap'

export function StatusBadge({ status, large }: { status: CaseStatus; large?: boolean }) {
  const s = STATUS[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-bold uppercase tracking-wide ${s.tone} ${
        large ? 'h-8 px-4 text-xs' : 'h-6 px-3 text-[10px]'
      }`}
    >
      {s.icon}
      {s.label}
    </span>
  )
}

const STANCE_TONE: Record<Stance, string> = {
  PROPOSAL: 'bg-purple-soft text-purple',
  ASSUMPTION: 'bg-neutral-soft text-ink-2',
  OBJECTION: 'bg-bad-soft text-bad',
  AGREEMENT: 'bg-ok-soft text-ok',
  COMMITMENT: 'bg-ok-soft text-ok',
  STATUS_UPDATE: 'bg-brand-soft text-brand-ink',
  IMPLEMENTATION_EVIDENCE: 'bg-brand-soft text-brand-ink',
  SUPERSEDED: 'bg-orange-soft text-orange',
  UNCERTAIN: 'bg-warn-soft text-warn',
}
const pretty = (v: string) => v.replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())

export function StanceChip({ stance }: { stance: Stance }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${STANCE_TONE[stance]}`}>
      {pretty(stance)}
    </span>
  )
}

/** Three bars plus words: readable at a glance and without colour. */
export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const level = confidence === 'HIGH' ? 3 : confidence === 'MEDIUM' ? 2 : 1
  const tone = level === 3 ? 'bg-ok' : level === 2 ? 'bg-warn' : 'bg-bad'
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-ink-2">
      <span className="flex gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <span key={n} className={`h-2.5 w-1 rounded-sm ${n <= level ? tone : 'bg-line'}`} />
        ))}
      </span>
      {pretty(confidence)} confidence
    </span>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-brand-ink">{children}</p>
}

export function Section({
  id,
  title,
  hint,
  icon,
  children,
}: {
  id?: string
  title: string
  hint?: string
  icon?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <div className="flex items-start gap-3">
        {icon && (
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">
            {icon}
          </span>
        )}
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-ink">{title}</h2>
          {hint && <p className="text-sm text-ink-2">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />
}

export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <span
      className="anim-spin-fast inline-block rounded-full border-2 border-current border-t-transparent"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

export function Tick({ size = 18 }: { size?: number }) {
  return (
    <span className="inline-grid place-items-center rounded-full bg-ok text-white" style={{ width: size, height: size }}>
      <IconCheck size={size - 6} strokeWidth={3.5} className="anim-draw" />
    </span>
  )
}
