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


def test_future_run_never_becomes_last(store):
    """Regression: a run stamped in the future (clock skew, UTC container, bad
    seed) rendered '-5358s ago' on Overview while Supervisor (id DESC) showed
    another value for the same agent. The future row must not be the 'last'."""
    from datetime import datetime, timedelta

    with store.db() as conn:
        future = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO runs (job_id, started_at, duration_sec, status, exit_code, log_path) "
            "VALUES (?,?,?,?,?,?)",
            ("alpha-agent-morning", future, 60, "success", 0, "logs/alpha.log"))
        conn.commit()
        stats = store.agent_run_stats(conn, "alpha-agent")
        last = datetime.strptime(stats["last"]["started_at"], "%Y-%m-%d %H:%M:%S")
        assert last <= datetime.now(), "future run leaked into 'last'"
        # the future row is excluded from the stats entirely, not just demoted
        assert all(
            datetime.strptime(r["started_at"], "%Y-%m-%d %H:%M:%S") <= datetime.now()
            for r in stats["recent"] if r["started_at"])


def test_json_only_agent_is_discovered(store, ecosystem):
    """Regression (field report): kiro-cli native agents are bare .json configs.
    A dashboard that only scans .md shows an empty Overview on such installs."""
    import json as _json

    (ecosystem.agents_dir / "gamma-agent.json").write_text(_json.dumps({
        "name": "gamma-agent",
        "description": "JSON-native kiro-cli agent",
        "tools": ["read"],
    }))
    agents = store.load_agents()
    assert "gamma-agent" in agents
    assert agents["gamma-agent"]["description"] == "JSON-native kiro-cli agent"
    assert agents["gamma-agent"]["has_config"] is True


def test_cli_name_follows_json_config_not_filename(store, ecosystem):
    """Regression (field report): kiro-cli resolves --agent by the ``name``
    field INSIDE the .json config, not by the filename. When they differ,
    a terminal opened with the filename fails with "no agent with name X
    found". The dashboard keeps the stem as its identity (runs, logs and
    queue are keyed by it) but must expose the config's name as ``cli_name``
    so every composed ``kiro-cli chat --agent`` uses the resolvable one."""
    import json as _json

    # json-only agent whose internal name differs from the file stem
    (ecosystem.agents_dir / "file-stem.json").write_text(_json.dumps({
        "name": "real-internal-name", "description": "mismatched", "tools": []}))
    # md+json pair with the same mismatch
    (ecosystem.agents_dir / "alpha-agent.json").write_text(_json.dumps({
        "name": "alpha-cli-name", "description": "config description", "tools": []}))
    agents = store.load_agents()
    assert agents["file-stem"]["cli_name"] == "real-internal-name"
    assert agents["alpha-agent"]["cli_name"] == "alpha-cli-name"
    # no config, or config without a usable name -> fall back to the stem
    assert agents["beta-agent"]["cli_name"] == "beta-agent"


def test_non_agent_json_is_ignored(store, ecosystem):
    """Random .json files in the agents dir (policies, state) are not agents."""
    import json as _json

    (ecosystem.agents_dir / "notify-policy.json").write_text(_json.dumps(
        {"channels": ["reminder"], "mode": "failures-only"}))
    (ecosystem.agents_dir / "broken.json").write_text("{not json")
    agents = store.load_agents()
    assert "notify-policy" not in agents
    assert "broken" not in agents


def test_md_spec_wins_over_its_json_config(store, ecosystem):
    """An .md + .json pair is ONE agent, described by the .md spec."""
    import json as _json

    (ecosystem.agents_dir / "alpha-agent.json").write_text(_json.dumps({
        "name": "alpha-agent", "description": "config description", "tools": []}))
    agents = store.load_agents()
    assert agents["alpha-agent"]["description"] == "First test agent"
    assert agents["alpha-agent"]["has_config"] is True


def test_exclude_agents_filters_by_glob(ecosystem):
    """DASHBOARD_EXCLUDE_AGENTS hides agents by glob pattern - lets an install
    keep vendor/json-native agents out of view without touching files."""
    import json as _json

    from dashboard.config import Settings
    from dashboard.datastore import Datastore

    (ecosystem.agents_dir / "vendor-tool-x.json").write_text(_json.dumps({
        "name": "vendor-tool-x", "description": "vendor agent", "tools": []}))
    s = Settings(agents_dir=ecosystem.agents_dir,
                 exclude_agents=["vendor-*", "beta-agent"])
    agents = Datastore(s).load_agents()
    assert "vendor-tool-x" not in agents
    assert "beta-agent" not in agents
    assert "alpha-agent" in agents


def test_runtime_config_file_overrides_settings(tmp_path, monkeypatch):
    """Under an app host (KiroCrew) the backend gets a minimal env - no
    DASHBOARD_* vars can reach it. The host's per-app config.json
    ($KIROCREW_HOME/apps/$KIROCREW_APP_NAME/data/config.json) is the only
    settings channel, so Settings must honor it."""
    import json as _json

    from dashboard.config import build_settings

    cfg_dir = tmp_path / "apps" / "agent-dashboard" / "data"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(_json.dumps({
        "exclude_agents": ["vendor-*"],
        "extra_hints": [["corp-sso", "SSO expired"]],
        "ignored_unknown_key": True,
    }))
    monkeypatch.setenv("KIROCREW_HOME", str(tmp_path))
    monkeypatch.setenv("KIROCREW_APP_NAME", "agent-dashboard")
    s = build_settings()
    assert s.exclude_agents == ["vendor-*"]
    assert s.extra_hints == [["corp-sso", "SSO expired"]]


def test_runtime_config_absent_or_malformed_is_ignored(tmp_path, monkeypatch):
    from dashboard.config import build_settings

    monkeypatch.setenv("KIROCREW_HOME", str(tmp_path))
    monkeypatch.setenv("KIROCREW_APP_NAME", "agent-dashboard")
    assert build_settings().exclude_agents == []  # no file -> defaults

    cfg_dir = tmp_path / "apps" / "agent-dashboard" / "data"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text("{not json")
    assert build_settings().exclude_agents == []  # malformed -> defaults
