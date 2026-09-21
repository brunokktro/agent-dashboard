# A2A observability

Dashboard route: `/a2a`. API: `GET /api/a2a`.

## Data contracts

| Artifact | Root | Shape |
|---|---|---|
| `shared-memory/handoffs.jsonl` | agents | append-only audit, event-sourced, latest status/result wins |
| `shared-memory/discoveries.jsonl` | agents | `{ts, from, to?, topic, content, ttl_days}`; no `to` means broadcast |
| `queue/{pending,running,done,failed}/*.json` | agents-state | real transport; A2A has `params.source=a2a-handoff` |
| `shared-memory/discovery-watermarks.json` | agents-state | `{consumer: ts}` cursors |

Paths derive from `DASHBOARD_AGENTS_DIR`: audit/readers under that root; state under its sibling
`agents-state`. The adapter deliberately does not modify shared `Settings`, so it can coexist with
independent config migration.

## Canonical parser delegation

The dashboard imports `scripts/read-handoffs.py` (`latest_rows`) and
`scripts/read-discoveries.py` (`active_rows`, `_load_watermarks`) by path. It does not implement a
third parser. Important semantics:

- `stale` is derived from `timeout_sec`, not stored;
- latest event wins for status/result, request event wins for `from`/`to`/`skill`;
- discoveries expire by TTL and watermarks affect per-consumer lag;
- missing readers produce explicit degraded state, never plausible empty data.

Module cache includes reader mtime, so canonical changes are picked up without backend restart. A
test pins callable names to fail loudly on upstream rename.

## Page

- A2A vs total queue counters per status;
- audit/transport drift (`orphan_audit`, `untracked_queue`);
- latest handoffs with status tally;
- discoveries with broadcast/targeted and TTL;
- consumer watermarks, lag and never-acked;
- source paths/parsers used.

Every status uses icon + text, never colour alone. The page refetches every 10 seconds.

## Validation

23 isolated backend tests use synthetic data plus the real canonical readers. Frontend build passes.
Full backend suite currently has unrelated failures from an uncommitted state-root migration in the
main worktree; A2A suite is green independently.
