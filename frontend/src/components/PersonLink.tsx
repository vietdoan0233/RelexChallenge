import { go } from '../hooks/useRoute'

/** A speaker/sender/mention name, made clickable to that participant's
 * universal profile (CLAUDE.md 19.D) when a subject_id is known. Renders as
 * a <span>, not a <button>: every call site here sits inside an
 * already-clickable citation card (opening the evidence drawer), and a
 * nested <button> inside a <button> is invalid HTML with unpredictable
 * click-bubbling. role="link" plus a keyboard handler keeps it operable
 * without that nesting. Renders as plain text when no subject resolved
 * (an anonymous label like "Me"/"Them", or free text that never matched a
 * known participant). */
export function PersonLink({
  subjectId,
  name,
  className = '',
}: {
  subjectId: string | null | undefined
  name: string
  className?: string
}) {
  if (!subjectId) return <>{name}</>
  return (
    <span
      role="link"
      tabIndex={0}
      onClick={(event) => {
        event.stopPropagation()
        go.person(subjectId)
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        event.stopPropagation()
        go.person(subjectId)
      }}
      className={`cursor-pointer underline decoration-dotted underline-offset-2 hover:text-brand-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand ${className}`}
    >
      {name}
    </span>
  )
}
