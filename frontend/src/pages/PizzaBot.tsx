import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink, Inbox, Loader2, Pizza, RefreshCw, TriangleAlert } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

export default function PizzaBotPage() {
  const { data, error, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["pizza"],
    queryFn: api.pizza,
    refetchInterval: 10_000,
  })

  const available = data?.available === true
  const url = data?.web_url ?? "http://127.0.0.1:7782"
  const frameRef = useRef<HTMLIFrameElement>(null)
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  )

  useEffect(() => {
    const root = document.documentElement
    const observer = new MutationObserver(() =>
      setTheme(root.classList.contains("dark") ? "dark" : "light"),
    )
    observer.observe(root, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const origin = new URL(url).origin
    const sendTheme = () =>
      frameRef.current?.contentWindow?.postMessage(
        { type: "agent-dashboard-theme", theme },
        origin,
      )
    sendTheme()
    const onMessage = (event: MessageEvent) => {
      if (event.origin === origin && event.data?.type === "pizza-theme-ready") sendTheme()
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [theme, url])

  return (
    <div className="flex min-h-[calc(100vh-5.5rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <div className="flex items-center gap-2">
          <Pizza className="size-5" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold">Pizza Bot Inbox</h1>
            <p className="text-xs text-muted-foreground">
              Long-running work, unread results and actions waiting for your decision.
            </p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-medium ${
              available ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"
            }`}
          >
            {isLoading || isFetching ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : available ? (
              <Inbox className="size-3.5" aria-hidden />
            ) : (
              <TriangleAlert className="size-3.5" aria-hidden />
            )}
            {isLoading ? "checking" : available ? "ready" : "unavailable"}
          </span>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`mr-1.5 size-3.5 ${isFetching ? "animate-spin" : ""}`} aria-hidden />
            Refresh
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={url} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1.5 size-3.5" aria-hidden />
              Open directly
            </a>
          </Button>
        </div>
      </div>

      {!available ? (
        <Card className="border-amber-500/40">
          <CardContent className="flex min-h-56 flex-col items-center justify-center gap-3 p-6 text-center">
            <TriangleAlert className="size-8 text-amber-500" aria-hidden />
            <div>
              <p className="font-medium">Pizza Bot sidecar is unavailable</p>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                {data?.detail ?? (error instanceof Error ? error.message : "The health endpoint did not respond.")}
              </p>
            </div>
            <code className="rounded bg-muted px-2 py-1 text-xs">{url}</code>
          </CardContent>
        </Card>
      ) : (
        <iframe
          ref={frameRef}
          title="Pizza Bot Inbox"
          src={url}
          className="min-h-[42rem] flex-1 rounded-lg border bg-background"
          allow="clipboard-read; clipboard-write"
        />
      )}
    </div>
  )
}
