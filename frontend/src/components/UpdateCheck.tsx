import { useEffect, useRef, useState } from "react"
import {
  ArrowUpCircle, Check, Copy, RefreshCw, TriangleAlert, X,
} from "lucide-react"
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

/** Remembered across reloads, so "you are behind" does not vanish on refresh. */
const SEEN_KEY = "dashboard.update.seen"

type Seen = { latest: string; current: string; at: string }

function loadSeen(): Seen | null {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    return raw ? (JSON.parse(raw) as Seen) : null
  } catch {
    return null
  }
}

/**
 * Update awareness, deliberately in three separable parts:
 *
 *  1. a marker that PERSISTS once a newer release was seen (localStorage), so
 *     the fact that you are on an older version survives a reload instead of
 *     being re-discovered on every click;
 *  2. a panel that shows the outcome of a check as a STATE, never as a flash -
 *     a failed check reads as "could not check", not as breakage;
 *  3. an update path that only ever hands you the command. Nothing here mutates
 *     the installation: a dashboard that git-pulls and rebuilds itself while
 *     running is a foot-gun (dirty tree, local commits, a service that needs a
 *     restart), and it must never happen without you asking for it.
 */
export function UpdateCheck() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [seen, setSeen] = useState<Seen | null>(loadSeen)
  const panel = useRef<HTMLDivElement>(null)

  // close the panel on outside click / Escape - it opens, so it must close
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!panel.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false)
    document.addEventListener("mousedown", onDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  const check = async () => {
    setOpen(true)
    setBusy(true)
    try {
      const r = await fetch("/api/version?check=1", {
        cache: "no-store",
        headers: { "Cache-Control": "no-cache" },
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d: VersionInfo = await r.json()
      setInfo(d)
      if (d.update_available && d.latest) {
        const rec = { latest: d.latest, current: d.current, at: new Date().toISOString() }
        localStorage.setItem(SEEN_KEY, JSON.stringify(rec))
        setSeen(rec)
      } else if (!d.error) {
        // we are current: the marker has served its purpose
        localStorage.removeItem(SEEN_KEY)
        setSeen(null)
      }
    } catch (e) {
      setInfo({
        current: info?.current ?? seen?.current ?? "?", latest: null,
        update_available: false, checked: true, error: String(e),
        repo: info?.repo ?? null, url: info?.url ?? null,
      })
    } finally {
      setBusy(false)
    }
  }

  const command = "git pull && (cd frontend && npm run build)"
  const behind = !!seen // a newer release was seen and not yet installed

  // The trigger never changes shape while working: same width, same position,
  // so a check does not make the header jump or look like it broke.
  return (
    <span className="relative flex items-center">
      <Button
        variant="ghost"
        size="sm"
        className={`h-7 gap-1.5 px-2 text-xs tabular-nums ${
          behind ? "text-blue-600" : "text-muted-foreground"
        }`}
        onClick={() => (open ? setOpen(false) : check())}
        title={behind
          ? `A newer release (v${seen!.latest}) was found. Click for details.`
          : "Check the upstream repo for a newer version. Nothing is checked in the background."}
      >
        {busy ? (
          <RefreshCw className="size-3.5 shrink-0 animate-spin" />
        ) : behind ? (
          <ArrowUpCircle className="size-3.5 shrink-0" />
        ) : (
          <RefreshCw className="size-3.5 shrink-0" />
        )}
        <span>{busy ? "Checking…" : behind ? `v${seen!.latest}` : "Version"}</span>
        {behind && <span className="size-1.5 rounded-full bg-blue-500" aria-hidden />}
      </Button>

      {open && (
        <div
          ref={panel}
          className="absolute right-0 top-9 z-50 w-80 rounded-lg border bg-background p-3 text-xs shadow-lg"
          role="dialog"
          aria-label="Update status"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="font-medium">Update</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
              <X className="size-3.5" />
            </button>
          </div>

          {busy && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <RefreshCw className="size-3.5 animate-spin" /> Asking {info?.repo ?? "the upstream repo"}…
            </p>
          )}

          {!busy && info?.error && (
            <div className="space-y-2">
              <p className="flex items-start gap-2 text-amber-600">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                <span>Could not check - your install is fine, the check is not.</span>
              </p>
              <p className="text-muted-foreground">{info.error}</p>
              <p className="text-muted-foreground">
                Installed: <span className="font-medium">v{info.current}</span>. Whether a
                newer release exists is unknown right now.
              </p>
              <Button size="sm" variant="outline" className="h-7 w-full text-xs" onClick={check}>
                Try again
              </Button>
            </div>
          )}

          {!busy && info && !info.error && !info.update_available && (
            <div className="space-y-1.5">
              <p className="flex items-center gap-2 text-emerald-600">
                <Check className="size-3.5" /> Up to date
              </p>
              <p className="text-muted-foreground">
                Installed <span className="font-medium">v{info.current}</span>, and{" "}
                {info.repo} has no newer release.
              </p>
              <p className="text-[11px] text-muted-foreground">
                The upstream file is CDN-cached for a few minutes, so a release published
                seconds ago may not show yet.
              </p>
            </div>
          )}

          {!busy && info?.update_available && (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-blue-600">
                <ArrowUpCircle className="size-3.5" /> v{info.latest} is available
              </p>
              <p className="text-muted-foreground">
                You are on <span className="font-medium">v{info.current}</span>. Nothing was
                changed - updating is your call.
              </p>
              <div className="rounded border bg-muted/50 p-2 font-mono text-[11px] leading-relaxed">
                {command}
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 flex-1 gap-1.5 text-xs"
                  onClick={() => {
                    navigator.clipboard?.writeText(command)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                >
                  <Copy className="size-3.5" /> {copied ? "Copied" : "Copy command"}
                </Button>
                {info.url && (
                  <Button asChild size="sm" variant="outline" className="h-7 flex-1 text-xs">
                    <a href={`${info.url}/blob/main/CHANGELOG.md`} target="_blank" rel="noreferrer noopener">
                      What changed
                    </a>
                  </Button>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                Restart the server afterwards. Installed as a KiroCrew app? Update it from
                the App Store instead.
              </p>
            </div>
          )}

          {!busy && !info && behind && (
            <p className="text-muted-foreground">
              A newer release (v{seen!.latest}) was found on{" "}
              {new Date(seen!.at).toLocaleString()}. Click Version to check again.
            </p>
          )}
        </div>
      )}
    </span>
  )
}
