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
 *
 * Two defects fixed after real use, both worth keeping in mind:
 *  - `cache: "no-store"` (and the same header from the API): without it the
 *    browser heuristically caches the GET, so a second click answers from cache
 *    and the check silently stops checking.
 *  - the "see repo" link is a SIBLING of the button, never nested inside it:
 *    interactive content inside a <button> is invalid HTML and made the click
 *    behave erratically.
 */
export function UpdateCheck() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [busy, setBusy] = useState(false)

  const check = async () => {
    setBusy(true)
    try {
      const r = await fetch("/api/version?check=1", {
        cache: "no-store",
        headers: { "Cache-Control": "no-cache" },
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setInfo(await r.json())
    } catch (e) {
      setInfo({
        current: info?.current ?? "?", latest: null, update_available: false,
        checked: true, error: String(e), repo: info?.repo ?? null, url: info?.url ?? null,
      })
    } finally {
      setBusy(false)
    }
  }

  const state = busy
    ? "busy"
    : !info
      ? "idle"
      : info.error
        ? "error"
        : info.update_available
          ? "update"
          : "current"

  const { Icon, label, tone, title } = {
    busy: {
      Icon: RefreshCw, label: "Checking…", tone: "text-muted-foreground",
      title: "Asking the upstream repo",
    },
    idle: {
      Icon: RefreshCw, label: "Check version", tone: "text-muted-foreground",
      title: "Check the upstream repo for a newer version. Nothing is checked " +
             "in the background - only when you click.",
    },
    error: {
      Icon: TriangleAlert, label: "Check failed", tone: "text-amber-600",
      title: `${info?.error ?? "unknown error"} - click to retry. A failed ` +
             "check is not a verdict: your version may or may not be current.",
    },
    update: {
      Icon: ArrowUpCircle, label: `v${info?.latest} available`,
      tone: "text-blue-600 font-medium",
      title: `You are on ${info?.current}, upstream has ${info?.latest}. ` +
             "CHANGELOG.md lists what changed. Update with: git pull && " +
             "(cd frontend && npm run build). Installed as a KiroCrew app? " +
             "Update it from the App Store instead. Click to check again.",
    },
    current: {
      Icon: Check, label: `v${info?.current}`, tone: "text-muted-foreground",
      title: `Up to date - checked against ${info?.repo ?? "the upstream repo"}. ` +
             "Click to check again. Note: the upstream file is CDN-cached for a " +
             "few minutes, so a release published seconds ago may not show yet.",
    },
  }[state]

  return (
    <span className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        className={`h-7 min-w-[7.5rem] justify-start gap-1.5 px-2 text-xs tabular-nums ${tone}`}
        onClick={check}
        disabled={busy}
        title={title}
      >
        <Icon className={`size-3.5 shrink-0 ${busy ? "animate-spin" : ""}`} />
        <span className="truncate">{label}</span>
      </Button>
      {info?.update_available && info.url && (
        <a
          href={info.url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-xs text-blue-600 underline hover:no-underline"
          title="Open the upstream repository"
        >
          repo
        </a>
      )}
    </span>
  )
}
