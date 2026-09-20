import type { ReactNode } from 'react'
import type { CaseStatus } from '../types/api'
import { IconAlert, IconApprox, IconCheckCircle, IconHelp } from './icons'

// Verdict styling: colour is never the only signal (icon and words too).
export const STATUS: Record<
  CaseStatus,
  { label: string; blurb: string; tone: string; band: string; icon: ReactNode }
> = {
  SUPPORTED: {
    label: 'Supported',
    blurb: 'The evidence backs this answer.',
    tone: 'border-[#b9e2cf] bg-[#eaf8f1] text-[#177049]',
    band: 'from-ok/25',
    icon: <IconCheckCircle size={13} />,
  },
  PARTIALLY_SUPPORTED: {
    label: 'Partially supported',
    blurb: 'Some of this is backed; some is not established.',
    tone: 'border-[#f4d9b0] bg-[#fdf3e2] text-[#a25f0c]',
    band: 'from-warn/25',
    icon: <IconApprox size={13} />,
  },
  CONFLICTING_EVIDENCE: {
    label: 'Conflicting evidence',
    blurb: 'The archive disagrees with itself. Read how it was weighed.',
    tone: 'border-[#f2c6c3] bg-[#fdeeed] text-[#b5382d]',
    band: 'from-bad/25',
    icon: <IconAlert size={13} />,
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    blurb: 'The archive does not settle this.',
    tone: 'border-[#c4dcf3] bg-[#eaf3fc] text-[#1c5f9c]',
    band: 'from-ink-3/25',
    icon: <IconHelp size={13} />,
  },
}
