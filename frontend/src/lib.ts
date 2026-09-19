// Shared non-component helpers (kept out of ui.tsx so fast refresh keeps working).
export const formatDate = (date: string | null) => {
  if (!date) return 'Undated'
  const d = new Date(date)
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export const btn =
  'inline-flex min-h-11 items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50'
export const btnPrimary = `${btn} bg-indigo-700 text-white hover:bg-indigo-800`
export const btnSecondary = `${btn} border border-zinc-300 bg-white text-zinc-900 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800`
export const btnDanger = `${btn} bg-rose-700 text-white hover:bg-rose-800`
