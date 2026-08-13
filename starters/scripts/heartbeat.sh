#!/usr/bin/env bash
# heartbeat.sh - proves the dashboard and its ecosystem are alive, and gives a
# brand-new install something real to show.
#
# A fresh dashboard looks dead: zero agents, zero runs, empty charts. This job
# records one run of itself every 15 minutes, so the Overview, the heatmap and
# the health score all have genuine data from minute one - and if the server
# ever stops answering, the failed run says so.
#
# Deterministic: no LLM, no network beyond localhost. Installed by
# bin/install-starters.
set -uo pipefail

PORT="${DASHBOARD_PORT:-7780}"
BASE="http://127.0.0.1:$PORT"
AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}"

fail() { echo "heartbeat: $*" >&2; exit 1; }

# 1. the server answers, and answers with the app (not just any 200)
OUT="$(mktemp -t heartbeat)"
trap 'rm -f "$OUT"' EXIT
# -w prints the code even on failure, so do not append a fallback here or a
# failed request reports "000000"; default only when nothing was printed.
CODE="$(curl -fsS -o "$OUT" -w '%{http_code}' --max-time 10 "$BASE/" 2>/dev/null)"
CODE="${CODE:-000}"
[ "$CODE" = "200" ] || fail "GET / returned $CODE"
grep -qi '<html' "$OUT" || fail "GET / answered $CODE but did not serve the app (frontend/dist missing?)"

# 2. the API reads the ecosystem
curl -fsS --max-time 10 "$BASE/api/overview" 2>/dev/null | grep -q '"agents"' \
  || fail "/api/overview did not return an agents payload"

# 3. the data sources the dashboard depends on are readable
[ -d "$AGENTS_DIR" ] || fail "agents dir not found: $AGENTS_DIR"
[ -f "$AGENTS_DIR/runs.db" ] || echo "heartbeat: no runs.db yet - it is created on the first recorded run" >&2

echo "heartbeat ok: server up on $PORT, API reading $AGENTS_DIR"
