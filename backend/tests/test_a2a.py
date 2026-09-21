"""A2A endpoint tests.

Isolation model, and why it is built this way
--------------------------------------------
Two things have to be true at once, and they pull in opposite directions:

* the DATA must be synthetic and disposable, so a test can assert exact counts
  and can never be perturbed by (or perturb) Bruno's live ecosystem;
* the PARSER must be the real canonical script, because the entire design claim
  of ``dashboard/a2a.py`` is "we do not re-implement A2A parsing". A vendored
  copy of the reader would satisfy the test while the claim silently rotted.

So each fixture builds a throwaway ecosystem under ``tmp_path`` and COPIES the
real ``read-handoffs.py`` / ``read-discoveries.py`` into its ``scripts/``. Real
code, synthetic input, nothing outside ``tmp_path`` is read or written. If the
canonical scripts are not installed on this machine the module skips with the
reason rather than passing vacuously.

Timestamps are generated relative to real ``utcnow`` because the canonical
readers call ``datetime.now(timezone.utc)`` internally to derive ``stale`` and
TTL expiry. Freezing the clock here would not reach inside them.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.a2a import CANONICAL_SCRIPTS, A2APaths, build_payload, worker_health
from dashboard.config import Settings, get_settings
from dashboard.main import create_app

CANONICAL_SRC = Path.home() / ".kiro" / "agents" / "scripts"

pytestmark = pytest.mark.skipif(
    not all((CANONICAL_SRC / f).is_file() for f in CANONICAL_SCRIPTS.values()),
    reason=f"canonical A2A readers not installed in {CANONICAL_SRC}",
)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now() -> datetime:
    return datetime.now(UTC)


def queue_item(path: Path, ident: str, *, a2a: bool = True, agent: str = "beta-agent") -> None:
    """Write a delivery-queue item in handoff.sh's exact shape."""
    item: dict = {
        "id": ident,
        "agent": agent,
        "input": f"A2A handoff for {ident}",
        "priority": "medium",
        "created": iso(now()),
        "status": path.parent.name,
    }
    if a2a:
        item["params"] = {
            "source": "a2a-handoff",
            "handoff_id": ident,
            "from": "alpha-agent",
            "skill": "do-thing",
            "expected_output": "a verified result",
            "timeout_sec": 600,
            "acceptance_pattern": None,
        }
    path.write_text(json.dumps(item, indent=2))


@pytest.fixture()
def a2a_env(tmp_path: Path) -> Settings:
    """Throwaway ecosystem with real canonical readers and known A2A state.

    Handoff scenarios, one per interesting branch:
      h-done      done, queue item in done            -> healthy
      h-live      pending, inside timeout, queued     -> pending
      h-stale     pending, past timeout, NOT queued   -> canonical stale + orphan drift
      h-failed    failed, queue item in failed        -> failed
      h-evented   two events (pending then done)      -> latest wins
      h-untracked queue item only, no audit line      -> untracked drift
    """
    agents = tmp_path / "agents"
    state = tmp_path / "agents-state"
    (agents / "scripts").mkdir(parents=True)
    (agents / "shared-memory").mkdir()
    (agents / "logs").mkdir()
    (state / "shared-memory").mkdir(parents=True)
    for st in ("pending", "running", "done", "failed"):
        (state / "queue" / st).mkdir(parents=True)

    # Real canonical readers, copied fresh - no vendored duplicate to drift.
    for filename in CANONICAL_SCRIPTS.values():
        shutil.copy2(CANONICAL_SRC / filename, agents / "scripts" / filename)

    t = now()
    handoffs = [
        {"id": "h-done", "ts": iso(t - timedelta(minutes=30)), "from": "alpha-agent",
         "to": "beta-agent", "skill": "do-thing", "input": {"k": 1, "j": 2},
         "expected_output": "result", "timeout_sec": 600, "trace_id": "tr-1",
         "status": "done", "result": "completed; acceptance matched"},
        {"id": "h-live", "ts": iso(t - timedelta(seconds=30)), "from": "alpha-agent",
         "to": "beta-agent", "skill": "do-thing", "input": {},
         "expected_output": "result", "timeout_sec": 600, "trace_id": "tr-2",
         "status": "pending", "result": None},
        # timeout_sec 60 but requested 2h ago -> canonical must derive `stale`
        {"id": "h-stale", "ts": iso(t - timedelta(hours=2)), "from": "alpha-agent",
         "to": "gamma-agent", "skill": "slow-thing", "input": {},
         "expected_output": "result", "timeout_sec": 60, "trace_id": "tr-3",
         "status": "pending", "result": None},
        {"id": "h-failed", "ts": iso(t - timedelta(minutes=10)), "from": "beta-agent",
         "to": "alpha-agent", "skill": "break-thing", "input": {},
         "expected_output": "result", "timeout_sec": 600, "trace_id": "tr-4",
         "status": "failed", "result": "boom"},
        # event-sourced pair: request first, completion later, same id
        {"id": "h-evented", "ts": iso(t - timedelta(minutes=20)), "from": "alpha-agent",
         "to": "beta-agent", "skill": "two-phase", "input": {},
         "expected_output": "result", "timeout_sec": 600, "trace_id": "tr-5",
         "status": "pending", "result": None},
        {"id": "h-evented", "ts": iso(t - timedelta(minutes=5)),
         "status": "done", "result": "second event wins"},
    ]
    (agents / "shared-memory" / "handoffs.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in handoffs))

    discoveries = [
        {"ts": iso(t - timedelta(hours=3)), "from": "meta-agent",
         "topic": "broadcast-topic", "content": "everyone should know", "ttl_days": 30},
        {"ts": iso(t - timedelta(hours=2)), "from": "alpha-agent", "to": ["agent-pm"],
         "topic": "targeted-acked", "content": "for agent-pm", "ttl_days": 30},
        {"ts": iso(t - timedelta(hours=1)), "from": "alpha-agent", "to": ["agent-pm"],
         "topic": "targeted-unacked", "content": "newer than the cursor", "ttl_days": 30},
        {"ts": iso(t - timedelta(hours=1)), "from": "alpha-agent", "to": ["never-acked-agent"],
         "topic": "never-consumed", "content": "no cursor exists", "ttl_days": 30},
        # ttl_days 1 but 40 days old -> canonical must drop it as expired
        {"ts": iso(t - timedelta(days=40)), "from": "old-agent",
         "topic": "expired-topic", "content": "should be filtered", "ttl_days": 1},
    ]
    (agents / "shared-memory" / "discoveries.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in discoveries))

    # agent-pm acked through the SECOND discovery, so it is 1 behind.
    (state / "shared-memory" / "discovery-watermarks.json").write_text(
        json.dumps({"agent-pm": iso(t - timedelta(hours=2))}, indent=2))

    q = state / "queue"
    queue_item(q / "done" / "h-done.json", "h-done")
    queue_item(q / "pending" / "h-live.json", "h-live")
    queue_item(q / "failed" / "h-failed.json", "h-failed")
    queue_item(q / "done" / "h-evented.json", "h-evented")
    queue_item(q / "done" / "h-untracked.json", "h-untracked")
    # ordinary backlog item sharing the queue - must never count as A2A
    queue_item(q / "pending" / "backlog-999.json", "backlog-999", a2a=False)

    return Settings(agents_dir=agents, supervisor_service="")


@pytest.fixture()
def a2a_client(a2a_env: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: a2a_env
    return TestClient(app)


@pytest.fixture()
def bare_env(tmp_path: Path) -> Settings:
    """Ecosystem with NO canonical scripts and no A2A files at all."""
    agents = tmp_path / "agents"
    (agents / "scripts").mkdir(parents=True)
    return Settings(agents_dir=agents, supervisor_service="")


# ── Contract with the canonical scripts ──────────────────────────────
def test_a2a_contract_canonical_callables_exist(a2a_env: Settings):
    """Pins the coupling this module accepted deliberately.

    ``dashboard/a2a.py`` chose in-process import over subprocess, whose cost is
    depending on these names. If upstream renames one, this test fails with a
    clear reason instead of the page silently rendering empty.
    """
    from dashboard.a2a import canonical

    handoffs = canonical(a2a_env, "handoffs")
    discoveries = canonical(a2a_env, "discoveries")
    assert handoffs is not None and discoveries is not None
    assert callable(handoffs.latest_rows), "read-handoffs.py must expose latest_rows()"
    assert callable(discoveries.active_rows), "read-discoveries.py must expose active_rows()"
    # Private, so its absence is tolerated by a documented fallback - but if it
    # is gone we want to KNOW, because the fallback is a second code path.
    assert hasattr(discoveries, "_load_watermarks"), (
        "read-discoveries.py no longer exposes _load_watermarks; a2a.py falls back to a "
        "plain JSON read - verify the watermark file format did not change too")


def _reimplementation_hits(source: str) -> list[str]:
    """Tokens that would mean the dashboard parses A2A data itself.

    Scope matters here. An earlier version of this gate matched the FIELD NAMES
    (``ttl_days``, ``timeout_sec``) and failed on ``a2a.py`` legitimately passing
    ``ttl_days`` through for display - reading a field to render it is not
    parsing. So the gate targets the two behaviours that must stay upstream:

    * opening or reading the JSONL files directly (line-by-line decoding), and
    * date arithmetic, which is how ``stale`` and TTL expiry get derived.

    ``timedelta`` is the honest tell for the second: there is no way to re-derive
    either without it.
    """
    forbidden = (
        "handoffs_path.open", "discoveries_path.open",
        "handoffs_path.read_text", "discoveries_path.read_text",
        "timedelta", "fromisoformat",
    )
    return [token for token in forbidden if token in source]


def test_no_local_reimplementation_of_a2a_parsing():
    """Guards the requirement itself: no third parser in the dashboard."""
    source = (Path(__file__).resolve().parents[1] / "src" / "dashboard" / "a2a.py").read_text()
    assert _reimplementation_hits(source) == [], (
        "a2a.py appears to parse A2A data itself; parsing must be delegated to the "
        "canonical scripts")


def test_reimplementation_gate_would_catch_a_real_violation():
    """Control for the gate above (A/B), so a passing gate proves something.

    A gate that cannot fail is decoration. These are the two shapes a genuine
    re-implementation would take.
    """
    rolled_own_stale = (
        "if now > parse_ts(row['ts']) + timedelta(seconds=row['timeout_sec']):\n"
        "    row['status'] = 'stale'\n"
    )
    read_jsonl_directly = (
        "with settings.handoffs_path.open() as fh:\n"
        "    rows = [json.loads(line) for line in fh]\n"
    )
    assert "timedelta" in _reimplementation_hits(rolled_own_stale)
    assert "handoffs_path.open" in _reimplementation_hits(read_jsonl_directly)
    # And the legitimate case stays clean: rendering a field is not parsing.
    assert _reimplementation_hits('{"ttl_days": row.get("ttl_days", 30)}') == []


# ── Endpoint shape ───────────────────────────────────────────────────
def test_endpoint_available_and_reports_its_sources(a2a_client: TestClient, a2a_env: Settings):
    body = a2a_client.get("/api/a2a").json()
    assert body["available"] is True
    assert body["degraded"] == []
    # Paths are surfaced so the page can prove WHICH files it read.
    paths = A2APaths(a2a_env)
    assert body["sources"]["handoffs"] == str(paths.handoffs)
    assert body["sources"]["queue"] == str(paths.queue)
    assert body["sources"]["parsers"]["handoffs"].endswith("read-handoffs.py")
    assert body["sources"]["handoffs_exists"] is True


def test_api_a2a_is_not_shadowed_by_the_spa(a2a_client: TestClient):
    r = a2a_client.get("/api/a2a")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


# ── Queue counters ───────────────────────────────────────────────────
def test_queue_counters_count_only_a2a_items(a2a_client: TestClient):
    q = a2a_client.get("/api/a2a").json()["queue"]
    # pending holds h-live (A2A) + backlog-999 (not A2A)
    assert q["counts"]["pending"] == 1
    assert q["queue_totals"]["pending"] == 2, "total must still report the shared queue"
    assert q["counts"]["done"] == 3       # h-done, h-evented, h-untracked
    assert q["counts"]["failed"] == 1
    assert q["counts"]["running"] == 0
    assert q["capped"] == []


def test_queue_counters_tolerate_corrupt_and_missing(a2a_env: Settings):
    queue = A2APaths(a2a_env).queue
    (queue / "pending" / "broken.json").write_text("{not json")
    (queue / "running").rmdir()
    payload = build_payload(a2a_env)
    assert payload["queue"]["counts"]["pending"] == 1   # corrupt skipped, not fatal
    assert payload["queue"]["counts"]["running"] == 0   # missing dir is 0, not a crash


# ── Handoffs, via canonical semantics ────────────────────────────────
def test_handoff_event_sourcing_latest_event_wins(a2a_client: TestClient):
    items = {i["id"]: i for i in a2a_client.get("/api/a2a").json()["handoffs"]["items"]}
    ev = items["h-evented"]
    assert ev["status"] == "done"
    assert ev["result"] == "second event wins"
    # Routing metadata comes from the REQUEST event even though the completion
    # event omitted it - that merge is canonical behaviour we must not lose.
    assert ev["from"] == "alpha-agent"
    assert ev["to"] == "beta-agent"
    assert ev["skill"] == "two-phase"


def test_stale_is_derived_by_canonical_not_stored(a2a_client: TestClient):
    body = a2a_client.get("/api/a2a").json()
    items = {i["id"]: i for i in body["handoffs"]["items"]}
    # On disk h-stale says "pending"; canonical must promote it past timeout_sec.
    assert items["h-stale"]["status"] == "stale"
    assert items["h-live"]["status"] == "pending", "inside its timeout, must stay pending"
    assert body["handoffs"]["counts"]["stale"] == 1
    assert body["handoffs"]["counts"]["failed"] == 1


def test_handoffs_are_newest_first_and_input_is_summarized(a2a_client: TestClient):
    items = a2a_client.get("/api/a2a").json()["handoffs"]["items"]
    stamps = [i["ts"] for i in items]
    assert stamps == sorted(stamps, reverse=True), "newest-first, per canonical ordering"
    done = next(i for i in items if i["id"] == "h-done")
    assert done["has_input"] is True
    assert done["input_keys"] == ["j", "k"], "keys only - raw payload never shipped"


def test_handoff_limit_is_honoured(a2a_env: Settings):
    payload = build_payload(a2a_env, limit=2)
    assert len(payload["handoffs"]["items"]) == 2
    assert payload["handoffs"]["total"] == 5, "5 distinct ids from 6 events"
    assert payload["handoffs"]["shown"] == 2


# ── Drift between audit and transport ────────────────────────────────
def test_drift_flags_open_handoff_with_no_queue_item(a2a_client: TestClient):
    drift = {d["id"]: d for d in a2a_client.get("/api/a2a").json()["drift"]}
    assert drift["h-stale"]["kind"] == "orphan_audit"
    assert "nothing will execute it" in drift["h-stale"]["detail"]
    assert drift["h-stale"]["to"] == "gamma-agent"


def test_drift_flags_queue_item_with_no_audit_entry(a2a_client: TestClient):
    drift = {d["id"]: d for d in a2a_client.get("/api/a2a").json()["drift"]}
    assert drift["h-untracked"]["kind"] == "untracked_queue"
    assert drift["h-untracked"]["status"] == "done"


def test_healthy_handoffs_produce_no_drift(a2a_client: TestClient):
    drift_ids = {d["id"] for d in a2a_client.get("/api/a2a").json()["drift"]}
    for healthy in ("h-done", "h-live", "h-failed", "h-evented"):
        assert healthy not in drift_ids
    assert "backlog-999" not in drift_ids, "non-A2A queue items are not A2A drift"


# ── Discoveries + watermarks ─────────────────────────────────────────
def test_expired_discovery_is_filtered_by_canonical_ttl(a2a_client: TestClient):
    topics = {d["topic"] for d in a2a_client.get("/api/a2a").json()["discoveries"]["items"]}
    assert "expired-topic" not in topics, "ttl_days expiry is canonical behaviour"
    assert {"broadcast-topic", "targeted-acked", "targeted-unacked"} <= topics


def test_discovery_audience_and_truncation(a2a_env: Settings):
    long = "x" * 2000
    with A2APaths(a2a_env).discoveries.open("a") as fh:
        fh.write(json.dumps({"ts": iso(now()), "from": "a", "topic": "long",
                             "content": long, "ttl_days": 30}) + "\n")
    items = {d["topic"]: d for d in build_payload(a2a_env)["discoveries"]["items"]}
    assert items["broadcast-topic"]["broadcast"] is True
    assert items["targeted-acked"]["to"] == ["agent-pm"]
    assert items["long"]["truncated"] is True
    assert items["long"]["content_chars"] == 2000
    assert len(items["long"]["content"]) == 1200


def test_watermark_lag_is_measured_against_canonical_resume(a2a_client: TestClient):
    marks = {w["consumer"]: w for w in a2a_client.get("/api/a2a").json()["watermarks"]}
    # agent-pm acked through `targeted-acked`, so exactly `targeted-unacked` remains.
    assert marks["agent-pm"]["lag"] == 1
    assert marks["agent-pm"]["never_acked"] is False
    assert marks["agent-pm"]["watermark"] is not None


def test_addressed_consumer_without_cursor_is_visible(a2a_client: TestClient):
    marks = {w["consumer"]: w for w in a2a_client.get("/api/a2a").json()["watermarks"]}
    # Would be invisible if the panel only listed watermark-file keys.
    assert "never-acked-agent" in marks
    assert marks["never-acked-agent"]["never_acked"] is True
    # 2, not 1: canonical counts a BROADCAST discovery (no `to`) as addressed to
    # every consumer, so the backlog is `broadcast-topic` + `never-consumed`.
    # Measured against the canonical reader rather than assumed - agent-pm's lag
    # is 1 only because its cursor already sits past the broadcast.
    assert marks["never-acked-agent"]["lag"] == 2


def test_corrupt_watermark_file_degrades_to_empty(a2a_env: Settings):
    A2APaths(a2a_env).watermarks.write_text("{ broken")
    payload = build_payload(a2a_env)
    marks = {w["consumer"]: w for w in payload["watermarks"]}
    assert marks["agent-pm"]["never_acked"] is True, "unreadable cursor != acked"
    assert payload["available"] is True


# ── Degradation ──────────────────────────────────────────────────────
def test_missing_canonical_scripts_degrade_explicitly(bare_env: Settings):
    """The one outcome worse than an error is a plausible empty page."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: bare_env
    body = TestClient(app).get("/api/a2a").json()
    assert body["available"] is False
    assert len(body["degraded"]) == 2
    assert all("canonical reader not found" in d for d in body["degraded"])
    assert body["handoffs"]["items"] == []
    assert body["sources"]["handoffs_exists"] is False


def test_missing_data_files_with_readers_present(a2a_env: Settings):
    paths = A2APaths(a2a_env)
    paths.handoffs.unlink()
    paths.discoveries.unlink()
    payload = build_payload(a2a_env)
    assert payload["available"] is True, "readers exist; there is simply no traffic yet"
    assert payload["handoffs"]["items"] == []
    assert payload["discoveries"]["items"] == []
    assert payload["sources"]["handoffs_exists"] is False


def test_reader_edit_invalidates_the_module_cache(a2a_env: Settings):
    """Cache key includes mtime, so upstream edits land without a restart."""
    from dashboard.a2a import canonical

    first = canonical(a2a_env, "handoffs")
    path = a2a_env.scripts_dir / CANONICAL_SCRIPTS["handoffs"]
    path.write_text(path.read_text() + "\nSENTINEL = 42\n")
    second = canonical(a2a_env, "handoffs")
    assert getattr(second, "SENTINEL", None) == 42
    assert first is not second


def test_a2a_paths_default_to_sibling_of_agents_dir(tmp_path: Path):
    settings = Settings(agents_dir=tmp_path / "kiro" / "agents")
    paths = A2APaths(settings)
    assert paths.state == tmp_path / "kiro" / "agents-state"
    assert paths.watermarks.name == "discovery-watermarks.json"
    assert paths.queue == tmp_path / "kiro" / "agents-state" / "queue"


def test_worker_health_uses_latest_cycle_after_error(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    logs = tmp_path / "agents-state" / "logs"
    agents.mkdir()
    logs.mkdir(parents=True)
    (logs / "a2a-queue-worker-2026-09-17.log").write_text(
        "2026-09-17T20:00:00-03:00 END started=0\n"
    )
    (logs / "supervisor.log").write_text(
        "2026-09-17 18:15:55,020 WARNING A2A_DRAIN: worker error=timed out after 15 seconds\n"
    )

    status = worker_health(Settings(agents_dir=agents))

    assert status == {
        "healthy": True,
        "last_cycle_at": "2026-09-17T20:00:00-03:00",
        "last_cycle_started": 0,
        "last_error_at": "2026-09-17 18:15:55,020",
        "last_error": "timed out after 15 seconds",
    }

    (logs / "supervisor.log").write_text(
        "2026-09-17 20:15:55,020 WARNING A2A_DRAIN: worker error=new timeout\n"
    )
    assert worker_health(Settings(agents_dir=agents))["healthy"] is False
