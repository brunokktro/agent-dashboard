"""Dashboard queue cancel: queue and A2A audit settle together (handoff h179187330957672).

The endpoint delegates to the REAL ``queue_lifecycle.py`` copied fresh into the fixture's
``scripts/`` (same rule as test_a2a: a vendored copy would pass while the contract rotted). When the
canonical module is not installed on this machine, the delegated cases skip with the reason.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.a2a import LIFECYCLE_SCRIPT, _load_script
from dashboard.config import Settings, get_settings
from dashboard.main import create_app

CANONICAL_SRC = Path.home() / ".kiro" / "agents" / "scripts"
REAL_QUEUE = Path.home() / ".kiro" / "agents-state" / "queue"
REAL_AUDIT = Path.home() / ".kiro" / "agents" / "shared-memory" / "handoffs.jsonl"
FIX = "h8880"


def _real_state() -> tuple[set[str], str]:
    names = {p.name for p in REAL_QUEUE.rglob("*.json")} if REAL_QUEUE.exists() else set()
    digest = "absent"
    if REAL_AUDIT.exists():
        digest = hashlib.sha256(REAL_AUDIT.read_bytes()).hexdigest()
    return names, digest


@pytest.fixture(scope="module", autouse=True)
def _real_untouched():
    before = _real_state()
    yield
    after = _real_state()
    leaked = [n for n in after[0] - before[0] if n.startswith(FIX)]
    assert not leaked, f"fixture item leaked into the real queue: {leaked}"
    assert after[1] == before[1], "the real handoffs audit changed"


def _env(tmp_path: Path, with_lifecycle: bool) -> Settings:
    agents, state = tmp_path / "agents", tmp_path / "agents-state"
    (agents / "scripts").mkdir(parents=True)
    (agents / "shared-memory").mkdir()
    (state / "locks").mkdir(parents=True)
    for st in ("pending", "running", "done", "failed"):
        (state / "queue" / st).mkdir(parents=True)
    (agents / "shared-memory" / "handoffs.jsonl").write_text("")
    if with_lifecycle:
        if not (CANONICAL_SRC / LIFECYCLE_SCRIPT).is_file():
            pytest.skip(f"canonical {LIFECYCLE_SCRIPT} not installed in {CANONICAL_SRC}")
        shutil.copy2(CANONICAL_SRC / LIFECYCLE_SCRIPT, agents / "scripts" / LIFECYCLE_SCRIPT)
    return Settings(agents_dir=agents, supervisor_service="")


def _client(settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _seed(s: Settings, ident: str, a2a: bool = True, state: str = "pending") -> Path:
    item = {"id": ident, "agent": "devex-agent", "status": state, "attempts": 0,
            "created": "2026-10-13T06:00:00+00:00"}
    if a2a:
        item["params"] = {"source": "a2a-handoff", "handoff_id": ident, "from": "agent-pm"}
    path = s.queue_dir / state / f"{ident}.json"
    path.write_text(json.dumps(item, indent=2))
    return path


def _audit(s: Settings) -> Path:
    return s.agents_dir / "shared-memory" / "handoffs.jsonl"


def _events(s: Settings, ident: str) -> list[dict]:
    return [r for r in map(json.loads, _audit(s).read_text().splitlines()) if r["id"] == ident]


def _one_terminal_event(s: Settings, ident: str) -> bool:
    ev = _events(s, ident)
    return (len(ev) == 1 and ev[0]["status"] == "canceled"
            and ev[0]["to"] == "agent-pm" and ev[0]["ts"].endswith("Z"))


def _module(s: Settings):
    path = s.scripts_dir / LIFECYCLE_SCRIPT
    return _load_script(str(path), path.stat().st_mtime)


def test_a2a_cancel_writes_exactly_one_terminal_event(tmp_path):
    s = _env(tmp_path, True)
    _seed(s, f"{FIX}1")
    r = _client(s).post(f"/api/queue/cancel/{FIX}1")
    assert r.status_code == 200 and r.json() == {"ok": True, "state": "canceled"}
    rec = json.loads((s.queue_dir / "done" / f"{FIX}1.json").read_text())
    assert rec["status"] == "canceled"
    assert datetime.fromisoformat(rec["completedAt"]).utcoffset().total_seconds() == 0
    assert not (s.queue_dir / "pending" / f"{FIX}1.json").exists()
    assert _one_terminal_event(s, f"{FIX}1")
    assert not (s.lock_dir / f"{FIX}1.lock").exists()


def test_non_a2a_cancel_invents_no_handoff(tmp_path):
    s = _env(tmp_path, True)
    _seed(s, f"{FIX}2", a2a=False)
    assert _client(s).post(f"/api/queue/cancel/{FIX}2").json()["ok"] is True
    assert json.loads((s.queue_dir / "done" / f"{FIX}2.json").read_text())["status"] == "canceled"
    assert _audit(s).read_text() == ""


def test_repeated_cancel_is_idempotent_and_does_not_duplicate(tmp_path):
    s = _env(tmp_path, True)
    _seed(s, f"{FIX}3")
    c = _client(s)
    assert c.post(f"/api/queue/cancel/{FIX}3").status_code == 200
    again = c.post(f"/api/queue/cancel/{FIX}3")
    assert again.status_code == 200
    assert again.json() == {"ok": True, "state": "canceled", "already": True}
    assert len(_events(s, f"{FIX}3")) == 1


def test_legacy_cancelled_record_reads_as_already_canceled(tmp_path):
    s = _env(tmp_path, True)
    path = _seed(s, f"{FIX}4", state="done")
    path.write_text(json.dumps({**json.loads(path.read_text()), "status": "cancelled"}))
    r = _client(s).post(f"/api/queue/cancel/{FIX}4")
    assert r.status_code == 200 and r.json()["already"] is True
    assert _events(s, f"{FIX}4") == []  # reading a legacy record never writes


def test_claimed_by_dispatcher_is_409_and_untouched(tmp_path):
    s = _env(tmp_path, True)
    _seed(s, f"{FIX}5", state="running")
    assert _client(s).post(f"/api/queue/cancel/{FIX}5").status_code == 409
    assert (s.queue_dir / "running" / f"{FIX}5.json").exists() and _events(s, f"{FIX}5") == []


def test_audit_failure_rolls_the_queue_back(tmp_path, monkeypatch):
    s = _env(tmp_path, True)
    original = _seed(s, f"{FIX}6").read_bytes()
    module = _module(s)

    def broken(audit, event):
        raise OSError("disk full")

    monkeypatch.setattr(module, "append_terminal_event", broken)
    with pytest.raises(OSError):
        _client(s).post(f"/api/queue/cancel/{FIX}6")
    assert (s.queue_dir / "pending" / f"{FIX}6.json").read_bytes() == original
    assert not (s.queue_dir / "done" / f"{FIX}6.json").exists()
    assert _events(s, f"{FIX}6") == []


def test_mutant_mutation_without_audit_write_is_detected(tmp_path, monkeypatch):
    """Control for the positive test: with the writer silenced the queue still moves, and the
    assertion used above MUST fail. If it passed, the suite could not see the original defect."""
    s = _env(tmp_path, True)
    _seed(s, f"{FIX}7")
    monkeypatch.setattr(_module(s), "append_terminal_event", lambda audit, event: False)
    assert _client(s).post(f"/api/queue/cancel/{FIX}7").status_code == 200
    assert (s.queue_dir / "done" / f"{FIX}7.json").exists()
    assert not _one_terminal_event(s, f"{FIX}7")


def test_without_lifecycle_a2a_cancel_is_refused(tmp_path):
    s = _env(tmp_path, False)
    _seed(s, f"{FIX}8")
    r = _client(s).post(f"/api/queue/cancel/{FIX}8")
    assert r.status_code == 503
    assert (s.queue_dir / "pending" / f"{FIX}8.json").exists() and _audit(s).read_text() == ""


def test_without_lifecycle_plain_cancel_still_works(tmp_path):
    s = _env(tmp_path, False)
    _seed(s, f"{FIX}9", a2a=False)
    assert _client(s).post(f"/api/queue/cancel/{FIX}9").json() == {"ok": True, "state": "canceled"}
    rec = json.loads((s.queue_dir / "done" / f"{FIX}9.json").read_text())
    assert rec["status"] == "canceled"
    assert datetime.fromisoformat(rec["completedAt"]).utcoffset().total_seconds() == 0


def test_unknown_item_is_404(tmp_path):
    s = _env(tmp_path, True)
    assert _client(s).post(f"/api/queue/cancel/{FIX}0").status_code == 404
