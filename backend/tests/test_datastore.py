"""Datastore tests against a real temp ecosystem (no mocks)."""

from __future__ import annotations

from datetime import datetime, timedelta

from hypothesis import given
from hypothesis import settings as hsettings
from hypothesis import strategies as st


def test_load_agents_detects_frontmatter_only(store):
    agents = store.load_agents()
    assert set(agents) == {"alpha-agent", "beta-agent"}  # README.md ignored
    assert agents["alpha-agent"]["description"] == "First test agent"


def test_resolve_agent_strips_known_suffixes(store):
    assert store.resolve_agent("alpha-agent-morning") == "alpha-agent"
    assert store.resolve_agent("beta-agent") == "beta-agent"


def test_resolve_agent_uses_overrides(ecosystem):
    from dashboard.datastore import Datastore
    ecosystem2 = ecosystem.model_copy(
        update={"job_agent_overrides": {"weird-job": "alpha-agent"}})
    assert Datastore(ecosystem2).resolve_agent("weird-job") == "alpha-agent"


def test_agent_run_stats(store):
    with store.db() as conn:
        s = store.agent_run_stats(conn, "alpha-agent")
    assert s["total"] == 2
    assert s["ok"] == 1
    assert s["fail"] == 1
    assert s["last"]["status"] == "success"  # most recent first


def test_stats_empty_agent(store):
    with store.db() as conn:
        s = store.agent_run_stats(conn, "ghost-agent")
    assert s == {"total": 0, "ok": 0, "fail": 0, "avg_dur": 0, "last": None,
                 "trend": "none", "score": 0, "recent": []}


def test_queue_counts_and_items(store):
    counts = store.queue_counts()
    assert counts == {"pending": 1, "running": 0, "done": 1, "failed": 1}
    items = store.load_queue_items(done_within_hours=None)
    states = [i["_state"] for i in items]
    # running > pending > failed > done ordering
    assert states == sorted(states, key=lambda s: ["running", "pending", "failed", "done"].index(s))


def test_queue_item_path_rejects_traversal(store):
    p = store.queue_item_path("pending", "../../../etc/passwd")
    assert p.parent == store.s.queue_dir / "pending"
    assert p.name == "passwd.json"


def test_acked_roundtrip(store):
    store.save_acked({"1", "2"})
    assert store.load_acked() == {"1", "2"}


# ── Invariants (property-based) ──────────────────────────────────────
@hsettings(max_examples=50, deadline=None)
@given(statuses=st.lists(st.sampled_from(["success", "failed"]), min_size=1, max_size=40))
def test_score_always_0_100(tmp_path_factory, statuses):
    """Health score must stay within 0-100 for ANY run history."""
    import sqlite3

    from dashboard.config import Settings
    from dashboard.datastore import Datastore

    d = tmp_path_factory.mktemp("inv")
    conn = sqlite3.connect(d / "runs.db")
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, "
        "started_at TEXT, duration_sec INTEGER, status TEXT, exit_code INTEGER, log_path TEXT)")
    now = datetime(2026, 8, 6, 12, 0, 0)
    for i, status in enumerate(statuses):
        started = (now - timedelta(hours=i * 3)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO runs (job_id, started_at, duration_sec, status) VALUES (?,?,?,?)",
                     ("x-agent", started, 10, status))
    conn.commit()
    conn.close()

    store = Datastore(Settings(agents_dir=d))
    with store.db() as c:
        s = store.agent_run_stats(c, "x-agent")
    assert 0 <= s["score"] <= 100
    assert s["ok"] + s["fail"] == s["total"] == len(statuses)
    assert s["trend"] in ("up", "down", "flat", "none")


def test_load_agents_folded_description(ecosystem):
    """Regression: YAML folded block (description: >) must not yield '>'."""
    from dashboard.datastore import Datastore
    (ecosystem.agents_dir / "gamma-agent.md").write_text(
        "---\nname: gamma-agent\ndescription: >\n  Folded description\n"
        "  across two lines.\ntools: [read]\n---\n# G\n")
    agents = Datastore(ecosystem).load_agents()
    assert agents["gamma-agent"]["description"] == "Folded description across two lines."
