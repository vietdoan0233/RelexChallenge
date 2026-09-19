import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { go } from '../hooks/useRoute'
import { readRecent, rememberQuestion } from '../hooks/useRecentQuestions'
import { btnPrimary, btnSecondary } from '../lib'

const EXAMPLES = [
  'What service levels were agreed for ordering, and in which meeting?',
  'Did Acme sign off UAT for the programme, and what was the scope?',
  'Is bakery inside the fresh workstream? Show how the answer changed over time.',
  'The weekly reports say the nightly extract completed with no errors. Is that true?',
]

// Coarse progress, not streaming: a high-risk question makes several model calls.
const STAGES = ['Analyzing evidence', 'Checking for contradictions', 'Reconciling current state']

export function AskPage({ prefill }: { prefill?: string }) {
  const [question, setQuestion] = useState(prefill ?? '')
  const [stage, setStage] = useState(0)
  const [recent] = useState(readRecent)

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(q),
    onSuccess: (receipt, q) => {
      rememberQuestion(q)
      go.caseView(receipt.case_id)
    },
  })

  useEffect(() => {
    if (!ask.isPending) return
    const timer = window.setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 9000)
    return () => window.clearInterval(timer)
  }, [ask.isPending])

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 3 || ask.isPending) return
    setStage(0)
    ask.mutate(trimmed)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div className="space-y-2 pt-6">
        <h1 className="text-3xl font-semibold text-zinc-900 dark:text-zinc-100">
          Ask the archive, with a receipt
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Every answer is a Case: a conclusion, the exact sources behind it, the evidence that
          disagrees, and what remains uncertain.
        </p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          submit(question)
        }}
        className="space-y-3"
      >
        <label htmlFor="question" className="block text-sm font-semibold">
          Your question
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          maxLength={1000}
          placeholder="What was decided about…?"
          className="w-full rounded-lg border border-zinc-300 bg-white p-3 text-base focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button type="submit" className={btnPrimary} disabled={ask.isPending || question.trim().length < 3}>
          {ask.isPending ? 'Investigating…' : 'Open a Case'}
        </button>
      </form>

      {ask.isPending && (
        <p role="status" className="rounded-lg bg-indigo-50 p-3 text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100">
          {STAGES[stage]}… decision and current-state questions are checked for contradictions,
          which takes a little longer.
        </p>
      )}
      {ask.isError && (
        <p role="alert" className="rounded-lg bg-rose-50 p-3 text-rose-900 dark:bg-rose-950 dark:text-rose-100">
          {ask.error.message}
        </p>
      )}

      <div className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-400">
          Try one
        </h2>
        <div className="flex flex-col gap-2">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className={`${btnSecondary} justify-start py-2 text-left`} onClick={() => setQuestion(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>

      {recent.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-400">
            Recently asked
          </h2>
          <ul className="space-y-1">
            {recent.map((q) => (
              <li key={q}>
                <button type="button" className="text-left text-indigo-800 underline dark:text-indigo-300" onClick={() => setQuestion(q)}>
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
