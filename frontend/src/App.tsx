const APP_NAME = import.meta.env.VITE_APP_NAME || 'Organizational Memory Auditor'

function App() {
  return (
    <div className="mx-auto flex min-h-svh max-w-3xl flex-col items-center justify-center gap-2 px-4 text-center">
      <h1 className="text-3xl font-medium">{APP_NAME}</h1>
      <p className="text-gray-500">Evidence-first organizational memory auditor.</p>
      <p className="text-sm text-gray-400">Backend, ingestion, and Case UI land in later build phases.</p>
    </div>
  )
}

export default App
