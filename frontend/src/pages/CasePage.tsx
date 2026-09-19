import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { CaseView } from '../components/case/CaseView'
import { IconAlert } from '../components/icons'
import { Skeleton } from '../components/ui'
import { btnPrimary } from '../lib'
import { go } from '../hooks/useRoute'

export function CasePage({ caseId }: { caseId: string }) {
  const query = useQuery({ queryKey: ['case', caseId], queryFn: () => api.getCase(caseId) })
  if (query.data) return <CaseView receipt={query.data} onAsk={go.ask} />
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      {query.isPending && (
        <div role="status" aria-label="Loading Case" className="space-y-4">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}
      {query.isError && (
        <div role="alert" className="space-y-4 rounded-3xl border border-line bg-surface p-8 text-center shadow-card">
          <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-neutral-soft text-ink-2">
            <IconAlert size={28} />
          </span>
          <h1 className="text-2xl font-extrabold">This Case is gone</h1>
          <p className="text-ink-2">{query.error.message} It may have been removed with the evidence it depended on.</p>
          <a href="#/" className={btnPrimary}>
            Ask it again
          </a>
        </div>
      )}
    </div>
  )
}
