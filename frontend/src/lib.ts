// Shared non-component helpers (kept out of component files so fast refresh works).
export const formatDate = (date: string | null) => {
  if (!date) return 'Undated'
  const d = new Date(date)
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export const formatMonth = (date: string | null) => {
  if (!date) return ''
  const d = new Date(date)
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' })
}

export const timeAgo = (iso: string) => {
  const seconds = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

// Buttons follow RELEX's pill shape. 44px minimum touch height.
const base =
  'inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50'
export const btn = base
export const btnPrimary = `${base} bg-brand text-white shadow-card hover:bg-brand-strong hover:shadow-lift`
export const btnSecondary = `${base} border border-line bg-surface text-ink hover:border-brand hover:bg-brand-soft`
export const btnGhost = `${base} text-brand-ink hover:bg-brand-soft`
export const btnDanger = `${base} bg-bad text-white hover:opacity-90`

export const card = 'rounded-[10px] border border-line bg-surface shadow-card'
