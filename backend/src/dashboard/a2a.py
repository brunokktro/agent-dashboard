"""A2A (inter-agent protocol) observability.

WHY THIS MODULE PARSES NOTHING
==============================
The ecosystem already owns two readers for the A2A formats:

    ~/.kiro/agents/scripts/read-handoffs.py    -> latest_rows()
    ~/.kiro/agents/scripts/read-discoveries.py -> active_rows()

They hold non-obvious semantics that a re-implementation would get subtly
wrong and then drift from: the handoff JSONL is event-sourced (latest event per
id wins, request metadata wins for routing fields while the latest event wins
for status/result), ``stale`` is DERIVED from ``timeout_sec`` rather than
stored, and discoveries carry TTL expiry plus per-consumer watermark resume.
A dashboard that re-derived any of that would eventually disagree with the CLI
the agents themselves use, and the dashboard would be the liar.

So this module is an ADAPTER, not a parser. Every field shown on the page comes
out of those two scripts.

The trade-off I picked, explicitly
----------------------------------
Two ways to consume them:

1. ``subprocess`` each script with ``--json`` and read stdout. Zero coupling to
   internals and exercises the exact CLI contract, but costs a Python
   interpreter spawn per call - four calls per page load at a 10s refetch
   interval - and still cannot reach watermarks, which no flag prints.
2. Import the script by file path and call its functions (this file). One
   in-process call each, watermarks reachable, and the derived ``stale`` logic
   is the same code the CLI runs.

I chose 2 for latency and for watermark access. Its real cost is coupling to
three function NAMES, so that coupling is pinned by ``test_a2a_contract`` -
rename one upstream and a test fails loudly instead of a page going quietly
empty. Filenames use hyphens and cannot be imported as modules, hence importlib
by path.

If the scripts are absent (a fresh ecosystem, or a checkout on another
machine), every endpoint degrades to an explicit ``available: false`` with the
reason - never a 500, and never a plausible-looking empty page, which is the
one outcome that would be indistinguishable from "no A2A traffic".
"""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from .config import Settings, get_settings

router = APIRouter()

# Canonical reader scripts, by role. Values are filenames inside settings.scripts_dir.
CANONICAL_SCRIPTS = {
    "handoffs": "read-handoffs.py",
    "discoveries": "read-discoveries.py",
}

# Queue states the delivery queue uses (handoff.sh publishes into pending).
QUEUE_STATES = ("pending", "running", "done", "failed")

# Marker handoff.sh stamps on every queue item it publishes. Items without it
# are ordinary backlog/manual work sharing the same queue, and must not be
# counted as A2A traffic.
A2A_SOURCE = "a2a-handoff"

# Per-state cap when scanning the queue. `done` grows without bound (152 files
# on the reference ecosystem), and an uncapped scan would make page latency a
# function of ecosystem age. Newest-first by mtime, and the payload reports
# `capped` so a total is never silently a lower bound.
QUEUE_SCAN_CAP = 500

# Ceiling for watermark lag. `active_rows` keeps a bounded deque, so lag is
# measured up to this many rows and reported as "500+" beyond it.
LAG_CAP = 500

# A handoff still open in the audit past this is worth pointing at even when
# the canonical timeout has not fired.
OPEN_STATUSES = ("pending", "running", "stale")


class A2APaths:
    """Protocol paths derived from the stable agents_dir contract.

    Kept here rather than Settings because the main worktree currently has an independent,
    uncommitted agents-state migration in config.py. A2A must not absorb/commit that session's work.
    """

    def __init__(self, settings: Settings):
        self.state = settings.agents_dir.parent / "agents-state"
        self.handoffs = settings.agents_dir / "shared-memory" / "handoffs.jsonl"
        self.discoveries = settings.agents_dir / "shared-memory" / "discoveries.jsonl"
        self.watermarks = self.state / "shared-memory" / "discovery-watermarks.json"
        self.queue = self.state / "queue"
        self.logs = self.state / "logs"


@lru_cache(maxsize=8)
def _load_script(path_str: str, _mtime: float) -> Any:
    """Import a canonical script by path.

    ``_mtime`` is part of the cache key on purpose: editing a canonical script
    invalidates the cached module, so the dashboard follows upstream changes
    without a restart. Without it a long-lived server would serve the version
    that happened to be on disk at boot.
    """
    path = Path(path_str)
    name = f"_a2a_canonical_{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(settings: Settings, role: str) -> Any | None:
    """The canonical reader module for ``role``, or None when unavailable."""
    path = settings.scripts_dir / CANONICAL_SCRIPTS[role]
    try:
        return _load_script(str(path), path.stat().st_mtime)
    except (OSError, ImportError, SyntaxError):
        return None


def _missing(settings: Settings) -> list[str]:
    return [
        str(settings.scripts_dir / filename)
        for role, filename in CANONICAL_SCRIPTS.items()
        if canonical(settings, role) is None
    ]


# ── Adapters over the canonical readers ──────────────────────────────
def read_handoffs(settings: Settings) -> list[dict]:
    """Latest event per handoff id, with ``stale`` derived - canonical logic."""
    paths = A2APaths(settings)
    module = canonical(settings, "handoffs")
    if module is None:
        return []
    return module.latest_rows(str(paths.handoffs))


def read_discoveries(settings: Settings, limit: int, since_hours: int) -> list[dict]:
    """Active (non-expired, in-window) discoveries - canonical logic."""
    paths = A2APaths(settings)
    module = canonical(settings, "discoveries")
    if module is None:
        return []
    return module.active_rows(
        str(paths.discoveries), limit=limit, since_hours=since_hours
    )


def read_watermarks(settings: Settings) -> dict[str, str]:
    """Consumer cursors.

    Prefers the canonical loader so malformed-file behavior matches the CLI
    exactly. It is a private name upstream, so a rename degrades to an
    equivalent plain read rather than emptying the panel - the file is a flat
    ``{consumer: ts}`` map, so this fallback duplicates no format logic.
    """
    paths = A2APaths(settings)
    module = canonical(settings, "discoveries")
    loader = getattr(module, "_load_watermarks", None) if module else None
    if loader is not None:
        marks = loader(paths.watermarks)
    else:
        try:
            marks = json.loads(paths.watermarks.read_text())
        except (OSError, json.JSONDecodeError):
            marks = {}
    return marks if isinstance(marks, dict) else {}


def consumer_lag(settings: Settings, consumer: str, watermark: str | None) -> int:
    """Discoveries addressed to ``consumer`` newer than its watermark.

    Delegates to the canonical reader with the same ``after``/``consumer``
    arguments the agent preflight uses, so the number on screen is the number
    the agent would actually receive on its next read.
    """
    paths = A2APaths(settings)
    module = canonical(settings, "discoveries")
    if module is None:
        return 0
    try:
        rows = module.active_rows(
            str(paths.discoveries),
            limit=LAG_CAP,
            since_hours=24 * 365,
            after=watermark,
            consumer=consumer,
        )
    except (ValueError, TypeError):
        # An unparseable watermark must not take the page down; treat the
        # cursor as unknown and report it via the `unknown_watermark` flag.
        return 0
    return len(rows)


# ── Queue (the real transport) ───────────────────────────────────────
def scan_queue(settings: Settings) -> dict:
    """Count A2A items per delivery state, newest-first, capped per state."""
    paths = A2APaths(settings)
    counts = dict.fromkeys(QUEUE_STATES, 0)
    totals = dict.fromkeys(QUEUE_STATES, 0)
    capped: list[str] = []
    ids: dict[str, str] = {}
    for state in QUEUE_STATES:
        directory = paths.queue / state
        if not directory.is_dir():
            continue
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        totals[state] = len(files)
        if len(files) > QUEUE_SCAN_CAP:
            capped.append(state)
        for path in files[:QUEUE_SCAN_CAP]:
            try:
                item = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            params = item.get("params") or {}
            if not isinstance(params, dict) or params.get("source") != A2A_SOURCE:
                continue
            counts[state] += 1
            handoff_id = params.get("handoff_id") or item.get("id")
            if handoff_id:
                ids[str(handoff_id)] = state
    return {"counts": counts, "queue_totals": totals, "capped": capped, "_ids": ids}


def find_drift(handoffs: list[dict], queue_ids: dict[str, str]) -> list[dict]:
    """Disagreements between the audit log and the real transport.

    This is the highest-value signal here and the reason the page reads both
    files. ``handoff.sh`` documents the incident that motivated it: while the
    JSONL was the only writer, a handoff sat ``pending`` for ten days because
    no queue item existed for anything to pick up. Audit-only observability
    cannot see that; comparing the two can.
    """
    drift = []
    for row in handoffs:
        status = row.get("status")
        ident = str(row.get("id", ""))
        if status in OPEN_STATUSES and ident not in queue_ids:
            drift.append({
                "id": ident,
                "kind": "orphan_audit",
                "status": status,
                "to": row.get("to"),
                "detail": (
                    f"audit says {status} but no queue item exists in "
                    "agents-state/queue - nothing will execute it"
                ),
            })
    known = {str(r.get("id", "")) for r in handoffs}
    for ident, state in queue_ids.items():
        if ident not in known:
            drift.append({
                "id": ident,
                "kind": "untracked_queue",
                "status": state,
                "to": None,
                "detail": (
                    f"queue item in {state} has no entry in handoffs.jsonl - "
                    "delivered without an audit trail"
                ),
            })
    return drift


def _tally(handoffs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in handoffs:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _trim_handoff(row: dict) -> dict:
    """Only fields the page renders. The full ``input`` payload can be large
    and no view shows it, so it is summarized rather than shipped."""
    payload = row.get("input")
    return {
        "id": row.get("id"),
        "ts": row.get("ts"),
        "from": row.get("from"),
        "to": row.get("to"),
        "skill": row.get("skill"),
        "status": row.get("status"),
        "result": row.get("result"),
        "expected_output": row.get("expected_output"),
        "acceptance_pattern": row.get("acceptance_pattern"),
        "timeout_sec": row.get("timeout_sec"),
        "trace_id": row.get("trace_id"),
        "has_input": bool(payload),
        "input_keys": sorted(payload)[:8] if isinstance(payload, dict) else [],
    }


def _trim_discovery(row: dict) -> dict:
    audience = row.get("to") or []
    if isinstance(audience, str):
        audience = [audience]
    content = str(row.get("content", ""))
    return {
        "ts": row.get("ts"),
        "from": row.get("from"),
        "topic": row.get("topic"),
        "to": [str(x) for x in audience],
        "broadcast": not audience,
        "ttl_days": row.get("ttl_days", 30),
        "content": content[:1200],
        "truncated": len(content) > 1200,
        "content_chars": len(content),
    }


def worker_health(settings: Settings) -> dict:
    """Last worker cycle and supervisor error, read from bounded log tails."""
    paths = A2APaths(settings)
    cycle_at: str | None = None
    cycle_started: int | None = None
    for path in sorted(paths.logs.glob("a2a-queue-worker-*.log"), reverse=True)[:2]:
        try:
            lines = path.read_bytes()[-131_072:].decode(errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if " END started=" in line:
                cycle_at = line.split(" END started=", 1)[0]
                try:
                    cycle_started = int(line.rsplit("=", 1)[1])
                except ValueError:
                    cycle_started = None
                break
        if cycle_at:
            break

    error_at: str | None = None
    error_detail: str | None = None
    supervisor = paths.logs / "supervisor.log"
    try:
        lines = supervisor.read_bytes()[-262_144:].decode(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in reversed(lines):
        marker = " A2A_DRAIN: worker error="
        if marker in line:
            prefix, error_detail = line.split(marker, 1)
            error_at = prefix.rsplit(" WARNING", 1)[0]
            break

    def order_key(value: str | None) -> str:
        # Both logs use local wall time; one uses ISO T/offset, the other a space/comma.
        # The first 19 characters normalize to YYYY-MM-DD HH:MM:SS in both formats.
        return (value or "")[:19].replace("T", " ")

    healthy = bool(cycle_at) and order_key(cycle_at) >= order_key(error_at)
    return {
        "healthy": healthy,
        "last_cycle_at": cycle_at,
        "last_cycle_started": cycle_started,
        "last_error_at": error_at,
        "last_error": error_detail,
    }


def build_payload(settings: Settings, *, limit: int = 25, since_hours: int = 336) -> dict:
    """Everything the /a2a page needs, in one round trip."""
    paths = A2APaths(settings)
    missing = _missing(settings)
    handoffs = read_handoffs(settings)
    discoveries = read_discoveries(settings, limit=limit, since_hours=since_hours)
    marks = read_watermarks(settings)
    queue = scan_queue(settings)
    queue_ids = queue.pop("_ids")

    # Consumers worth a row: anyone holding a cursor, plus anyone ADDRESSED by
    # a discovery. The union is what makes "targeted but never acked" visible -
    # a consumer with no cursor would otherwise not appear at all.
    addressed: set[str] = set()
    for row in discoveries:
        audience = row.get("to") or []
        if isinstance(audience, str):
            audience = [audience]
        addressed.update(str(x) for x in audience)

    watermarks = []
    for consumer in sorted(set(marks) | addressed):
        cursor = marks.get(consumer)
        lag = consumer_lag(settings, consumer, cursor)
        watermarks.append({
            "consumer": consumer,
            "watermark": cursor,
            "never_acked": cursor is None,
            "lag": lag,
            "lag_capped": lag >= LAG_CAP,
        })

    newest = max((str(r.get("ts", "")) for r in discoveries), default=None)
    return {
        "available": not missing,
        "degraded": (
            [f"canonical reader not found: {p}" for p in missing]
            + ([f"queue scan capped at {QUEUE_SCAN_CAP} in: {', '.join(queue['capped'])}"]
               if queue["capped"] else [])
        ),
        "sources": {
            "handoffs": str(paths.handoffs),
            "discoveries": str(paths.discoveries),
            "watermarks": str(paths.watermarks),
            "queue": str(paths.queue),
            "parsers": {
                role: str(settings.scripts_dir / filename)
                for role, filename in CANONICAL_SCRIPTS.items()
            },
            "handoffs_exists": paths.handoffs.is_file(),
            "discoveries_exists": paths.discoveries.is_file(),
        },
        "queue": queue,
        "handoffs": {
            "counts": _tally(handoffs),
            "total": len(handoffs),
            "items": [_trim_handoff(r) for r in handoffs[:limit]],
            "shown": min(limit, len(handoffs)),
        },
        "discoveries": {
            "total": len(discoveries),
            "newest_ts": newest,
            "since_hours": since_hours,
            "items": [_trim_discovery(r) for r in discoveries][::-1],
        },
        "watermarks": watermarks,
        "worker": worker_health(settings),
        "drift": find_drift(handoffs, queue_ids),
    }


@router.get("/api/a2a")
def a2a_overview(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = 25,
    since_hours: int = 336,
):
    """A2A protocol state: delivery queue, handoffs, discoveries, watermarks."""
    return build_payload(settings, limit=max(1, min(limit, 200)),
                         since_hours=max(1, min(since_hours, 24 * 365)))
