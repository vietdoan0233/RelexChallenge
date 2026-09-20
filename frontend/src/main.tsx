import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

const queryClient = new QueryClient()

// index.html ships a static ENGRAM fallback title; override it here when
// VITE_APP_NAME is configured, so renaming the app never requires a code change.
if (import.meta.env.VITE_APP_NAME) {
  document.title = import.meta.env.VITE_APP_NAME
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
