import { useRoute } from './hooks/useRoute'
import { AskPage } from './pages/AskPage'
import { CasePage } from './pages/CasePage'
import { PrivacyPage } from './pages/PrivacyPage'

const APP_NAME = import.meta.env.VITE_APP_NAME || 'Organizational Memory Auditor'

function NavLink({ href, current, children }: { href: string; current: boolean; children: string }) {
  return (
    <a
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold ${
        current
          ? 'bg-indigo-100 text-indigo-950 dark:bg-indigo-950 dark:text-indigo-100'
          : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
      }`}
    >
      {children}
    </a>
  )
}

function App() {
  const route = useRoute()
  return (
    <div className="min-h-svh bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <a href="#/" className="font-semibold">
            {APP_NAME}
          </a>
          <nav aria-label="Main" className="flex gap-1">
            <NavLink href="#/" current={route.page === 'ask' || route.page === 'case'}>
              Ask
            </NavLink>
            <NavLink href="#/privacy" current={route.page === 'privacy'}>
              Privacy console
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        {route.page === 'ask' && <AskPage key={route.prefill} prefill={route.prefill} />}
        {route.page === 'case' && <CasePage caseId={route.caseId} />}
        {route.page === 'privacy' && <PrivacyPage />}
      </main>
    </div>
  )
}

export default App
