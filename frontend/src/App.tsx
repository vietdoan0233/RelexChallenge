import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import { IconAlert, IconCheck, IconChevronDown, IconFlag, IconUser } from './components/icons'
import { Logo } from './components/Logo'
import { useRoute } from './hooks/useRoute'
import { CasePage } from './pages/CasePage'
import { HomePage } from './pages/HomePage'
import { PrivacyPage } from './pages/PrivacyPage'
import { RadarPage } from './pages/RadarPage'

const APP_NAME = import.meta.env.VITE_APP_NAME || 'Organizational Memory Auditor'

function NavLink({ href, current, children }: { href: string; current: boolean; children: string }) {
  return (
    <a
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`inline-flex min-h-9 cursor-pointer items-center rounded-full px-4 text-sm font-bold transition-colors duration-200 ${
        current ? 'bg-brand-soft text-brand-ink' : 'text-ink-2 hover:text-ink'
      }`}
    >
      {children}
    </a>
  )
}

function ArchiveStatus() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, retry: false })
  const ok = stats.isSuccess
  const err = stats.isError
  return (
    <span
      className={`hidden items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold lg:inline-flex ${
        err ? 'border-bad/30 bg-bad-soft text-bad' : 'border-ok/30 bg-ok-soft text-ok'
      }`}
      title={ok ? `${stats.data.documents} documents · ${stats.data.evidence_units} evidence units` : undefined}
    >
      {err ? <IconAlert size={14} /> : <IconCheck size={14} strokeWidth={3} />}
      {ok ? 'Archive ready' : err ? 'Archive unavailable' : 'Connecting…'}
    </span>
  )
}

function PrivacyBadge() {
  return (
    <span className="hidden items-center gap-1.5 rounded-full border border-brand/20 bg-brand-soft px-3 py-1.5 text-xs font-bold text-brand-ink md:inline-flex">
      <IconFlag size={14} />
      EU privacy controls
    </span>
  )
}

function AccountMenu() {
  return (
    <button
      type="button"
      title="Signed in as reviewer"
      className="flex cursor-pointer items-center gap-1 rounded-full py-1 pl-1 pr-1.5 transition-colors duration-200 hover:bg-surface-2"
    >
      <span className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-brand-soft to-purple-soft text-brand-ink">
        <IconUser size={18} />
      </span>
      <IconChevronDown size={16} className="hidden text-ink-3 sm:block" />
    </button>
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
            <Logo size={30} />
            <span className="leading-tight">
              <span className="block text-base font-extrabold tracking-tight text-ink">{APP_NAME}</span>
              <span className="hidden text-xs font-semibold text-ink-3 sm:block">Every answer, with a receipt</span>
            </span>
          </a>
          <nav aria-label="Main" className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-1 sm:flex">
            <NavLink href="#/" current={route.page === 'ask' || route.page === 'case'}>
              Ask
            </NavLink>
            <NavLink href="#/radar" current={route.page === 'radar'}>
              Radar
            </NavLink>
            <NavLink href="#/privacy" current={route.page === 'privacy'}>
              Privacy
            </NavLink>
          </nav>
          <div className="flex items-center gap-2">
            <ArchiveStatus />
            <PrivacyBadge />
            <AccountMenu />
          </div>
        </div>
        <nav aria-label="Main" className="flex items-center justify-center gap-1 border-t border-line py-1.5 sm:hidden">
          <NavLink href="#/" current={route.page === 'ask' || route.page === 'case'}>
            Ask
          </NavLink>
          <NavLink href="#/radar" current={route.page === 'radar'}>
            Radar
          </NavLink>
          <NavLink href="#/privacy" current={route.page === 'privacy'}>
            Privacy
          </NavLink>
        </nav>
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
