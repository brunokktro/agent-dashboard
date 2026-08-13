import { useState } from "react"
import { ArrowUpCircle, Check, RefreshCw, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"

interface VersionInfo {
  current: string
  latest: string | null
  update_available: boolean
  checked: boolean
  error: string | null
  repo: string | null
  url: string | null
}

/**
 * On-demand update check. It calls out to the upstream repo ONLY when clicked -
 * the dashboard makes no background network requests, which also means the
 * result is never stale-but-silent: you see exactly what the last click found.
 * A failed check reports as a failure, never as "up to date".
 */
export function UpdateCheck({ version }: { version?: string }) {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [busy, setBusy] = useState(false)

  const check = async () => {
    setBusy(true)
    try {
      const r = await fetch("/api/version?check=1")
      setInfo(await r.json())
    } catch (e) {
      setInfo({
        current: version ?? "?", latest: null, update_available: false,
        checked: true, error: String(e), repo: null, url: null,
      })
    } finally {
      setBusy(false)
    }
  }

  const label = () => {
    if (busy) return "Checking…"
    if (!info) return version ? `v${version}` : "Check for updates"
    if (info.error) return "Check failed"
    if (info.update_available) return `v${info.latest} available`
    return `Up to date (v${info.current})`
  }

  const tone = info?.error
    ? "text-amber-600"
    : info?.update_available
      ? "text-blue-600 font-medium"
      : "text-muted-foreground"

  const title = info?.error
    ? `${info.error} - click to retry`
    : info?.update_available
      ? `Your version: ${info.current}. Upstream: ${info.latest}. ` +
        "See CHANGELOG.md for what changed. Update with: git pull && " +
        "(cd frontend && npm run build) - installed as a KiroCrew app, " +
        "update it from the App Store instead."
      : info
        ? `Checked against ${info.repo}. Click to check again.`
        : "Check the upstream repo for a newer version (no background requests)"

  const Icon = busy
    ? RefreshCw
    : info?.error
      ? TriangleAlert
      : info?.update_available
        ? ArrowUpCircle
        : info
          ? Check
          : RefreshCw

  return (
    <Button
      variant="ghost"
      size="sm"
      className={`h-7 gap-1.5 px-2 text-xs ${tone}`}
      onClick={check}
      disabled={busy}
      title={title}
    >
      <Icon className={`size-3.5 ${busy ? "animate-spin" : ""}`} />
      <span className="hidden sm:inline">{label()}</span>
      {info?.update_available && info.url && (
        <a
          href={info.url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline"
          onClick={(e) => e.stopPropagation()}
        >
          repo
        </a>
      )}
    </Button>
  )
}
