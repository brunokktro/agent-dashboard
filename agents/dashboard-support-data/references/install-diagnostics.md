# Install diagnostics reference

Command-level detail for action 1 of `dashboard-support`. The spec owns the
decision flow; this file owns the commands, the expected output and what each
failure actually means.

All paths are placeholders. `$DASHBOARD_DIR` is the clone,
`$DASHBOARD_AGENTS_DIR` is the observed ecosystem (default `~/.kiro/agents`).

## Phase 1 - detect

Run everything, collect everything, then report once. A missing tool is data,
not a reason to stop.

One-shot alternative: `bin/collect-diagnostics` runs this whole phase and prints
a single paste-able report (no secrets - env vars come out as SET/UNSET only).
The manual commands below are the reference for driving it question-by-question
over chat.

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

Keep it in a session that stays open, or supervise it (launchd, systemd, `tmux`).

## Phase 3 - symptom to cause

| Symptom | Most likely cause | Check |
|---------|-------------------|-------|
| Browser shows nothing / 404 at `/`, but `/api/overview` answers | `frontend/dist` not built | `ls frontend/dist/index.html` |
| `Address already in use` | previous server still running | `lsof -iTCP:$PORT -sTCP:LISTEN -Pn` |
| UI loads but is empty (0 agents, 0 runs) | correct on a fresh install, or wrong `DASHBOARD_AGENTS_DIR` | count `*.md` with frontmatter in the agents dir |
| Agents listed but no chat/terminal offered | the agent has a `.md` spec but no sibling `.json` config | `ls $AGENTS_DIR/<agent>.json` |
| `record-run` exits 127 | `sqlite3` CLI missing | `sqlite3 --version` |
| Run recorded but invisible in the UI | `record-run` wrote to a different dir than the server reads | compare `AGENTS_DIR` used by the script with `DASHBOARD_AGENTS_DIR` of the server |
| Server dies when the terminal closes (WSL2) | the distro shut down with its last process | run under `tmux` or enable systemd |
| Code changed, UI unchanged | stale server, or frontend not rebuilt | restart the server; rerun `npm run build` |
| Supervisor page shows nothing | no `scripts/schedule.json` in the agents dir | `ls $AGENTS_DIR/scripts/schedule.json` |

## Phase 4 - an empty install is not a broken install

The dashboard is a consumer. It reads, under `DASHBOARD_AGENTS_DIR`:
`runs.db`, `queue/{pending,running,done,failed}/*.json`,
`scripts/schedule.json`, `locks/*.lock`, agent `*.md` specs and `*.json`
configs. It creates none of them (`runs.db` is auto-created empty).

So a fresh clone with an empty dashboard is working as designed. The right move
is to record one run and watch it appear:

```bash
AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}" \
  "$DASHBOARD_DIR/bin/record-run" hello-dashboard echo "first run"
```

For an agent to be listed, its `*.md` needs YAML frontmatter with at least a
`name:` field, and it must sit directly in `DASHBOARD_AGENTS_DIR` - not in a
subdirectory. A sibling `<name>.json` is what unlocks chat and terminal for it.

That is also how `dashboard-support` itself becomes visible in the dashboard:
copy or symlink the two files from `agents/` in this repo into
`DASHBOARD_AGENTS_DIR`.

```bash
ln -s "$DASHBOARD_DIR/agents/dashboard-support.md"   "${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}/"
ln -s "$DASHBOARD_DIR/agents/dashboard-support.json" "${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}/"
```

## Phase 5 - closing validation

Never declare success from an intermediate exit code. The three checks in the
spec, in order: root returns 200 **and HTML**, `record-run` writes a real run,
the API reports that run back.

Distinguish the two ways step 3 can fail:

- run absent from the API, present in the DB: the server reads another directory.
- run absent from both: `record-run` itself failed - read its log under
  `$AGENTS_DIR/logs/`.
