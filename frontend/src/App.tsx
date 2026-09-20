import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import { IconAlert, IconCheck, IconChevronDown, IconUser } from './components/icons'
import { EuFlag, Logo, PageArt } from './components/Logo'
import { useRoute } from './hooks/useRoute'
import { CasePage } from './pages/CasePage'
import { AddEvidencePage } from './pages/AddEvidencePage'
import { HomePage } from './pages/HomePage'
import { PrivacyPage } from './pages/PrivacyPage'
import { RadarPage } from './pages/RadarPage'

const APP_NAME = import.meta.env.VITE_APP_NAME || 'Organizational Memory Auditor'

function NavLink({ href, current, children }: { href: string; current: boolean; children: string }) {
  return (
    <a
      href={href}
      aria-current={current ? 'page' : undefined}
      className={`inline-flex h-[29px] cursor-pointer items-center rounded-full px-[19px] text-[13px] font-semibold transition-colors duration-200 ${
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
      className={`hidden h-[25px] items-center gap-1.5 rounded-full border px-[11px] text-[10.5px] font-semibold lg:inline-flex ${
        err ? 'border-bad/30 bg-bad-soft text-bad' : 'border-[#bfe4d2] bg-[#f0faf5] text-ok'
      }`}
      title={ok ? `${stats.data.documents} documents · ${stats.data.evidence_units} evidence units` : undefined}
    >
      {err ? (
        <IconAlert size={14} />
      ) : (
        <span className="grid size-[14px] place-items-center rounded-full border-[1.5px] border-current">
          <IconCheck size={8} strokeWidth={4} />
        </span>
      )}
      {ok ? 'Archive ready' : err ? 'Archive unavailable' : 'Connecting…'}
    </span>
  )
}

function PrivacyBadge() {
  return (
    <span className="hidden items-center gap-2 text-[10px] font-medium text-ink-2 xl:inline-flex">
      <EuFlag width={20} />
      EU privacy controls
    </span>
  )
}

function AccountMenu() {
  return (
    <button
      type="button"
      title="Signed in as reviewer"
      className="flex cursor-pointer items-center gap-1.5 rounded-full transition-opacity duration-200 hover:opacity-80"
    >
      <span className="grid size-[26px] place-items-center rounded-full bg-gradient-to-br from-[#f2c9b0] to-[#d99a7e] text-white">
        <IconUser size={15} />
      </span>
      <IconChevronDown size={14} className="hidden text-ink-3 sm:block" />
    </button>
  )
}

const NAV = [
  { href: '#/', label: 'Ask', pages: ['ask', 'case'] },
  { href: '#/radar', label: 'Radar', pages: ['radar'] },
  { href: '#/add-evidence', label: 'Add Evidence', pages: ['evidence'] },
  { href: '#/privacy', label: 'Privacy', pages: ['privacy'] },
]

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
      <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-[52px] max-w-[1208px] items-center justify-between gap-3 px-4">
          <a href="#/" className="flex cursor-pointer items-center gap-3" aria-label={`${APP_NAME} home`}>
            <Logo size={26} />
            <span className="leading-tight">
              <span className="block text-[13.5px] font-bold tracking-tight text-ink">{APP_NAME}</span>
              <span className="hidden text-[11px] font-medium text-ink-3 sm:block">Every answer, with a receipt</span>
            </span>
          </a>
          <nav aria-label="Main" className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-0.5 sm:flex">
            {NAV.map((n) => (
              <NavLink key={n.href} href={n.href} current={n.pages.includes(route.page)}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-4">
            <ArchiveStatus />
            <PrivacyBadge />
            <AccountMenu />
          </div>
        </div>
        <nav aria-label="Main" className="flex items-center justify-center gap-0.5 border-t border-line py-1.5 sm:hidden">
          {NAV.map((n) => (
            <NavLink key={n.href} href={n.href} current={n.pages.includes(route.page)}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main id="main" className="relative isolate flex-1">
        <PageArt />
        {route.page === 'ask' && <HomePage key={route.prefill} prefill={route.prefill} />}
        {route.page === 'case' && <CasePage caseId={route.caseId} />}
        {route.page === 'privacy' && <PrivacyPage />}
        {route.page === 'radar' && <RadarPage />}
        {route.page === 'evidence' && <AddEvidencePage />}
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
