/** Unit tests for lib/hostTheme, run by Node's built-in test runner.
 *
 * Like lastRoute.test.ts, this sits outside `src` so the app's tsconfig does
 * not try to type-check `node:test` into the browser build.
 *
 * The module touches the DOM (documentElement class, matchMedia, postMessage,
 * message events), so each test installs a minimal DOM stub on globalThis and
 * loads the module fresh — Node caches ESM imports per process and the module
 * keeps state (`hostControlled`), so a cached import would leak between cases.
 */
import { test } from "node:test"
import assert from "node:assert/strict"

/** Minimal shape of the parts of the DOM the bridge module touches. */
type Dom = {
  html: { classes: Set<string>; dataset: Record<string, string> }
  prefersDark: boolean
  mediaListeners: Array<() => void>
  parent: { postMessage: (msg: unknown, origin: string) => void }
  posts: Array<{ msg: unknown; origin: string }>
  messageListeners: Array<(e: unknown) => void>
}

/** Install a DOM stub, load the module fresh, run the body, clean up. */
async function withDom(body: (dom: Dom, mod: typeof import("../src/lib/hostTheme.ts")) => void): Promise<void> {
  const dom: Dom = {
    html: { classes: new Set(), dataset: {} },
    prefersDark: true,
    mediaListeners: [],
    parent: {
      postMessage: (msg: unknown, origin: string) => {
        dom.posts.push({ msg, origin })
      },
    },
    posts: [],
    messageListeners: [],
  }
  ;(globalThis as Record<string, unknown>).document = {
    documentElement: {
      classList: {
        toggle: (name: string, on: boolean) => {
          if (on) dom.html.classes.add(name)
          else dom.html.classes.delete(name)
        },
        contains: (name: string) => dom.html.classes.has(name),
      },
      dataset: dom.html.dataset,
    },
  }
  ;(globalThis as Record<string, unknown>).window = {
    matchMedia: (query: string) => {
      assert.match(query, /prefers-color-scheme/)
      return {
        matches: dom.prefersDark,
        addEventListener: (_: string, fn: () => void) => dom.mediaListeners.push(fn),
        removeEventListener: (_: string, fn: () => void) => {
          const i = dom.mediaListeners.indexOf(fn)
          if (i >= 0) dom.mediaListeners.splice(i, 1)
        },
      }
    },
    addEventListener: (_: string, fn: (e: unknown) => void) => dom.messageListeners.push(fn),
    removeEventListener: (_: string, fn: (e: unknown) => void) => {
      const i = dom.messageListeners.indexOf(fn)
      if (i >= 0) dom.messageListeners.splice(i, 1)
    },
    parent: dom.parent,
  }
  ;(globalThis as Record<string, unknown>).localStorage = {
    getItem: () => undefined,
    setItem: () => {},
    removeItem: () => {},
  }
  try {
    const mod = (await import(`../src/lib/hostTheme.ts?t=${Math.random()}`)) as typeof import("../src/lib/hostTheme.ts")
    mod.resetHostControlledForTests()
    body(dom, mod)
  } finally {
    delete (globalThis as Record<string, unknown>).document
    delete (globalThis as Record<string, unknown>).window
    delete (globalThis as Record<string, unknown>).localStorage
  }
}

/** Deliver a message event through the currently registered listeners.
 *  `source` must be `dom.parent` to pass the bridge's check, because the
 *  bridge compares `event.source` against the stubbed `window.parent`. */
function fire(dom: Dom, msg: unknown, source: unknown, origin: string): void {
  for (const fn of [...dom.messageListeners]) {
    fn({ data: msg, source, origin })
  }
}

/** Distinct stand-in for a window that is not the embedding parent. */
const OTHER = Symbol("other-window")

const SYNC = { type: "kirocrew:theme-sync" }

test("standalone boot: no stored theme follows the OS preference", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(mod.isHostControlled(), false)
    assert.deepEqual(dom.posts, [{ msg: { type: "kirocrew:theme-ready" }, origin: "*" }])
  })
})

test("standalone boot: stored light wins over OS dark", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    ;(globalThis as Record<string, unknown>).localStorage = {
      getItem: (key: string) => (key === "theme" ? "light" : undefined),
      setItem: () => {},
      removeItem: () => {},
    }
    mod.installHostThemeBridge()
    assert.equal(dom.html.classes.has("dark"), false)
  })
})

test("standalone boot: OS flips and the unhosted bridge follows", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    assert.equal(dom.html.classes.has("dark"), true)
    dom.prefersDark = false
    for (const fn of dom.mediaListeners) fn()
    assert.equal(dom.html.classes.has("dark"), false)
  })
})

test("host message from the parent on a loopback origin applies mode and theme", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    assert.equal(dom.html.classes.has("dark"), true)
    fire(dom, { ...SYNC, theme: "intellij-light", mode: "light" }, dom.parent, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), false)
    assert.equal(dom.html.dataset.theme, "intellij-light")
    assert.equal(mod.isHostControlled(), true)
  })
})

test("host message applies dark mode and a verbatim theme attribute", async () => {
  await withDom((dom, mod) => {
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, theme: "kiro-dark", mode: "dark" }, dom.parent, "http://127.0.0.1:9103")
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(dom.html.dataset.theme, "kiro-dark")
  })
})

test("host message with an invalid mode is ignored", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, theme: "dark", mode: "tiramisu" }, dom.parent, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(mod.isHostControlled(), false)
    assert.equal(dom.html.dataset.theme, undefined)
  })
})

test("host message from a non-parent source is ignored", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, theme: "dark", mode: "dark" }, OTHER, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(mod.isHostControlled(), false)
  })
})

test("host message from a non-loopback origin is ignored", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, theme: "dark", mode: "dark" }, dom.parent, "https://evil.example.com")
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(mod.isHostControlled(), false)
  })
})

test("non-theme-sync messages and null data are ignored", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { type: "something:else", mode: "light" }, dom.parent, "http://localhost:7780")
    fire(dom, null, dom.parent, "http://localhost:7780")
    fire(dom, "kirocrew:theme-sync", dom.parent, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), true)
    assert.equal(mod.isHostControlled(), false)
  })
})

test("OS preference change is not applied once the host controls the theme", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, theme: "dark", mode: "light" }, dom.parent, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), false)
    for (const fn of dom.mediaListeners) fn() // OS flips to dark…
    assert.equal(dom.html.classes.has("dark"), false, "the host's word must stay")
  })
})

test("install announces readiness to the parent", async () => {
  await withDom((dom, mod) => {
    mod.installHostThemeBridge()
    assert.equal(dom.posts.length, 1)
    assert.deepEqual(dom.posts[0].msg, { type: "kirocrew:theme-ready" })
  })
})

test("cleanup removes the message listener so later messages are ignored", async () => {
  await withDom((dom, mod) => {
    assert.equal(dom.messageListeners.length, 0)
    const cleanup = mod.installHostThemeBridge()
    assert.equal(dom.messageListeners.length, 1)
    assert.equal(dom.mediaListeners.length, 1)
    cleanup()
    assert.equal(dom.messageListeners.length, 0)
    assert.equal(dom.mediaListeners.length, 0)
    fire(dom, { ...SYNC, theme: "dark", mode: "dark" }, dom.parent, "http://localhost:7780")
    assert.equal(mod.isHostControlled(), false)
    assert.equal(dom.html.dataset.theme, undefined)
  })
})

test("a host message missing the theme key still applies the mode", async () => {
  await withDom((dom, mod) => {
    dom.prefersDark = true
    mod.installHostThemeBridge()
    fire(dom, { ...SYNC, mode: "light" }, dom.parent, "http://localhost:7780")
    assert.equal(dom.html.classes.has("dark"), false)
    assert.equal(dom.html.dataset.theme, undefined, "no theme key must not clear an attribute")
    assert.equal(mod.isHostControlled(), true)
  })
})
