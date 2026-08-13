# Changelog

## 3.0.0-alpha.2

First release shaped by an external install. Everything here came from someone
other than the author running it on their own machine.

### Fixed

- **JSON-native agents were invisible.** Discovery only scanned `.md` frontmatter,
  so an ecosystem whose agents are bare kiro-cli `.json` configs showed an empty
  dashboard. A `.json` carrying `name` + `tools` is now a first-class agent; an
  `.md` + `.json` pair still counts once.
- **Triggering a run on a fresh clone failed opaquely.** `run-agent.sh` /
  `run-scheduled.sh` belong to the observed ecosystem, not to this repo. The API
  now answers `503` naming the missing file, and the Run buttons render
  **disabled** with a tooltip instead of offering a click that can only fail.
- **`main` no longer tracks build output.** Committed `dist` churned on every
  build and went stale silently. The bundles now live on a generated `release`
  branch (`bin/make-release`), which is what the app registry entry points at,
  so a one-click install still needs no Node.
- **A run stamped in the future is never the "last run"** (clock skew, a UTC
  container, a bad seed). It used to render a negative relative time while other
  views disagreed.
- Agent cards in the Agents tab are clickable as a whole, matching Overview.

### Added

- **Starter agents and jobs** - `bin/install-starters`: `heartbeat` (every 15 min,
  verifies the server serves the app and the API reads your ecosystem, and gives
  the charts real data immediately), `log-hygiene` (weekly, compresses logs past
  the threshold and never deletes), plus the `failure-triage` and
  `dashboard-support` agents. The scheduled ones need no LLM.
- **`bin/init-ecosystem`** - scaffolds the runner scripts and installs a launchd
  or systemd unit so the dashboard survives a reboot. Re-runnable on a live
  install; `--force` backs your files up before refreshing.
- **`bin/collect-diagnostics`** - one paste-able, secret-free environment report.
- **Update check** - a version button in the header, comparing against the
  upstream `app.json`. It only calls out when clicked, and a failed check says so
  instead of claiming you are up to date.
- **`DASHBOARD_INCLUDE_AGENTS`** - an allowlist, for when the agents directory is
  shared with agents installed by other tools. Exclusions still win.
- **App-host settings** - under KiroCrew the backend gets a minimal environment,
  so recognized keys from the host's per-app `config.json` now override env.
- **Packaged as a KiroCrew app** - `app.json` manifest, ASGI backend on an auto
  port, `/health`, and a thin shell page that embeds the app same-origin so the
  WebSocket terminals and SSE streams keep working.
- **Backlog kanban reorder** - drag cards in the active column; the order
  persists in each file's frontmatter.
- **`dashboard-support` agent** - guided install locally, or troubleshooting over
  a chat DM with a bounded reply window (`bin/await-reply`).

### Changed

- Site-specific failure hints moved out of the code into
  `DASHBOARD_EXTRA_HINTS`, keeping the shipped hint list generic.
- `docs/DECISIONS.md` records two decisions that came from real bugs: a PTY needs
  an explicit `winsize`, and a future-stamped run is not the last run.

## 3.0.0-alpha.1

Initial public release: typed FastAPI backend over the ecosystem's own
artifacts (`runs.db`, `queue/`, `schedule.json`, agent specs), React frontend
with Overview, Agents, Board, Health, Supervisor, Logs and Console, real-time
via a single WebSocket channel, failure diagnosis, PTY terminals and pipe mode,
and the universal `bin/record-run` adapter.
