# Design Decisions - Dashboard v3

> Session log of architectural decisions. Newest first.

## 2026-08-06 - Foundation session (supersedes ALL `backlog/dashboard-v3-*` items and `~/.kiro/specs/dashboard-v3/`)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Public GitHub repo from day 1** | Best practices enforced by design: no hardcoded paths/usernames (all config via `DASHBOARD_*` env vars), MIT license, CI |
| 2 | **Backend stays Python** (FastAPI, modern: uv + pyproject + pydantic v2 + ruff + full typing) | The agent ecosystem it observes is Python; rewriting the data layer in TS would duplicate logic. Python 3.12+ |
| 3 | **Frontend: React + Vite + TypeScript + Tailwind + shadcn/ui** (replaces the April HTMX/Jinja2 plan) | Requirement changed: public repo + market-grade UX. Build step accepted (`npm run build` → FastAPI serves `dist/`) |
| 4 | **API-first, JSON only** | Backend has zero HTML. React consumes `/api/*`. OpenAPI docs free via FastAPI |
| 5 | **Dashboard is a CONSUMER of the ecosystem data** | runs.db, queue/, schedule.json, locks/ are owned by the supervisor/scripts. v3 reads; only writes are queue transitions + alert acks. Datastore is the single adapter |
| 6 | **Keep SQLite + file contracts** | Local single-user tool; Postgres/Redis would be over-engineering. Observability phase adds columns additively/idempotently |
| 7 | **Chat embedded: CUT** | [KiroCrew](https://github.com/kirodotdev/kirocrew) (public, launched 2026-08-05) covers chat-with-agents. No duplication |
| 8 | **xterm.js terminal: KEEP and improve** | Practical for quick commands. Improvements planned: PTY session surviving WS reconnect, keepalive, reliable resize, scrollback, search |
| 9 | **Observability UI copies Datadog patterns** | Known market standard: P50/P95/P99 timeseries, day×hour heatmap, host-map style agent grid, monitor-style alert list |
| 10 | **Test culture ported from futebol-alcance** | Real SQLite in fixtures (no MagicMock), freezegun for time, hypothesis for invariants, regression-bug-first policy, E2E never against real data |
| 11 | **v2 untouched on port 7779 until v3 reaches parity** | v3 runs on 7780. Zero risk to the running ecosystem |

### Phases

1. **F1 - Backend API** ✅ (2026-08-06): typed datastore + full JSON API + 21 tests
2. **F2 - Frontend foundation**: 6 pages (Overview, Agent, Queue, Health, Supervisor, Logs) in React/shadcn, functional parity with v2, terminal + SSE logs
3. **F3 - Real-time**: `/ws/events` single channel (run.started/completed/failed, queue.changed, log.appended, alert.raised/acked), reactive UI
4. **F4 - Observability**: Datadog-style charts, runs.db additive schema extension, instrumentation via run-agent.sh wrapper

### Salvaged from the April 2026 skeleton
Data layer logic and API contracts from `~/.kiro/agents/scripts/dashboard-v3.py` (ported with typing + config injection). Jinja2 templates kept as visual reference only.
