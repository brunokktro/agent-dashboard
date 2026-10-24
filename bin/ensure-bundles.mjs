#!/usr/bin/env node
// ensure-bundles - the setup.onEnable hook (issue #5).
//
// A release install ships frontend/dist and ui/dist prebuilt, so this does nothing there: no npm
// install, no build. A source or tag install can lack either bundle; each tree is built ONLY when
// its own entry is missing, and the entries come from app.json, so a renamed ui.entry cannot
// silently drift from what this checks. Node, not shell, because every build needs npm (and so
// node) anyway, and the same file runs on any host that can build the bundles.
//
//   node bin/ensure-bundles.mjs            build what is missing
//   node bin/ensure-bundles.mjs --check    exit 1 listing what is missing, build nothing
import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"

const root = join(dirname(fileURLToPath(import.meta.url)), "..")
const manifest = JSON.parse(readFileSync(join(root, "app.json"), "utf8"))

export function bundles(appRoot = root, app = manifest) {
  // The dashboard SPA served by the backend, and the KiroCrew-facing ui.entry (relative to ui/).
  return [
    { tree: "frontend", entry: join(appRoot, "frontend", "dist", "index.html") },
    { tree: "ui", entry: join(appRoot, "ui", app.ui.entry) },
  ]
}

function run(cwd, args) {
  const npm = process.platform === "win32" ? "npm.cmd" : "npm"
  const r = spawnSync(npm, args, { cwd, stdio: "inherit", shell: process.platform === "win32" })
  if (r.status !== 0) throw new Error(`npm ${args.join(" ")} failed in ${cwd} (exit ${r.status})`)
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const missing = bundles().filter((b) => !existsSync(b.entry))
  if (process.argv.includes("--check")) {
    for (const b of missing) console.error(`missing ${b.tree}: ${b.entry}`)
    process.exit(missing.length ? 1 : 0)
  }
  for (const b of missing) {
    const cwd = join(root, b.tree)
    console.log(`[ensure-bundles] ${b.tree}: ${b.entry} absent, building`)
    if (!existsSync(join(cwd, "node_modules"))) run(cwd, ["ci", "--no-audit", "--no-fund"])
    run(cwd, ["run", "build"])
    if (!existsSync(b.entry)) {
      console.error(`[ensure-bundles] ${b.tree} built but ${b.entry} is still absent`)
      process.exit(1)
    }
  }
  if (!missing.length) console.log("[ensure-bundles] both bundles present, nothing to do")
}
