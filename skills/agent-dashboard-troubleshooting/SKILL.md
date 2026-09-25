---
name: agent-dashboard-troubleshooting
description: Install and troubleshoot the Agent Dashboard KiroCrew app (agent-dashboard) - App Store install errors, backend that will not start or fails its health check, an empty dashboard after install, missing runs, and updates. Read before diagnosing any agent-dashboard error.
triggers: apps detail agent dashboard, agent dashboard install, agent dashboard backend, agent dashboard healthz, agent dashboard runs db, agent dashboard empty, agent dashboard record run, agent dashboard not starting
version: 1.0.0
tags: [agent-dashboard, kirocrew-app, troubleshooting, install]
---

# Agent Dashboard - install and troubleshooting (KiroCrew app)

This skill ships inside the app and is registered when the app is enabled. It
covers the app **installed from the KiroCrew App Store**. For a standalone clone
(`uv run uvicorn ...` on port 7780) use the `dashboard-support` agent and
`agents/dashboard-support-data/references/install-diagnostics.md` instead.

## How the App Store install works

Nothing is cloned or built by hand. The catalog entry pins the **`release`**
branch, which is `main` plus one generated commit carrying the built
`frontend/dist` and `ui/dist`. So the target machine needs no Node and no uv.

1. **Install** fetches the `release` branch into `~/.kiro/crew/apps/agent-dashboard/`.
   The installer's build step finds the root `package.json` (an empty marker, no
   dependencies, no `build` script) and does nothing. See `docs/DECISIONS.md` #14.
2. **Trust.** It is a third-party app, so KiroCrew asks for consent once. Nothing
   runs until the user confirms that dialog.
3. **First backend start.** KiroCrew installs `requirements.txt` with
   `pip --target` into `data/.kirocrew-deps` (outside the signed bundle, so it
   works in the desktop app), then spawns `uvicorn server:app` on an automatic
   port and polls `/healthz`.
4. **onEnable** runs `cd frontend && [ -f dist/index.html ] || (npm ci && npm run build)`.
   On the `release` branch `dist/` exists, so this is a no-op.

## Where to look

| What | Path |
|------|------|
| App root | `~/.kiro/crew/apps/agent-dashboard/` |
| Backend log (stdout/stderr of uvicorn) | `~/.kiro/crew/apps/agent-dashboard/data/logs/backend.log` |
| Python deps provisioned by KiroCrew | `~/.kiro/crew/apps/agent-dashboard/data/.kirocrew-deps/` |
| Per-app settings | `~/.kiro/crew/apps/agent-dashboard/data/config.json` |
| Observed ecosystem (default) | `~/.kiro/agents/` (`runs.db`, `queue/`, `schedule.json`) |

```bash
kirocrew app info agent-dashboard      # installed version, enabled, backend state
kirocrew status                        # gateway health
tail -n 80 ~/.kiro/crew/apps/agent-dashboard/data/logs/backend.log
```

## Known failures - symptom, cause, fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| Install fails: `Python apps that require a build step are not supported in the desktop app` | Version 3.2.6 or older: no root `package.json`, so the installer tried `pip install` into the signed bundle | Update to 3.2.7+ from the App Store. Do not delete `requirements.txt`: the backend needs it at start |
| Install or enable is refused with a trust message | Third-party app not yet trusted | Confirm the consent dialog. Never edit config files to bypass it |
| Backend unhealthy, log shows `ModuleNotFoundError: fastapi` / `uvicorn` | Dependency provisioning failed (offline, proxy, private index) | Read the pip error in `backend.log`; fix network or index, then disable and re-enable the app |
| Page opens but everything is **empty** | Correct behavior: the dashboard only reads artifacts, and `~/.kiro/agents/runs.db` does not exist yet | See "Empty on a fresh install" below |
| Runs of one agent missing | That agent never writes to `runs.db` | Wrap its command with `bin/record-run <name> <command>` |
| Some agents hidden | `exclude_agents` globs in `data/config.json` | Remove the pattern |
| Run / Run-now buttons fail | `$DASHBOARD_AGENTS_DIR/scripts/run-agent.sh` or `run-scheduled.sh` missing | `bin/init-ecosystem --runners` from the app root |

## Empty on a fresh install

An empty dashboard is not a bug. Give it data, from the app root
(`cd ~/.kiro/crew/apps/agent-dashboard`):

```bash
bin/init-ecosystem                 # reports what is missing, changes nothing
bin/install-starters               # shows what it would install, changes nothing
bin/install-starters --scripts     # heartbeat + log-hygiene jobs, no LLM needed
bin/record-run hello-world echo ok # one throwaway run; needs the sqlite3 CLI
```

Validate by effect, never by exit code: the run must appear in the Overview
after a refresh.

## Rules for the diagnosing agent

- Read `backend.log` before proposing any fix. A process that exists is not a
  backend that answers `/healthz`.
- Never `pip install` into the KiroCrew bundle, and never remove `package.json`
  or `requirements.txt` from the app root: each is load-bearing (DECISIONS #14).
- Never edit trust, security or `denied_commands.json` settings to make a step pass.
- Never run `bin/init-ecosystem --service` for the App Store install: it creates a
  launchd/systemd unit for the STANDALONE server, and KiroCrew already owns the
  backend process. `--runners` is fine.
- `bin/collect-diagnostics` targets the standalone clone; its port and `dist`
  checks do not apply to the App Store install. Use the table above instead.
