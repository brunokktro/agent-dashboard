#!/usr/bin/env bash
# discover.sh - Write a discovery to shared memory
# Usage: discover.sh <from_agent> <topic> <content> [ttl_days] [to_csv]
# `to_csv` empty = broadcast. Ex: "agent-a,agent-b".

set -euo pipefail

SHARED="${A2A_SHARED_DIR:-$HOME/.kiro/agents/shared-memory}"
FILE="$SHARED/discoveries.jsonl"
mkdir -p "$SHARED"

FROM="${1:?Usage: discover.sh <from> <topic> <content> [ttl_days] [to_csv]}"
TOPIC="${2:?}"
CONTENT="${3:?}"
TTL="${4:-30}"
TO_CSV="${5:-}"

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

jq -cn \
  --arg ts "$TS" \
  --arg from "$FROM" \
  --arg topic "$TOPIC" \
  --arg content "$CONTENT" \
  --arg ttl "$TTL" \
  --arg to "$TO_CSV" \
  '{ts:$ts, from:$from, topic:$topic, content:$content, ttl_days:($ttl|tonumber)}
   + (if ($to|length)>0 then {to:($to|split(",")|map(gsub("^\\s+|\\s+$";"")))} else {} end)' >> "$FILE"
