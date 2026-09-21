#!/usr/bin/env bash
# handoff.sh - Durable A2A delegation through the REAL queue.
# Usage: handoff.sh <from> <to> <skill> '<json_input>' [timeout_sec] [expected_output] [acceptance_pattern] [idempotency_key] [max_attempts]
#
# Two artifacts, two roles: `handoffs.jsonl` is append-only AUDIT history, and
# `agents-state/queue/pending` is the DELIVERY mechanism a worker actually polls.
# Writing only the audit log means nothing executes the handoff - it just sits
# `pending` forever. This script writes both, atomically.
set -euo pipefail

SHARED="${A2A_SHARED_DIR:-$HOME/.kiro/agents/shared-memory}"
QUEUE="${A2A_QUEUE_DIR:-$HOME/.kiro/agents-state/queue/pending}"
AGENTS="${A2A_AGENTS_DIR:-$HOME/.kiro/agents}"
HANDOFFS="$SHARED/handoffs.jsonl"
mkdir -p "$SHARED" "$QUEUE"

FROM="${1:?Usage: handoff.sh <from> <to> <skill> '<json_input>' [timeout] [expected_output]}"
TO="${2:?}"
SKILL="${3:?}"
INPUT="${4:-\{\}}"
TIMEOUT="${5:-600}"
EXPECTED="${6:-Agent returns a verified result and the artifacts changed.}"
ACCEPTANCE="${7:-}"
IDEMPOTENCY="${8:-}"
MAX_ATTEMPTS="${9:-2}"

# Exact target only. A runtime that fuzzy-resolves `example-agent` to `example-agent-qa` is not a
# delegation contract: the wrong agent can act on a shared artifact. Reject before queue/audit.
if [ ! -f "$AGENTS/$TO.md" ] && [ ! -f "$AGENTS/$TO.json" ]; then
  suggestion=$(find "$AGENTS" -maxdepth 1 \( -name "*$TO*.md" -o -name "*$TO*.json" \) -print 2>/dev/null | head -1)
  echo "ERROR: target agent exato nao existe: $TO${suggestion:+; talvez $(basename "$suggestion" | sed 's/\.[^.]*$//')}" >&2
  exit 2
fi

# Optional producer dedup. Benchmark: re-enqueueing 50 completed file handoffs reprocessed all 50;
# SQLite/JetStream rejected them. Keep backward compatibility when no key is provided, but when the
# caller knows the business identity, reuse the existing handoff across pending/running/done/failed.
if [ -n "$IDEMPOTENCY" ]; then
  existing=$(A2A_QUEUE_ROOT="$(dirname "$QUEUE")" A2A_IDEMPOTENCY="$IDEMPOTENCY" python3 - <<'PY'
import json,os
from pathlib import Path
for p in Path(os.environ['A2A_QUEUE_ROOT']).glob('*/*.json'):
    try:d=json.loads(p.read_text())
    except Exception:continue
    if d.get('idempotencyKey') == os.environ['A2A_IDEMPOTENCY']:
        print(d.get('id',''));break
PY
)
  if [ -n "$existing" ]; then
    echo "$existing"
    exit 0
  fi
fi

ID="h$(date +%s)$(( RANDOM % 1000 ))"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TRACE="tr-$(date +%s)-$$"
TMP="$QUEUE/.${ID}.tmp"
DST="$QUEUE/${ID}.json"

# Python validates input JSON and writes both contracts. Queue publish is atomic: the supervisor
# never sees a half-written item. `expected_output` is mandatory in the documented handoff schema;
# the old producer silently omitted it.
HANDOFF_ID="$ID" HANDOFF_TS="$TS" HANDOFF_FROM="$FROM" HANDOFF_TO="$TO" \
HANDOFF_SKILL="$SKILL" HANDOFF_INPUT="$INPUT" HANDOFF_TIMEOUT="$TIMEOUT" \
HANDOFF_EXPECTED="$EXPECTED" HANDOFF_ACCEPTANCE="$ACCEPTANCE" HANDOFF_IDEMPOTENCY="$IDEMPOTENCY" HANDOFF_MAX_ATTEMPTS="$MAX_ATTEMPTS" HANDOFF_TRACE="$TRACE" HANDOFF_TMP="$TMP" \
HANDOFF_DST="$DST" HANDOFF_LOG="$HANDOFFS" python3 - <<'PY'
import json, os
from pathlib import Path
try:
    data=json.loads(os.environ["HANDOFF_INPUT"])
except json.JSONDecodeError as exc:
    raise SystemExit(f"invalid json_input: {exc}")
record={
    "id":os.environ["HANDOFF_ID"], "ts":os.environ["HANDOFF_TS"],
    "from":os.environ["HANDOFF_FROM"], "to":os.environ["HANDOFF_TO"],
    "skill":os.environ["HANDOFF_SKILL"], "input":data,
    "expected_output":os.environ["HANDOFF_EXPECTED"],
    "acceptance_pattern":os.environ["HANDOFF_ACCEPTANCE"] or None,
    "idempotency_key":os.environ["HANDOFF_IDEMPOTENCY"] or None,
    "max_attempts":int(os.environ["HANDOFF_MAX_ATTEMPTS"]),
    "timeout_sec":int(os.environ["HANDOFF_TIMEOUT"]),
    "trace_id":os.environ["HANDOFF_TRACE"], "status":"pending", "result":None,
}
prompt=(f"A2A handoff from {record['from']}. Skill/mode: {record['skill']}. "
        f"Input: {json.dumps(data,ensure_ascii=False)}. "
        f"Expected output: {record['expected_output']}")
queue={
    "id":record["id"], "agent":record["to"], "input":prompt,
    "params":{"source":"a2a-handoff","handoff_id":record["id"],
              "from":record["from"],"skill":record["skill"],
              "expected_output":record["expected_output"],"timeout_sec":record["timeout_sec"],
              "acceptance_pattern":record["acceptance_pattern"]},
    "priority":"medium", "created":record["ts"], "status":"pending",
    "idempotencyKey":record["idempotency_key"], "attempts":0,
    "maxAttempts":record["max_attempts"],
}
tmp=Path(os.environ["HANDOFF_TMP"]); dst=Path(os.environ["HANDOFF_DST"])
tmp.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+"\n")
tmp.replace(dst)
with Path(os.environ["HANDOFF_LOG"]).open("a") as f:
    f.write(json.dumps(record,ensure_ascii=False)+"\n")
PY

echo "$ID"
