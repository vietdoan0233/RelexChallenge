import type { ReactNode } from 'react'
import type { CaseStatus } from '../types/api'
import { IconAlert, IconEye, IconScale, IconShield } from './icons'

// Verdict styling: colour is never the only signal (icon and words too).
export const STATUS: Record<
  CaseStatus,
  { label: string; blurb: string; tone: string; band: string; icon: ReactNode }
> = {
  SUPPORTED: {
    label: 'Supported',
    blurb: 'The evidence backs this answer.',
    tone: 'bg-ok-soft text-ok',
    band: 'from-ok/25',
    icon: <IconShield size={18} />,
  },
  PARTIALLY_SUPPORTED: {
    label: 'Partially supported',
    blurb: 'Some of this is backed; some is not established.',
    tone: 'bg-warn-soft text-warn',
    band: 'from-warn/25',
    icon: <IconScale size={18} />,
  },
  CONFLICTING_EVIDENCE: {
    label: 'Conflicting evidence',
    blurb: 'The archive disagrees with itself. Read how it was weighed.',
    tone: 'bg-bad-soft text-bad',
    band: 'from-bad/25',
    icon: <IconAlert size={18} />,
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    blurb: 'The archive does not settle this.',
    tone: 'bg-neutral-soft text-ink-2',
    band: 'from-ink-3/25',
    icon: <IconEye size={18} />,
  },
}

