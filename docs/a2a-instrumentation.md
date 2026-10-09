# Instrumenting your agents for A2A

The dashboard's `/a2a` page is an **observer**. It shows inter-agent traffic; it
does not create it. To see anything there, your agents have to speak the
protocol. This guide is how you make that happen from zero.

If you only want to read the observability contract (what the page renders and
where it reads from), see [`a2a.md`](a2a.md). This document is the other half:
how an agent **produces** the traffic that page observes.

## The model in one paragraph

A2A here is a **file-based** protocol, not a network service. Two primitives:

- **Handoff** - one agent delegates a unit of work to another, durably. It lands
  in a real **delivery queue** that a worker polls, and is mirrored to an
  append-only **audit log**. The requester can state an `expected_output` and an
  `acceptance_pattern` so completion is verifiable, not vibes.
- **Discovery** - one agent publishes a reusable finding to shared memory, either
  **broadcast** (everyone) or **targeted** (named consumers). Consumers read new
  discoveries since their own **watermark** and acknowledge to advance it.

Nothing is centrally orchestrated. The queue is the transport, the JSONL files
are the audit and the knowledge bus, and the dashboard reads all of it read-only.

## Where things live

Everything derives from one root, the agents directory (`DASHBOARD_AGENTS_DIR`,
default `~/.kiro/agents`). Its sibling `-state` directory holds mutable state.

| Artifact | Path | Role |
|---|---|---|
| Audit log | `<agents>/shared-memory/handoffs.jsonl` | append-only, event-sourced |
| Discoveries | `<agents>/shared-memory/discoveries.jsonl` | knowledge bus, TTL'd |
| Delivery queue | `<agents-state>/queue/{pending,running,done,failed}/*.json` | real transport |
| Watermarks | `<agents-state>/shared-memory/discovery-watermarks.json` | per-consumer cursors |

The four protocol scripts live in `<agents>/scripts/`, which is exactly where the
dashboard's backend looks for its canonical readers. Install them with:

```bash
bin/init-ecosystem --a2a
```

This copies `handoff.sh`, `discover.sh`, `read-handoffs.py` and
`read-discoveries.py` from the repo's `scripts/a2a/` into your ecosystem, without
ever overwriting an existing copy (use `--force` to refresh, which keeps a
`.bak`). `discover.sh` needs `jq`; the readers need `python3` (>=3.9).

## Minimum viable instrumentation (from zero)

1. `bin/init-ecosystem --a2a` - land the scripts where the dashboard reads them.
2. Make each agent that can be delegated to **exist as a file**:
   `<agents>/<agent-name>.md` (or `.json`). `handoff.sh` rejects an exact-name
   miss on purpose - a fuzzy match could hand work to the wrong agent.
3. Give one agent a way to **publish** a handoff (call `handoff.sh`).
4. Give the target agent a way to **poll** the queue and mark items done/failed.
5. Optionally, have agents **publish discoveries** and **ack** them on their next run.
6. Open `/a2a` - it lights up as soon as the first handoff or discovery is written.

You do not need all six to start. One `handoff.sh` call is enough to see a row.

## Publishing a handoff

```bash
scripts/a2a/handoff.sh <from> <to> <skill> '<json_input>' \
  [timeout_sec] [expected_output] [acceptance_pattern] [idempotency_key] [max_attempts]
```

Example:

```bash
scripts/a2a/handoff.sh orchestrator report-builder generate-report \
  '{"account":"ACME","quarter":"Q3"}' \
  900 "A PDF is written to reports/ and the path is returned" \
  'reports/.+\.pdf'
```

What it does, atomically:

- writes a queue item to `<agents-state>/queue/pending/<id>.json` with
  `params.source = "a2a-handoff"` (this marker is how the dashboard tells A2A
  traffic apart from ordinary manual/backlog items sharing the same queue);
- appends the request event to `handoffs.jsonl`;
- prints the handoff `id` on stdout.

Fields worth setting:

- **`expected_output`** - a plain-language definition of done. Mandatory in the
  schema; the requester owns it, not the worker.
- **`acceptance_pattern`** - an optional regex the result must match to count as
  accepted. Use it whenever success is machine-checkable (a path, a status).
- **`idempotency_key`** - when set, re-running the same business action reuses the
  existing handoff across any state instead of enqueuing a duplicate. Set it
  whenever the same logical work could be triggered twice.
- **`timeout_sec`** - default 600. A `pending`/`running` handoff older than this is
  reported as `stale` by the reader (the status is derived, never stored).

## Consuming the queue (the worker side)

The queue is the transport, so a worker is whatever moves an item through the
states. A minimal loop:

```bash
for f in "$AGENTS_STATE/queue/pending/"*.json; do
  item=$(cat "$f")
  # only A2A items carry this marker
  [ "$(jq -r '.params.source' <<<"$item")" = "a2a-handoff" ] || continue
  mv "$f" "$AGENTS_STATE/queue/running/"
  # ... run the agent named in .agent with the prompt in .input ...
  # on success move to done/ ; on failure to failed/
done
```

Then record completion in the audit log by appending an event with the **same
`id`** and a terminal `status` (`done`/`failed`) plus a `result`. The reader
merges events per id: request metadata wins for routing fields
(`from`/`to`/`skill`), the latest event wins for `status`/`result`. A completion
event may be authored by the worker, but the handoff stays FROM the requester TO
the target.

> This repo scaffolds `run-agent.sh` / `run-scheduled.sh` (via
> `bin/init-ecosystem --runners`) for the dashboard's Run buttons. A queue worker
> is intentionally NOT scaffolded - how you execute an agent is yours to define.
> Wire the loop above into whatever runs your agents (a cron job, a launchd/systemd
> unit, a long-lived supervisor).

## Publishing and consuming discoveries

Publish (broadcast when the last argument is empty, targeted otherwise):

```bash
# broadcast
scripts/a2a/discover.sh billing-agent "rate-limit" "the API caps at 5 rps, batch in 20s windows" 30 ""
# targeted at two consumers
scripts/a2a/discover.sh billing-agent "rate-limit" "..." 30 "agent-a,agent-b"
```

Consume, resuming from your own watermark and advancing it:

```bash
python3 scripts/a2a/read-discoveries.py --consumer agent-a --ack --json
```

`--consumer` filters to rows addressed to you (plus broadcasts) and starts after
your stored cursor; `--ack` advances that cursor through the newest row returned,
atomically. Discoveries expire by `ttl_days` (default 30). On the dashboard, a
consumer that is addressed but has never acked shows as **never-acked**, and its
**lag** is how many rows it is behind.

## Data contracts

**Handoff audit event** (`handoffs.jsonl`, one JSON per line):

```json
{"id":"h1789...","ts":"2026-09-18T01:49:22Z","from":"orchestrator","to":"report-builder",
 "skill":"generate-report","input":{"account":"ACME"},"expected_output":"A PDF ...",
 "acceptance_pattern":"reports/.+\\.pdf","idempotency_key":null,"max_attempts":2,
 "timeout_sec":900,"trace_id":"tr-...","status":"pending","result":null}
```

**Discovery** (`discoveries.jsonl`, one JSON per line):

```json
{"ts":"2026-09-18T01:49:22Z","from":"billing-agent","topic":"rate-limit",
 "content":"the API caps at 5 rps","ttl_days":30,"to":["agent-a","agent-b"]}
```

`to` absent means broadcast. **Watermarks** is a flat `{consumer: ts}` map.

## How the dashboard observes it

`GET /api/a2a` (page `/a2a`) delegates parsing to the two readers you installed -
it never re-implements the format, so it cannot drift from the CLI your agents
use. It reports:

- A2A vs total queue counters per state;
- latest handoffs with a status tally;
- discoveries (broadcast/targeted, TTL);
- consumer watermarks, lag, and never-acked;
- **drift** - the highest-value signal: an `orphan_audit` (audit says open but no
  queue item exists, so nothing will execute it) or an `untracked_queue` (a queue
  item with no audit trail). This is the failure that motivated reading both files.

If the readers are absent, every field degrades to an explicit `available: false`
with the reason - never a 500, never a plausible-looking empty page.

## Portability

The scripts default to the `~/.kiro/agents` layout but honor overrides, so they
run anywhere:

- `DASHBOARD_AGENTS_DIR` - the dashboard's agents root.
- `A2A_SHARED_DIR`, `A2A_QUEUE_DIR`, `A2A_AGENTS_DIR` - per-script overrides used by
  `handoff.sh` / `discover.sh`.
- `--file` / `--state-file` on the readers point them at any path.

Nothing in these scripts is specific to one machine or one user.
