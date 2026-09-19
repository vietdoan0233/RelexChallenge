import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { CaseView } from '../components/case/CaseView'
import { btnSecondary } from '../lib'
import { go } from '../hooks/useRoute'

export function CasePage({ caseId }: { caseId: string }) {
  const query = useQuery({ queryKey: ['case', caseId], queryFn: () => api.getCase(caseId) })
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <button type="button" className={btnSecondary} onClick={() => go.ask()}>
        ← Ask another question
      </button>
      {query.isPending && <p role="status">Loading Case…</p>}
      {query.isError && (
        <p role="alert" className="rounded-lg bg-rose-50 p-3 text-rose-900 dark:bg-rose-950 dark:text-rose-100">
          {query.error.message} This Case may have been removed.
        </p>
      )}
      {query.data && <CaseView receipt={query.data} onAsk={go.ask} />}
    </div>
  )
}
