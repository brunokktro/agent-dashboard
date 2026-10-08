import { useEffect } from "react"

const APP_NAME = "Agent Dashboard"

/** Sets the browser tab title to "<most specific> - ... - Agent Dashboard", the
 *  same convention as the Reports Portal. Called by each PAGE, never by the
 *  Shell: React runs child effects before parent effects, so a title set in the
 *  Shell would overwrite the page's more specific one on every navigation.
 *  Empty parts (data still loading) are skipped. */
export function usePageTitle(...parts: Array<string | null | undefined>) {
  const title = [...parts.filter(Boolean), APP_NAME].join(" - ")
  useEffect(() => {
    document.title = title
  }, [title])
}
