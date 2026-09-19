const KEY = 'recent-questions'
const MAX = 6

// A per-viewer convenience only. localStorage can be blocked or empty, so every
// access is guarded and the page works without it. Cleared after a privacy
// operation so a removed person's name cannot linger in this browser.
export function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((q): q is string => typeof q === 'string') : []
  } catch {
    return []
  }
}

export function rememberQuestion(query: string): void {
  try {
    const next = [query, ...readRecent().filter((q) => q !== query)].slice(0, MAX)
    window.localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable: nothing to do */
  }
}

export function clearRecent(): void {
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* storage unavailable: nothing to do */
  }
}
