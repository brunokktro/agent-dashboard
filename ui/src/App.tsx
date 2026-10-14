import { useAppApi } from '@kirocrew/app-sdk'
import { Card, CardTitle, PageHeader } from '@kirocrew/app-sdk/ui'
import { resolveAppHost } from './appHost'
import { useEffect, useState } from 'react'

/**
 * Thin shell wrapper (format A): the real dashboard is the SPA served by the
 * app's own FastAPI backend. Embedding it as a same-origin iframe keeps the
 * WebSocket terminals, SSE log streams and xterm sessions working - the
 * KiroCrew proxy is HTTP-only and cannot upgrade WebSocket connections.
 *
 * The backend port is dynamic (KiroCrew assigns it at spawn), so we discover
 * it through the proxied /api/apphost endpoint, which reports the effective port.
 */
export default function AgentDashboard() {
  const api = useAppApi()
  const [port, setPort] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)

    // KiroCrew may mount this wrapper before an updated backend has registered
    // its dynamic port. Retry that expected startup race, but fail visibly if
    // the backend is still unavailable after the bounded window.
    resolveAppHost(() => api.get('/apps/agent-dashboard/api/apphost'))
      .then((host) => {
        if (!cancelled) setPort(host.port)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })

    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error) {
    return (
      <>
        <PageHeader title="Agent Dashboard" subtitle="Local-first observability for your agent fleet" />
        <div className="px-6 pb-8">
          <Card>
            <CardTitle>Backend not reachable</CardTitle>
            <p className="text-sm text-muted">
              The dashboard backend did not answer its health check yet: {error}
            </p>
            <p className="text-sm text-muted">
              If this is the first start, the frontend may still be building
              (onEnable runs npm install + build once). Check the app logs and reload.
            </p>
          </Card>
        </div>
      </>
    )
  }

  if (port === null) {
    return (
      <>
        <PageHeader title="Agent Dashboard" subtitle="Connecting to the dashboard backend..." />
      </>
    )
  }

  return (
    <iframe
      src={`http://127.0.0.1:${port}/`}
      title="Agent Dashboard"
      className="h-full w-full flex-1 border-0"
      style={{ minHeight: 0 }}
    />
  )
}
