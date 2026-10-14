export interface AppHost {
  status: string
  port: number
}

interface ResolveOptions {
  attempts?: number
  delayMs?: number
  wait?: (delayMs: number) => Promise<void>
}

const sleep = (delayMs: number) => new Promise<void>((resolve) => setTimeout(resolve, delayMs))

/** Resolve the managed backend after an install/update restart.
 *
 * KiroCrew can mount the app wrapper before the backend has registered its
 * dynamic port. A bounded retry absorbs that expected startup window without
 * hiding a backend that never becomes healthy.
 */
export async function resolveAppHost(
  get: () => Promise<AppHost>,
  { attempts = 30, delayMs = 500, wait = sleep }: ResolveOptions = {},
): Promise<AppHost> {
  if (attempts < 1) throw new Error("attempts must be at least 1")

  let lastError: unknown
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const host = await get()
      if (host.status !== "ok" || !Number.isInteger(host.port) || host.port < 1 || host.port > 65535) {
        throw new Error("app host returned an invalid status or port")
      }
      return host
    } catch (error) {
      lastError = error
      if (attempt < attempts) await wait(delayMs)
    }
  }

  const detail = lastError instanceof Error ? lastError.message : String(lastError)
  throw new Error(`backend did not become reachable after ${attempts} attempts: ${detail}`)
}
