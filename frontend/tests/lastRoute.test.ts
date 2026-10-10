/** Unit tests for lib/lastRoute, run by Node's built-in test runner.
 *
 * No test dependency is added on purpose: Node strips the types natively, so
 * `npm run test` needs nothing that `npm run build` does not already need.
 * The file sits outside `src` so the app's tsconfig (include: ["src"]) does
 * not try to type-check `node:test` into the browser build.
 */
import { test } from "node:test"
import assert from "node:assert/strict"

import { readLastRoute, routeToRestore, writeLastRoute } from "../src/lib/lastRoute.ts"

/** The real tab list from App.tsx, as the hook passes it in. */
const TABS = [
  "/", "/agents", "/queue", "/a2a", "/pizza",
  "/health", "/supervisor", "/console", "/logs", "/help",
] as const

type Store = { get: Record<string, string> }

/** Install a localStorage stub for one test and remove it afterwards. */
function withStorage(impl: Partial<Storage>, body: () => void): void {
  const had = "localStorage" in globalThis
  const previous = (globalThis as { localStorage?: unknown }).localStorage
  Object.defineProperty(globalThis, "localStorage", {
    value: impl, configurable: true, writable: true,
  })
  try {
    body()
  } finally {
    if (had) {
      Object.defineProperty(globalThis, "localStorage", {
        value: previous, configurable: true, writable: true,
      })
    } else {
      delete (globalThis as { localStorage?: unknown }).localStorage
    }
  }
}

test("restores a remembered tab when the iframe boots at the root", () => {
  assert.equal(routeToRestore("/", "/logs", TABS), "/logs")
  assert.equal(routeToRestore("/", "/console", TABS), "/console")
})

test("never overrides a deep link or an in-place reload", () => {
  // The iframe is pointed at `/`, so any other boot path is explicit intent.
  assert.equal(routeToRestore("/logs", "/health", TABS), null)
  assert.equal(routeToRestore("/agent/meta-agent", "/queue", TABS), null)
})

test("does nothing when there is nothing to restore", () => {
  assert.equal(routeToRestore("/", null, TABS), null)
  assert.equal(routeToRestore("/", "", TABS), null)
  assert.equal(routeToRestore("/", "/", TABS), null) // already the destination
})

test("ignores a path that is not a live route", () => {
  assert.equal(routeToRestore("/", "/does-not-exist", TABS), null)
  assert.equal(routeToRestore("/", "/logs/extra", TABS), null)
  assert.equal(routeToRestore("/", "logs", TABS), null) // not absolute
})

test("ignores a forged or hostile stored value", () => {
  // localStorage is writable by anything running in this origin, and
  // navigate() takes whatever string it is given - so these must not pass.
  for (const hostile of [
    "//evil.example.com",
    "https://evil.example.com",
    "javascript:alert(1)",
    "/../../etc/passwd",
    "/logs?x=<script>alert(1)</script>",
    "/agent/../../admin",
    "/agent/<script>",
    "/agent/", // empty name
    `/agent/${"a".repeat(65)}`, // over the length bound
  ]) {
    assert.equal(routeToRestore("/", hostile, TABS), null, `accepted ${hostile}`)
  }
})

test("accepts the dynamic per-agent route", () => {
  assert.equal(routeToRestore("/", "/agent/meta-agent", TABS), "/agent/meta-agent")
  assert.equal(routeToRestore("/", "/agent/r2d2_v2.1", TABS), "/agent/r2d2_v2.1")
})

test("a tab added in App.tsx becomes restorable with no change here", () => {
  // The guard against the list drifting: `known` is the live tab list, so a
  // new tab needs no second edit in lib/lastRoute.
  assert.equal(routeToRestore("/", "/brand-new", TABS), null)
  assert.equal(routeToRestore("/", "/brand-new", [...TABS, "/brand-new"]), "/brand-new")
})

test("reads and writes through a working storage", () => {
  const data: Store = { get: {} }
  withStorage(
    {
      getItem: (k: string) => data.get[k] ?? null,
      setItem: (k: string, v: string) => { data.get[k] = v },
    } as Partial<Storage>,
    () => {
      assert.equal(readLastRoute(), null)
      writeLastRoute("/health")
      assert.equal(readLastRoute(), "/health")
    },
  )
})

test("survives storage that throws, and storage that is absent", () => {
  const boom = () => { throw new Error("storage partitioned") }
  withStorage({ getItem: boom, setItem: boom } as Partial<Storage>, () => {
    assert.equal(readLastRoute(), null)
    assert.doesNotThrow(() => writeLastRoute("/logs"))
  })

  // No localStorage at all: the reference itself throws, which must also be
  // caught - this is the case Node reproduces for free.
  const had = "localStorage" in globalThis
  if (!had) {
    assert.equal(readLastRoute(), null)
    assert.doesNotThrow(() => writeLastRoute("/logs"))
  }
})
