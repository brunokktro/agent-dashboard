import test from "node:test"
import assert from "node:assert/strict"

import { resolveAppHost } from "../src/appHost.ts"

const noWait = async () => {}

test("returns a healthy app host without retrying", async () => {
  let calls = 0
  const host = await resolveAppHost(
    async () => {
      calls += 1
      return { status: "ok", port: 9103 }
    },
    { wait: noWait },
  )

  assert.deepEqual(host, { status: "ok", port: 9103 })
  assert.equal(calls, 1)
})

test("recovers when the backend registers after the wrapper mounts", async () => {
  let calls = 0
  let waits = 0
  const host = await resolveAppHost(
    async () => {
      calls += 1
      if (calls < 3) throw new Error("API 502: no reachable backend")
      return { status: "ok", port: 9103 }
    },
    { attempts: 4, delayMs: 1, wait: async () => { waits += 1 } },
  )

  assert.equal(host.port, 9103)
  assert.equal(calls, 3)
  assert.equal(waits, 2)
})

test("fails after the bounded retry window", async () => {
  let calls = 0
  await assert.rejects(
    resolveAppHost(
      async () => {
        calls += 1
        throw new Error("API 502: no reachable backend")
      },
      { attempts: 3, delayMs: 1, wait: noWait },
    ),
    /after 3 attempts: API 502/,
  )
  assert.equal(calls, 3)
})

test("rejects an invalid app-host response", async () => {
  await assert.rejects(
    resolveAppHost(
      async () => ({ status: "ok", port: 0 }),
      { attempts: 1, wait: noWait },
    ),
    /invalid status or port/,
  )
})
