import type { RadarAssessment } from '../../types/api'
import { IconApprox, IconBlock, IconCheckCircle, IconHelp } from '../icons'

// The Radar may say only these four things, and never that an idea should be pursued.
// `tone` colours a status pill; `chip` colours the summary count on the Radar page.
export const ASSESSMENT: Record<
  RadarAssessment,
  { label: string; meaning: string; tone: string; chip: string; ink: string; icon: React.ReactNode }
> = {
  STILL_BLOCKED: {
    label: 'Still blocked',
    meaning: 'Original constraints still appear to apply.',
    tone: 'border-[#f2c6c3] bg-[#fdeeed] text-[#c0392b]',
    chip: 'border-[#f2c6c3] bg-[#fdeeed] text-[#b5382d]',
    ink: 'text-[#d64545]',
    icon: <IconBlock size={15} />,
  },
  PARTIALLY_CHANGED: {
    label: 'Partially changed',
    meaning: 'Some conditions have changed, further review needed.',
    tone: 'border-[#f4d9b0] bg-[#fdf3e2] text-[#b16a12]',
    chip: 'border-[#f4d9b0] bg-[#fdf3e2] text-[#a25f0c]',
    ink: 'text-[#e09a2e]',
    icon: <IconApprox size={15} />,
  },
  WORTH_REASSESSING: {
    label: 'Worth reassessing',
    meaning: 'Strong signs the original blocker may have changed.',
    tone: 'border-[#b9e2cf] bg-[#eaf8f1] text-[#1a7a55]',
    chip: 'border-[#b9e2cf] bg-[#eaf8f1] text-[#177049]',
    ink: 'text-[#22a06b]',
    icon: <IconCheckCircle size={15} />,
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    meaning: 'Not enough information yet to assess.',
    tone: 'border-[#c4dcf3] bg-[#eaf3fc] text-[#1c5f9c]',
    chip: 'border-[#c4dcf3] bg-[#eaf3fc] text-[#1c5f9c]',
    ink: 'text-[#2f7fc4]',
    icon: <IconHelp size={15} />,
  },
}
