/** lastRoute - remember which tab you were on across iframe remounts.
 *
 * Why this exists
 * ---------------
 * The dashboard runs as an iframe inside the KiroCrew host, and the host
 * renders an app page as an ordinary lazy React Router element. Navigating to
 * another app or another Crew function unmounts that element, so coming back
 * mounts a FRESH iframe - and the shell always points it at `/`. The tab you
 * were on is lost on every excursion, even though this SPA has a perfectly
 * good router that knew exactly where you were.
 *
 * The host side cannot be fixed from here: an app manifest may declare only
 * `entry`, `pages`, `overlays` and `sidebar`, so an app page has no way to ask
 * to stay mounted (the host's side panel does keep its tabs mounted and hides
 * them with `display:none`, but a third-party app cannot register there). So
 * the SPA remembers its own position instead: it records the path it is on,
 * and when it next boots at `/` it goes back there.
 *
 * Deliberate limits
 * -----------------
 *  * Only a boot at `/` restores. A deep link, or a reload while on `/logs`,
 *    is explicit intent and is never overridden.
 *  * The stored destination is validated against the live route table before use.
 *    The only query state accepted is one safe `file` parameter on `/logs`, so
 *    returning to Logs can reopen the exact file without turning localStorage
 *    into a generic navigation input.
 *  * Storage failure is not an error. Partitioned or disabled storage simply
 *    turns the feature off; it must never break the dashboard.
 *  * The key lives in this iframe's own origin, which includes the backend's
 *    dynamic port. If KiroCrew assigns a different port, the memory starts
 *    fresh - a reset to Overview, never a wrong destination.
 */

const KEY = "agent-dashboard:last-route"

/** `/agent/<name>` is the one real route that is not in the tab list. Names
 *  come from directory entries, so the charset is deliberately narrow and the
 *  length is bounded: this is a validator, not a parser. */
const AGENT_PATH = /^\/agent\/[A-Za-z0-9._-]{1,64}$/

/** Mirror the backend log-name boundary before restoring a selected file. */
function isSelectedLogPath(stored: string): boolean {
  if (!stored.startsWith("/logs?")) return false
  try {
    const url = new URL(stored, "http://dashboard.local")
    if (url.origin !== "http://dashboard.local" || url.pathname !== "/logs" || url.hash)
      return false
    const entries = [...url.searchParams.entries()]
    if (entries.length !== 1 || entries[0][0] !== "file") return false
    const name = entries[0][1]
    return name.length > 0 && name.length <= 255
      && !name.includes("/") && !name.includes("..") && name.endsWith(".log")
  } catch {
    return false
  }
}

/** The last recorded path, or null when there is nothing usable to read. */
export function readLastRoute(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null // storage partitioned or disabled: feature off, not broken
  }
}

/** Record the current path. Failure is silent by design - see above. */
export function writeLastRoute(path: string): void {
  try {
    localStorage.setItem(KEY, path)
  } catch {
    /* nothing to remember and nothing worth reporting */
  }
}

/**
 * The path to restore, or null to stay where we are.
 *
 * `known` is the live tab list, passed in rather than copied here on purpose:
 * adding a tab in App.tsx must not require a second edit to make it
 * restorable, and a list duplicated here would drift silently.
 */
export function routeToRestore(
  current: string,
  stored: string | null,
  known: readonly string[],
): string | null {
  if (current !== "/") return null // deep link or reload: the user's intent wins
  if (!stored || stored === "/") return null // already where we would send them
  if (known.includes(stored) || AGENT_PATH.test(stored) || isSelectedLogPath(stored))
    return stored
  return null // unknown, stale or forged: ignore it
}
