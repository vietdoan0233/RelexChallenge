import type { ReactNode } from 'react'
import type { CaseStatus, Confidence, Stance } from '../types/api'

const STATUS: Record<CaseStatus, { label: string; cls: string }> = {
  SUPPORTED: {
    label: 'Supported',
    cls: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  },
  PARTIALLY_SUPPORTED: {
    label: 'Partially supported',
    cls: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  },
  CONFLICTING_EVIDENCE: {
    label: 'Conflicting evidence',
    cls: 'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200',
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    cls: 'bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200',
  },
}

export function StatusBadge({ status }: { status: CaseStatus }) {
  const s = STATUS[status]
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${s.cls}`}>
      {s.label}
    </span>
  )
}

const pretty = (v: string) => v.replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())

export function StanceChip({ stance }: { stance: Stance }) {
  return (
    <span className="rounded border border-zinc-300 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:text-zinc-300">
      {pretty(stance)}
    </span>
  )
}

export function ConfidenceChip({ confidence }: { confidence: Confidence }) {
  const cls =
    confidence === 'HIGH'
      ? 'text-emerald-800 dark:text-emerald-300'
      : confidence === 'MEDIUM'
        ? 'text-amber-800 dark:text-amber-300'
        : 'text-rose-800 dark:text-rose-300'
  return <span className={`text-xs font-semibold ${cls}`}>{pretty(confidence)} confidence</span>
}

export function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
        {hint && <p className="text-sm text-zinc-600 dark:text-zinc-400">{hint}</p>}
      </div>
      {children}
    </section>
  )
}
