import { useEffect, useState } from 'react'
import { Logo } from './Logo'
import { Skeleton, Spinner, Tick } from './ui'

// What the system is genuinely doing, in the order it does it. The phase moves on
// a timer because the server does not stream progress, so the wording stays honest:
// it names the stage, and only claims "almost there" late in the wait.
const PHASES = [
  {
    title: 'Reading the archive',
    detail: 'Finding the passages that matter, in every meeting, email and report.',
    messages: [
      'Tinkering with the evidence',
      'Pulling on the threads',
      'Reading between the timestamps',
      'Gathering the relevant turns',
      'Lining up the sources',
    ],
  },
  {
    title: 'Challenging the answer',
    detail: 'Searching for anything that contradicts it, in different words.',
    messages: [
      "Playing devil's advocate",
      'Hunting for the catch',
      'Asking who disagreed',
      'Checking what changed later',
      'Looking at the other side of the story',
    ],
  },
  {
    title: 'Checking every citation',
    detail: 'Reconciling what was found and verifying each source is real.',
    messages: [
      'Almost there',
      "Weighing what's current",
      'Double-checking every citation',
      'Putting the receipt together',
      'Just a moment more',
    ],
  },
] as const

const PHASE_STARTS = [0, 9, 20] // seconds
const ROTATE_MS = 2600

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export function Thinking({ question }: { question: string }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const start = Date.now()
    const t = window.setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500)
    return () => window.clearInterval(t)
  }, [])

  const phase = PHASE_STARTS.filter((s) => elapsed >= s).length - 1
  const { messages } = PHASES[phase]
  const tick = Math.floor((elapsed * 1000) / ROTATE_MS)
  const message = messages[tick % messages.length]

  return (
    <div className="mx-auto max-w-3xl space-y-8 py-10">
      <div className="anim-fade-up space-y-2 text-center">
        <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-brand-ink">Opening a Case</p>
        <h1 className="text-balance text-2xl font-extrabold tracking-tight sm:text-3xl">{question}</h1>
      </div>

      <div className="anim-fade-up rounded-3xl border border-line bg-surface p-8 shadow-lift">
        <div className="flex flex-col items-center gap-6 text-center">
          {/* Orbit: purely decorative, and stopped for reduced-motion users. */}
          <div className="relative size-32" aria-hidden="true">
            <span className="anim-ring absolute inset-4 rounded-full border-2 border-brand/50" />
            <span className="anim-spin-slow absolute inset-0 rounded-full border-2 border-dashed border-brand/40">
              <span className="absolute -top-1.5 left-1/2 size-3 -translate-x-1/2 rounded-full bg-brand" />
            </span>
            <span className="anim-spin-mid absolute inset-3 rounded-full border-2 border-purple/40">
              <span className="absolute -bottom-1.5 left-1/2 size-3 -translate-x-1/2 rounded-full bg-purple" />
            </span>
            <span className="absolute inset-0 grid place-items-center">
              <Logo size={44} />
            </span>
          </div>

          {/* Announced to screen readers once per phase; the rotating line is decorative. */}
          <div role="status" aria-live="polite" className="sr-only">
            {PHASES[phase].title}
          </div>
          <div className="min-h-16 space-y-1">
            <p key={message} className="anim-swap shimmer-text text-2xl font-extrabold" aria-hidden="true">
              {message}
              <span className="ml-0.5 inline-block w-6 text-left">
                {'.'.repeat((Math.floor(elapsed * 2) % 3) + 1)}
              </span>
            </p>
            <p className="text-sm text-ink-2">{PHASES[phase].detail}</p>
          </div>

          <ol className="grid w-full max-w-md gap-2 text-left" aria-label="Progress">
            {PHASES.map((p, i) => (
              <li
                key={p.title}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition-colors duration-300 ${
                  i === phase ? 'bg-brand-soft text-ink' : i < phase ? 'text-ink-2' : 'text-ink-3'
                }`}
                aria-current={i === phase ? 'step' : undefined}
              >
                <span className="grid size-5 place-items-center">
                  {i < phase ? <Tick size={20} /> : i === phase ? <Spinner size={18} /> : <span className="size-2 rounded-full bg-line" />}
                </span>
                {p.title}
              </li>
            ))}
          </ol>

          <p className="text-xs font-semibold tabular-nums text-ink-3">
            {clock(elapsed)} elapsed
            {elapsed >= 30 && ' · big questions get a second look, thanks for your patience'}
          </p>
        </div>
      </div>

      {/* A preview of the shape of the answer, so the wait feels like progress. */}
      <div className="space-y-3 opacity-80" aria-hidden="true">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-4/5" />
        <div className="grid gap-3 pt-2 sm:grid-cols-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      </div>
    </div>
  )
}
