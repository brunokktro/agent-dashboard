/**
 * Theme bridge for the cross-origin KiroCrew host.
 *
 * When the dashboard embeds this app as an iframe, the host is a different
 * origin, so this window cannot read the host's localStorage and the host
 * cannot read ours. The host therefore POSTS the theme here:
 *
 *   { type: "kirocrew:theme-sync", theme: "dark" | "intellij-dark" | …,
 *     mode: "dark" | "light" }
 *
 * addressed to our exact origin. We validate before applying:
 *   - `event.source === window.parent` (only the embedding window, not a
 *     sibling frame), and
 *   - `event.origin` is a loopback host (the host runs on localhost / 127.0.0.1
 *     in every deployment this app supports).
 *
 * When no host message has arrived (direct open at http://localhost:7780 or
 * any standalone run), we fall back to our own `theme` localStorage key and
 * the OS `prefers-color-scheme`, so standalone behaviour is unchanged.
 *
 * `mode` is what we trust for the Tailwind `dark` class; `theme` is stored
 * verbatim and exposed on `data-theme` for styling keyed on the attribute.
 */

const HOST_THEME_SYNC = "kirocrew:theme-sync"
const READY_ANNOUNCE = "kirocrew:theme-ready"

/** Loopback hosts the embedding dashboard may run on. Anything else is not a
 *  KiroCrew host and its messages are ignored. */
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1"])

function isLoopbackOrigin(origin: string): boolean {
  try {
    return LOOPBACK_HOSTS.has(new URL(origin).hostname)
  } catch {
    return false
  }
}

function systemMode(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

/** Apply a resolved mode to the document. Exported for tests. */
export function applyMode(mode: "dark" | "light"): void {
  document.documentElement.classList.toggle("dark", mode === "dark")
}

/** Sync state shared by the bridge hook and the toggle. `null` while no host
 *  message has arrived; after that, the host's word is final until it stops
 *  sending (the host re-announces on every change, so a stale entry is not a
 *  concern — the bridge only applies what it receives). */
let hostControlled: boolean = false

/** Whether a host has ever taken control of the theme this boot. Exported for
 *  the toggle: when true, the toggle keeps localStorage write-only (its local
 *  choice is overridden by the next host post, which is correct — the host
 *  frame is the same dashboard surface the user just toggled on). */
export function isHostControlled(): boolean {
  return hostControlled
}

/**
 * Install the host-theme receiver. Returns a cleanup function. Call once at
 * the app root. Exported for tests and for the app entry.
 */
/** Test hook only: the module caches `hostControlled` across imports in one
 *  process, so Node tests call this between cases. Never used by the app. */
export function resetHostControlledForTests(): void {
  hostControlled = false
}

export function installHostThemeBridge(): () => void {
  // Initial state: standalone fallback. Under an embedding host this is
  // immediately overridden by the first post (which the host sends on mount
  // and again when we announce readiness below).
  const stored = localStorage.getItem("theme")
  applyMode(stored === "light" ? "light" : stored === "dark" ? "dark" : systemMode())

  const onMessage = (e: MessageEvent) => {
    const data = e.data as { type?: string; theme?: string; mode?: string } | null
    if (!data || data.type !== HOST_THEME_SYNC) return
    if (e.source !== window.parent) return
    if (!isLoopbackOrigin(e.origin)) return
    if (data.mode !== "dark" && data.mode !== "light") return
    hostControlled = true
    if (typeof data.theme === "string" && data.theme) {
      document.documentElement.dataset.theme = data.theme
    }
    applyMode(data.mode)
  }
  window.addEventListener("message", onMessage)

  // Announce readiness so the host re-posts if its first push raced our boot
  // (the host matches our source against live iframes before replying).
  window.parent.postMessage({ type: READY_ANNOUNCE }, "*")

  // Standalone fallback only: follow the OS while no host has spoken. Once a
  // host message lands, its word wins and this listener stops applying.
  const media = window.matchMedia("(prefers-color-scheme: dark)")
  const onMedia = () => {
    if (!hostControlled) applyMode(systemMode())
  }
  media.addEventListener("change", onMedia)

  return () => {
    window.removeEventListener("message", onMessage)
    media.removeEventListener("change", onMedia)
  }
}
