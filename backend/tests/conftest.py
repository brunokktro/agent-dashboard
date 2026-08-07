"""Fixtures: a REAL miniature agent ecosystem in a temp dir.

Philosophy (ported from the futebol-alcance suite): no MagicMock for data
sources - real SQLite, real queue files, real markdown specs. Mocks mask
type errors and schema drift; real artifacts catch them.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.config import Settings, get_settings
from dashboard.datastore import Datastore
from dashboard.main import create_app

NOW = datetime(2026, 8, 6, 12, 0, 0)


def make_run(conn, job_id: str, status: str = "success", *,
             hours_ago: float = 1, duration: int = 60, exit_code: int = 0):
    started = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO runs (job_id, started_at, duration_sec, status, exit_code, log_path) "
        "VALUES (?,?,?,?,?,?)",
        (job_id, started, duration, status, exit_code, f"logs/{job_id}.log"))


@pytest.fixture()
def ecosystem(tmp_path: Path) -> Settings:
    """Temp agents dir with runs.db, queue, schedule, locks and 2 agent specs."""
    agents = tmp_path / "agents"
    (agents / "logs").mkdir(parents=True)
    (agents / "scripts").mkdir()
    (agents / "locks").mkdir()
    for st in ("pending", "running", "done", "failed"):
        (agents / "queue" / st).mkdir(parents=True)

    # agent specs (frontmatter with name => detected; without => ignored)
    (agents / "alpha-agent.md").write_text(
        "---\nname: alpha-agent\ndescription: First test agent\n---\n# Alpha\n")
    (agents / "beta-agent.md").write_text(
        "---\nname: beta-agent\ndescription: Second test agent\n---\n# Beta\n")
    (agents / "README.md").write_text("# not an agent, no frontmatter\n")

    # schedule
    (agents / "scripts" / "schedule.json").write_text(json.dumps({
        "version": 1, "jobs": [
            {"id": "alpha-agent-morning", "script": "alpha.sh", "cron": "0 8 * * 1-5",
             "timeout_sec": 600, "enabled": True},
            {"id": "beta-agent", "script": "beta.sh", "cron": "0 12 * * *",
             "timeout_sec": 300, "enabled": True},
        ]}))

    # runs.db with the real schema used by the supervisor
    conn = sqlite3.connect(agents / "runs.db")
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, "
        "started_at TEXT, duration_sec INTEGER, status TEXT, exit_code INTEGER, log_path TEXT)")
    make_run(conn, "alpha-agent-morning", "success", hours_ago=2)
    make_run(conn, "alpha-agent-morning", "failed", hours_ago=26, exit_code=1)
    make_run(conn, "beta-agent", "success", hours_ago=1)
    make_run(conn, "beta-agent", "success", hours_ago=25)
    conn.commit()
    conn.close()

    # one queue item per state
    for st, extra in (("pending", {}), ("failed", {"result": "boom"}),
                      ("done", {"completedAt": NOW.isoformat()})):
        item = {"id": f"item-{st}", "agent": "alpha-agent", "input": "do something",
                "created": (NOW - timedelta(hours=1)).isoformat(), "status": st, **extra}
        (agents / "queue" / st / f"item-{st}.json").write_text(json.dumps(item))

    return Settings(agents_dir=agents, supervisor_service="")


@pytest.fixture()
def store(ecosystem: Settings) -> Datastore:
    return Datastore(ecosystem)


@pytest.fixture()
def client(ecosystem: Settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: ecosystem
    return TestClient(app)
