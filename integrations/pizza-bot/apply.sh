#!/usr/bin/env bash
# Applies the Kiro bridge patch to a Pizza Bot checkout so the dashboard's /pizza tab is usable.
# Usage: apply.sh [path-to-pizza-bot-checkout]   (default: ../pizza-bot relative to the repo root)
#
# Without this patch the tab still renders the upstream inbox, but nothing can reach it: the bridge
# endpoints the agents publish through do not exist upstream.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/kiro-bridge.patch"
TARGET="${1:-$(cd "$HERE/../.." && pwd)/../pizza-bot}"

# shellcheck disable=SC1091
source "$HERE/UPSTREAM"

die() { echo "error: $*" >&2; exit 1; }

[ -f "$PATCH" ] || die "patch missing at $PATCH"
# A worktree's .git is a file, not a directory, so ask git instead of guessing.
git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 \
  || die "$TARGET is not a git checkout. Clone $repo first."

cd "$TARGET" || die "cannot enter $TARGET"

# A patch applied to the wrong project produces confusing rejects rather than an honest failure.
actual_remote="$(git remote get-url origin 2>/dev/null || echo "")"
case "$actual_remote" in
  *pizza-bot-app/pizza-bot*) ;;
  "") echo "warning: $TARGET has no origin; continuing" >&2 ;;
  *) die "$TARGET origin is '$actual_remote', expected $repo" ;;
esac

if git apply --reverse --check "$PATCH" >/dev/null 2>&1; then
  echo "already applied: $TARGET is at the bridged state, nothing to do"
  exit 0
fi

if ! git merge-base --is-ancestor "$base" HEAD 2>/dev/null; then
  echo "warning: $base_short ($base_subject) is not an ancestor of HEAD." >&2
  echo "         The patch was produced against it; expect conflicts elsewhere." >&2
fi

git apply --check "$PATCH" || die "patch does not apply cleanly to $(git rev-parse --short HEAD). Check out $base_short and retry."
git apply "$PATCH" || die "patch failed mid-apply; the tree may be partially modified"

cat <<EOF
applied to $TARGET

next:
  cd "$TARGET"
  npm install
  npm run build && npm run backend:bundle
  PORT=7782 node dist/backend/start.mjs

Do NOT run 'npm run dev' unless you want the Electron desktop shell; the dashboard embeds the
headless backend only, and the first Electron launch downloads a ~295MB binary.
EOF
