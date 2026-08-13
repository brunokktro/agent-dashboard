# Install diagnostics reference

Command-level detail for action 1 of `dashboard-support`. The spec owns the
decision flow; this file owns the commands, the expected output and what each
failure actually means.

All paths are placeholders. `$DASHBOARD_DIR` is the clone,
`$DASHBOARD_AGENTS_DIR` is the observed ecosystem (default `~/.kiro/agents`).

## The tools that already exist - reach for these first

Nothing below should be done by hand when a command does it. Each one is
non-destructive and safe to re-run:

| Command | What it does |
|---------|--------------|
| `bin/collect-diagnostics` | the whole detect phase in one paste-able, secret-free report |
| `bin/init-ecosystem` | reports what is missing; `--runners` scaffolds the runner scripts, `--service` installs a launchd/systemd unit, `--all` both, `--force` refreshes keeping a `.bak` |
| `bin/install-starters` | a starter routine so a new install is not born with empty charts (`heartbeat`, `log-hygiene`, `failure-triage`) |
| `bin/record-run <job> <cmd>` | records any command as a run - the universal adapter |
| `bin/sweep` | 31 assertions against the RUNNING server: every endpoint, every SPA route, the Help assets |

Telling someone to type five commands when one exists is a worse answer, and
doing it by hand hides which step actually failed.

## Phase 1 - detect

```bash
bin/collect-diagnostics
```

That is the whole phase: platform (including WSL2), runtime versions, whether
`frontend/dist` was built and `backend/.venv` exists, the agents dir and its
`runs.db`, the port, whether the server answers, and the npm registry in use.
A missing binary is reported, never fatal, and no secret is printed (env vars
come out as SET/UNSET only).

The manual commands below are the reference for driving it question-by-question
over chat, when the person cannot run the script.

```bash
# platform
uname -srm
[ -f /proc/version ] && grep -qi microsoft /proc/version && echo "WSL2 detected"
[ "$(uname -s)" = Darwin ] && sw_vers -productVersion

# runtimes
python3 --version   || echo "MISSING python3"
uv --version        || echo "MISSING uv"
node --version      || echo "MISSING node"
npm --version       || echo "MISSING npm"
sqlite3 --version   || echo "MISSING sqlite3 (only bin/record-run needs it)"

# build artifact - gitignored, exists only after npm run build
ls -l "$DASHBOARD_DIR/frontend/dist/index.html" 2>/dev/null || echo "dist NOT built"

# backend environment
ls -d "$DASHBOARD_DIR/backend/.venv" 2>/dev/null || echo "uv sync not run yet"

# observed ecosystem
AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}"
ls -d "$AGENTS_DIR" 2>/dev/null || echo "agents dir does not exist: $AGENTS_DIR"
ls -l "$AGENTS_DIR/runs.db" 2>/dev/null || echo "no runs.db yet (expected on a fresh install)"
ls "$AGENTS_DIR"/*.md 2>/dev/null | wc -l   # agent specs discovered

# port
PORT="${DASHBOARD_PORT:-7780}"
(command -v lsof >/dev/null && lsof -iTCP:"$PORT" -sTCP:LISTEN -Pn) \
  || (command -v ss >/dev/null && ss -ltnp "sport = :$PORT") \
  || echo "could not check the port (no lsof, no ss)"
```

Version comparison: Python must be >= 3.12 and Node >= 20. `python3.11` is the
most common blocker on Debian stable and on older WSL2 images.

### Reporting format

| Check | Found | Required | Verdict |
|-------|-------|----------|---------|
| Python | 3.11.9 | >= 3.12 | blocker |
| Node | 22.14.0 | >= 20 | ok |
| `frontend/dist` | absent | present | blocker |

Then: "what could not be checked and why". Never leave a check silently absent -
"I could not check the port, no `lsof` or `ss` on this machine" is a valid line
and an unchecked box is not.

## Phase 2 - fix, in this order

Order matters: each step depends on the previous one.

### 1. Runtimes

Debian / Ubuntu / WSL2:

```bash
sudo apt-get update && sudo apt-get install -y git sqlite3 curl python3-venv
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `python3-venv` unversioned. Pinning `python3.12-venv` breaks on releases
that ship a different Python.

macOS:

```bash
brew install node sqlite
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If the system Python is older than 3.12, `uv` can provide one:
`uv python install 3.12` and then `uv sync` picks it up.

After installing `uv` in the current shell, `uv` may not be on `PATH` until the
shell is restarted - `source $HOME/.local/bin/env` or open a new shell rather
than concluding the install failed.

### 2. Frontend build

```bash
cd "$DASHBOARD_DIR/frontend" && npm install && npm run build
```

Success looks like `dist/index.html` plus hashed assets under `dist/assets/`.
Verify the artifact, not the exit code:

```bash
ls -l "$DASHBOARD_DIR/frontend/dist/index.html" && ls "$DASHBOARD_DIR/frontend/dist/assets" | head
```

Common failures:

- `EACCES` inside `node_modules` - a previous `npm` ran as root. Fix ownership
  rather than re-running with `sudo`.
- Corporate npm registry with an expired token - `npm error code E401`. The
  packages here are public; point npm at the public registry for this install.
- Out of memory in a small WSL2/VM - raise the memory in `.wslconfig`, or build
  once on a bigger machine and copy `dist/`.

### 3. Backend dependencies

```bash
cd "$DASHBOARD_DIR/backend" && uv sync
```

`uv sync` creates `backend/.venv` from `uv.lock`. It is not `pip install -r`;
there is no `requirements.txt` on purpose.

### 4. Serve

```bash
cd "$DASHBOARD_DIR/backend"
DASHBOARD_AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}" \
  uv run uvicorn dashboard.main:app --port "${DASHBOARD_PORT:-7780}"
```

Keep it in a session that stays open, or supervise it - which step 5 does for you.

### 5. Make Run work, and survive a reboot

```bash
bin/init-ecosystem              # report only
bin/init-ecosystem --all        # runner scripts + launchd/systemd unit
```

The Run buttons are **disabled until `scripts/run-agent.sh` exists** in the
observed ecosystem - that is not a bug, it is the dashboard refusing to offer a
click that can only fail. Triggering is the ecosystem's job; the dashboard only
observes. `--service` installs the unit so a hand-started server stops dying on
reboot. Existing files are reported as `KEPT`, never overwritten (`--force`
moves yours to `<file>.bak-<timestamp>` first).

### 6. Give an empty install something to show

```bash
bin/install-starters --all
```

`heartbeat` (every 15 min) verifies the server serves the app and the API reads
the ecosystem, and fills the Overview, heatmap and health score with real data.
`log-hygiene` (weekly) compresses oversized logs and never deletes.
`failure-triage` diagnoses failed runs through the dashboard's own endpoint.
The two scheduled ones need no LLM and no kiro-cli.

## Phase 3 - symptom to cause

| Symptom | Most likely cause | Check |
|---------|-------------------|-------|
| Browser shows nothing / 404 at `/`, but `/api/overview` answers | `frontend/dist` not built | `ls frontend/dist/index.html` |
| **Run button is greyed out** | no `scripts/run-agent.sh` (jobs: `run-scheduled.sh`) in the ecosystem - by design | `curl -s $BASE/api/overview \| grep capabilities`, then `bin/init-ecosystem --runners` |
| **Terminal opens on "no agent with name X found"** | the config's internal `name` differs from the filename, and the version predates 3.0.1 | `curl -s $BASE/api/version`; update, or align the JSON `name` with the filename |
| **Code updated but the UI is the old one** | pre-3.0.0 served `index.html` with no `Cache-Control`, so the browser kept the previous bundle | one hard refresh, then update - 3.0.0+ revalidates the shell every load |
| **`/health` answers JSON instead of the Health page** | pre-3.0.0: the liveness route hijacked the page. It is `/healthz` now | `curl -s $BASE/healthz` |
| **Agents you do not operate clutter the list** | a shared agents dir also holds agents installed by other tools | `DASHBOARD_INCLUDE_AGENTS` (allowlist) or `DASHBOARD_EXCLUDE_AGENTS` |
| `Address already in use` | previous server still running | `lsof -iTCP:$PORT -sTCP:LISTEN -Pn` |
| UI loads but is empty (0 agents, 0 runs) | correct on a fresh install, or wrong `DASHBOARD_AGENTS_DIR` | count agent files in the agents dir; `bin/install-starters --all` |
| An agent is missing from the list | it needs `.md` frontmatter with `name:`, OR a `.json` with `name` + `tools`, directly in the agents dir (not a subdirectory) | `ls $AGENTS_DIR/<agent>.*` |
| `record-run` exits 127 | `sqlite3` CLI missing | `sqlite3 --version` |
| Run recorded but invisible in the UI | `record-run` wrote to a different dir than the server reads | compare `AGENTS_DIR` used by the script with `DASHBOARD_AGENTS_DIR` of the server |
| Server dies when the terminal closes (WSL2) | the distro shut down with its last process | `bin/init-ecosystem --service`, `tmux`, or enable systemd |
| Supervisor page shows nothing | no `scripts/schedule.json` in the agents dir | `ls $AGENTS_DIR/scripts/schedule.json` |

## Phase 4 - an empty install is not a broken install

The dashboard is a consumer. It reads, under `DASHBOARD_AGENTS_DIR`:
`runs.db`, `queue/{pending,running,done,failed}/*.json`,
`scripts/schedule.json`, `locks/*.lock`, agent `*.md` specs and `*.json`
configs. It creates none of them (`runs.db` is auto-created empty).

So a fresh clone with an empty dashboard is working as designed. Two ways to
give it something real, in order of preference:

```bash
bin/install-starters --all        # a routine that keeps producing data
# or, the single-shot version:
AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}" \
  "$DASHBOARD_DIR/bin/record-run" hello-dashboard echo "first run"
```

For an agent to be listed it must sit **directly** in `DASHBOARD_AGENTS_DIR`
(not a subdirectory) as either an `*.md` with YAML frontmatter carrying `name:`,
or a bare `*.json` kiro-cli config carrying `name` **and** `tools`. An `.md` +
`.json` pair is one agent. The `.json` is what unlocks chat and terminal.

One thing worth knowing before composing any kiro-cli command: the dashboard's
identity for an agent is the **filename**, but kiro-cli resolves `--agent` by
the `name` INSIDE the json. The API exposes both (`name`, `cli_name`) - use
`cli_name` to launch, `name` for everything else.

That is also how `dashboard-support` itself becomes visible in the dashboard:

```bash
bin/install-starters --agents   # installs failure-triage and dashboard-support
```

## Phase 5 - closing validation

Never declare success from an intermediate exit code. Three checks, in order:

```bash
BASE="http://127.0.0.1:${DASHBOARD_PORT:-7780}"
curl -fsS -o /dev/null -w '%{http_code} %{content_type}\n' "$BASE/"   # 200 AND html
curl -fsS "$BASE/healthz"                                             # liveness + effective port
bin/record-run support-selftest true && curl -fsS "$BASE/api/overview" | grep -q support-selftest
```

`/healthz` is the liveness probe; `/health` belongs to the SPA's Health page.

For a thorough pass - every endpoint, every route, the Help assets - run
`bin/sweep`. It catches what a unit test cannot, because it drives the running
server the way a browser does.

Distinguish the two ways the record-run check can fail:

- run absent from the API, present in the DB: the server reads another directory.
- run absent from both: `record-run` itself failed - read its log under
  `$AGENTS_DIR/logs/`.
