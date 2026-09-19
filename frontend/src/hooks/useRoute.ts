import { useEffect, useState } from 'react'

// A tiny hash router: three pages do not justify a routing dependency, and a
// hash URL keeps a Case link shareable without any server configuration.
export type Route =
  | { page: 'ask'; prefill?: string }
  | { page: 'case'; caseId: string }
  | { page: 'privacy' }
  | { page: 'radar' }

function parse(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?')
  const parts = path.split('/').filter(Boolean)
  if (parts[0] === 'case' && parts[1]) return { page: 'case', caseId: parts[1] }
  if (parts[0] === 'privacy') return { page: 'privacy' }
  if (parts[0] === 'radar') return { page: 'radar' }
  return { page: 'ask', prefill: new URLSearchParams(query).get('q') ?? undefined }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const go = {
  ask: (prefill?: string) => {
    window.location.hash = prefill ? `#/?q=${encodeURIComponent(prefill)}` : '#/'
  },
  caseView: (caseId: string) => {
    window.location.hash = `#/case/${caseId}`
  },
  privacy: () => {
    window.location.hash = '#/privacy'
  },
}
