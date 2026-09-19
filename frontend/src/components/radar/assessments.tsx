import type { RadarAssessment } from '../../types/api'
import { IconEye, IconLock, IconRadar, IconScale } from '../icons'

// The Radar may say only these four things, and never that an idea should be pursued.
export const ASSESSMENT: Record<RadarAssessment, { label: string; meaning: string; tone: string; icon: React.ReactNode }> = {
  STILL_BLOCKED: {
    label: 'Still blocked',
    meaning: 'The reason for saying no appears to remain.',
    tone: 'bg-neutral-soft text-ink',
    icon: <IconLock size={16} />,
  },
  PARTIALLY_CHANGED: {
    label: 'Partially changed',
    meaning: 'Something relevant changed, but it does not clearly remove the blocker.',
    tone: 'bg-warn-soft text-warn',
    icon: <IconScale size={16} />,
  },
  WORTH_REASSESSING: {
    label: 'Worth reassessing',
    meaning: 'The blocker may have changed enough for a human to look again.',
    tone: 'bg-purple-soft text-purple',
    icon: <IconRadar size={16} />,
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    meaning: 'The archive cannot tell whether the blocker has changed.',
    tone: 'bg-neutral-soft text-ink-2',
    icon: <IconEye size={16} />,
  },
}

