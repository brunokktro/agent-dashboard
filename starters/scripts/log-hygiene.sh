#!/usr/bin/env bash
# log-hygiene.sh - keep the logs directory from growing without bound.
#
# The dashboard raises a "large log" alert past DASHBOARD_BIG_LOG_MB (default
# 50). This job acts on it: every log over the threshold is COMPRESSED, never
# deleted - the archive stays fully readable with `gzip -dc <file>` (note: BSD
# zcat on macOS refuses a .gz argument, use `zcat < file` or gzip -dc), and
# nothing that was written is ever lost. Already-compressed files are skipped.
#
# Deterministic: no LLM. Installed by bin/install-starters.
set -uo pipefail

AGENTS_DIR="${DASHBOARD_AGENTS_DIR:-$HOME/.kiro/agents}"
LOG_DIR="$AGENTS_DIR/logs"
LIMIT_MB="${DASHBOARD_BIG_LOG_MB:-50}"
KEEP_TAIL_LINES="${LOG_HYGIENE_KEEP_TAIL:-2000}"

[ -d "$LOG_DIR" ] || { echo "log-hygiene: no logs dir at $LOG_DIR - nothing to do"; exit 0; }

rotated=0
while IFS= read -r f; do
  size_mb=$(( $(wc -c < "$f") / 1024 / 1024 ))
  [ "$size_mb" -ge "$LIMIT_MB" ] || continue
  stamp="$(date +%Y%m%d-%H%M%S)"
  archive="$f.$stamp.gz"
  # keep the tail live so a tail -f consumer (and the Logs tab) is not blinded,
  # and archive the whole thing first: compress, verify, only then truncate.
  gzip -c "$f" > "$archive" || { echo "log-hygiene: failed to archive $f" >&2; continue; }
  gzip -t "$archive" || { echo "log-hygiene: archive of $f is corrupt, keeping original" >&2; rm -f "$archive"; continue; }
  tail -n "$KEEP_TAIL_LINES" "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  echo "log-hygiene: rotated $(basename "$f") (${size_mb}MB) -> $(basename "$archive"), kept last $KEEP_TAIL_LINES lines"
  rotated=$(( rotated + 1 ))
done < <(find "$LOG_DIR" -maxdepth 1 -type f -name "*.log" 2>/dev/null)

echo "log-hygiene: ${rotated} log(s) over ${LIMIT_MB}MB rotated"
