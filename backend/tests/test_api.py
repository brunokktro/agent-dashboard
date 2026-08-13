"""API contract tests via TestClient against the temp ecosystem."""

from __future__ import annotations

import json


def test_overview_shape(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"agents", "metrics", "alerts", "timeline", "schedule", "chart"}
    assert body["metrics"]["total_runs"] == 4
    assert len(body["agents"]) == 2
    assert len(body["chart"]) == 7


def test_agent_detail(client):
    r = client.get("/api/agent/alpha-agent")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["name"] == "alpha-agent"
    assert body["stats"]["total"] == 2
    assert body["job"]["id"] == "alpha-agent-morning"


def test_agent_404(client):
    assert client.get("/api/agent/ghost").status_code == 404


def test_queue_endpoint(client):
    r = client.get("/api/queue")
    body = r.json()
    assert body["counts"]["pending"] == 1
    assert all(not k.startswith("_") for item in body["items"] for k in item)


def test_health_sorted_worst_first(client):
    body = client.get("/api/health").json()
    scores = [a["score"] for a in body["agents"] if a["total"] > 0]
    assert scores == sorted(scores)


def test_logs_endpoint(client):
    assert client.get("/api/logs").json() == {"files": []}


def test_ack_alerts(client):
    r = client.post("/api/alerts/ack", json={"ids": ["10", "11"]})
    assert r.json()["ok"] is True
    # persisted: second call accumulates
    r = client.post("/api/alerts/ack", json={"ids": ["12"]})
    assert r.json()["acked"] == 3


def test_queue_retry_moves_failed_to_pending(client, ecosystem):
    r = client.post("/api/queue/retry/item-failed")
    assert r.json()["ok"] is True
    pending = ecosystem.queue_dir / "pending" / "item-failed.json"
    assert pending.exists()
    item = json.loads(pending.read_text())
    assert item["status"] == "pending"
    assert "result" not in item
    assert not (ecosystem.queue_dir / "failed" / "item-failed.json").exists()


def test_queue_cancel_moves_pending_to_done(client, ecosystem):
    r = client.post("/api/queue/cancel/item-pending")
    assert r.json()["ok"] is True
    done = ecosystem.queue_dir / "done" / "item-pending.json"
    assert done.exists()
    assert json.loads(done.read_text())["status"] == "cancelled"


def test_enqueue_creates_pending_item(client, ecosystem):
    r = client.post("/api/queue/enqueue",
                    json={"agent": "beta-agent", "input": "test task"})
    body = r.json()
    assert body["ok"] is True
    assert (ecosystem.queue_dir / "pending" / f"{body['id']}.json").exists()


def test_enqueue_validates_empty(client):
    assert client.post("/api/queue/enqueue",
                       json={"agent": " ", "input": ""}).status_code == 422


def test_supervisor_endpoint(client):
    body = client.get("/api/supervisor").json()
    assert body["status"] == "unknown"  # no service configured in tests
    assert body["total_runs"] == 4
    assert len(body["schedule"]) == 2


def test_observability_agent(client):
    body = client.get("/api/observability/agent/alpha-agent").json()
    assert body["agent"] == "alpha-agent"
    keys = {"date", "p50", "p95", "p99", "runs", "success_rate"}
    assert all(keys <= set(s) for s in body["series"])
    for s in body["series"]:
        assert s["p50"] <= s["p95"] <= s["p99"]


def test_observability_heatmap(client):
    body = client.get("/api/observability/heatmap").json()
    assert all(0 <= c["dow"] <= 6 and 0 <= c["hour"] <= 23 for c in body["cells"])
    assert sum(c["runs"] for c in body["cells"]) == 4


def test_queue_retry_when_filename_differs_from_id(client, ecosystem):
    """Regression: real queue files often have filename != item id (HTTP 404 bug)."""
    import json as _json
    f = ecosystem.queue_dir / "failed" / "some-other-filename.json"
    f.write_text(_json.dumps({"id": "mnzx1h6c", "agent": "alpha-agent",
                              "input": "x", "status": "failed", "created": "2026-08-06T00:00:00"}))
    r = client.post("/api/queue/retry/mnzx1h6c")
    assert r.status_code == 200
    assert not f.exists()
    assert (ecosystem.queue_dir / "pending" / "mnzx1h6c.json").exists()


def test_trigger_without_runner_script_is_a_clear_error(client, ecosystem):
    """Regression (field report): fresh clones have no run-agent.sh /
    run-scheduled.sh (they belong to the observed ecosystem, not this repo).
    Triggering must explain that, not crash with an opaque 500."""
    r = client.post("/api/trigger-agent/alpha-agent")
    assert r.status_code == 503
    assert "run-agent.sh" in r.json()["detail"]

    r = client.post("/api/trigger/alpha-agent-morning")
    assert r.status_code == 503
    assert "run-scheduled.sh" in r.json()["detail"]


def test_diagnose_uses_configured_extra_hints(ecosystem):
    """Site-specific failure patterns (internal auth tools etc.) come from
    DASHBOARD_EXTRA_HINTS config - the public code stays generic."""
    import sqlite3

    from fastapi.testclient import TestClient

    from dashboard.config import Settings, get_settings
    from dashboard.main import create_app

    log = ecosystem.agents_dir / "logs" / "alpha-agent-morning.log"
    log.write_text("[2026-08-06 10:00:00] ERROR: corp-sso session expired\n")
    conn = sqlite3.connect(ecosystem.agents_dir / "runs.db")
    conn.execute(
        "INSERT INTO runs (job_id, started_at, duration_sec, status, exit_code, log_path) "
        "VALUES (?,?,?,?,?,?)",
        ("alpha-agent-morning", "2026-08-06 10:00:00", 5, "failed", 1,
         "logs/alpha-agent-morning.log"))
    run_id = conn.execute("SELECT MAX(id) FROM runs").fetchone()[0]
    conn.commit()
    conn.close()

    s = Settings(agents_dir=ecosystem.agents_dir, supervisor_service="",
                 extra_hints=[["corp-sso", "Corporate SSO expired - re-authenticate"]])
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: s
    r = TestClient(app).get(f"/api/runs/{run_id}/diagnose")
    assert r.status_code == 200
    assert "Corporate SSO expired - re-authenticate" in r.json()["hints"]
