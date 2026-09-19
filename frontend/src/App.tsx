import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import { IconRadar, IconSearch, IconShield } from './components/icons'
import { Logo } from './components/Logo'
import { useRoute } from './hooks/useRoute'
import { CasePage } from './pages/CasePage'
import { HomePage } from './pages/HomePage'
import { PrivacyPage } from './pages/PrivacyPage'
import { RadarPage } from './pages/RadarPage'

const APP_NAME = import.meta.env.VITE_APP_NAME || 'Organizational Memory Auditor'

function NavLink({
  href,
  current,
  icon,
  children,
}: {
  href: string
  current: boolean
  icon: React.ReactNode
  children: string
}) {
  return (
    <a
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full px-4 text-sm font-bold transition-colors duration-200 ${
        current ? 'bg-brand text-white shadow-card' : 'text-ink-2 hover:bg-brand-soft hover:text-ink'
      }`}
    >
      {icon}
      <span className="hidden sm:inline">{children}</span>
      <span className="sr-only sm:hidden">{children}</span>
    </a>
  )
}

function ArchiveStatus() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, retry: false })
  const ok = stats.isSuccess
  return (
    <span
      className="hidden items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink-2 lg:inline-flex"
      title={ok ? `${stats.data.documents} documents · ${stats.data.evidence_units} evidence units` : undefined}
    >
      <span className="relative flex size-2.5">
        {ok && <span className="anim-ring absolute inline-flex size-full rounded-full bg-ok opacity-60" />}
        <span className={`relative inline-flex size-2.5 rounded-full ${ok ? 'bg-ok' : 'bg-ink-3'}`} />
      </span>
      {ok ? 'Archive ready' : stats.isError ? 'Archive unavailable' : 'Connecting…'}
    </span>
  )
}

function App() {
  const route = useRoute()
  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-brand focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
          <a href="#/" className="flex min-h-11 cursor-pointer items-center gap-3" aria-label={`${APP_NAME} home`}>
            <Logo size={34} />
            <span className="leading-tight">
              <span className="block text-base font-extrabold tracking-tight text-ink">{APP_NAME}</span>
              <span className="hidden text-xs font-semibold text-ink-3 sm:block">Every answer, with a receipt</span>
            </span>
          </a>
          <div className="flex items-center gap-2">
            <ArchiveStatus />
            <nav aria-label="Main" className="flex items-center gap-1">
              <NavLink href="#/" current={route.page === 'ask' || route.page === 'case'} icon={<IconSearch size={18} />}>
                Ask
              </NavLink>
              <NavLink href="#/radar" current={route.page === 'radar'} icon={<IconRadar size={18} />}>
                Radar
              </NavLink>
              <NavLink href="#/privacy" current={route.page === 'privacy'} icon={<IconShield size={18} />}>
                Privacy
              </NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        {route.page === 'ask' && <HomePage key={route.prefill} prefill={route.prefill} />}
        {route.page === 'case' && <CasePage caseId={route.caseId} />}
        {route.page === 'privacy' && <PrivacyPage />}
        {route.page === 'radar' && <RadarPage />}
      </main>

      <footer className="no-print border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-ink-3">
          <span className="font-semibold">
            Answers come only from the archive and are validated against it. Open a source to check any claim.
          </span>
          <span>Plan better. Sell more. Waste less.</span>
        </div>
      </footer>
    </div>
  )
}

export default App
