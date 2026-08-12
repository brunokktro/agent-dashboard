#!/usr/bin/env python3
"""Rebuild the generic demo ecosystem used for the public screenshots.

Deterministic: every run timestamp is derived from the agent's real cron
cadence walking BACKWARDS from now, so nothing can land in the future
(the bug that produced "-5358s ago" in the previous screenshots).

Usage: python3 seed-demo.py [target_dir]
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else
              Path(__file__).parent / "demo-agents").expanduser()
NOW = datetime.now().replace(microsecond=0)
random.seed(20260807)  # stable output across re-runs

FMT = "%Y-%m-%d %H:%M:%S"


# agent: (description, chat_ready, cron, human_cadence, total, fails, fails_7d,
#         avg_dur, dur_jitter, last_offset_min, last_failed)
AGENTS = {
    "site-monitor": dict(
        desc="Probes public endpoints every 15 minutes and tracks latency budgets",
        chat=False, cron="*/15 * * * *", step=15, total=1200, fails=9, fails_7d=7,
        dur=17, jitter=6, last_min=8),
    "email-triage": dict(
        desc="Labels and prioritizes the shared inbox, drafts suggested replies",
        chat=False, cron="*/30 8-18 * * 1-5", step=30, total=420, fails=23, fails_7d=8,
        dur=72, jitter=25, last_min=95, hours=range(8, 19), weekdays={0, 1, 2, 3, 4}),
    "cost-optimizer": dict(
        desc="Analyzes cloud spend daily and flags idle resources to reclaim",
        chat=False, cron="0 7 * * *", step=1440, total=30, fails=0, fails_7d=0,
        dur=143, jitter=40, at=(7, 0)),
    "code-reviewer": dict(
        desc="Reviews pull requests for style, security and test coverage before merge",
        chat=True, cron=None, step=190, total=90, fails=8, fails_7d=1,
        dur=286, jitter=90, last_min=175),
    "data-syncer": dict(
        desc="Syncs product analytics into the warehouse every hour",
        chat=False, cron="0 * * * *", step=60, total=480, fails=9, fails_7d=5,
        dur=52, jitter=18, last_min=420, last_failed=True),
    "security-scanner": dict(
        desc="Scans dependencies and containers for CVEs, opens fix tickets",
        chat=True, cron="0 5 * * *", step=1440, total=30, fails=0, fails_7d=0,
        dur=418, jitter=110, at=(5, 0)),
    "standup-reporter": dict(
        desc="Compiles yesterday's commits and tickets into a standup summary",
        chat=True, cron="45 8 * * 1-5", step=1440, total=30, fails=0, fails_7d=0,
        dur=64, jitter=20, at=(8, 45), weekdays={0, 1, 2, 3, 4}),
    "news-digest": dict(
        desc="Curates a morning digest from RSS feeds and newsletters into one summary",
        chat=False, cron="30 6 * * 1-5", step=1440, total=30, fails=3, fails_7d=1,
        dur=145, jitter=45, at=(6, 30), weekdays={0, 1, 2, 3, 4}),
    "dep-updater": dict(
        desc="Opens weekly dependency-update PRs with changelogs and risk notes",
        chat=False, cron="0 9 * * 1", step=10080, total=4, fails=0, fails_7d=0,
        dur=221, jitter=60, at=(9, 0), weekdays={0}),
    "backup-runner": dict(
        desc="Nightly incremental backups of workspaces to object storage with retention",
        chat=False, cron="0 3 * * *", step=1440, total=30, fails=1, fails_7d=0,
        dur=1977, jitter=300, at=(3, 0)),
    "release-bot": dict(
        desc="Cuts releases: changelog, version bump, tag and publish pipeline",
        chat=True, cron=None, step=10080, total=5, fails=0, fails_7d=0,
        dur=402, jitter=90, last_min=10080),
    "docs-writer": dict(
        desc="Keeps README and API docs in sync with the codebase after merges",
        chat=True, cron="0 12 * * 1-5", step=1440, total=0, fails=0, fails_7d=0,
        dur=0, jitter=0, enabled=False),
}

# jobs shown on the Supervisor page (10) - code-reviewer and release-bot are event-driven
SCHEDULED = ["site-monitor", "email-triage", "cost-optimizer", "data-syncer",
             "security-scanner", "standup-reporter", "news-digest", "dep-updater",
             "backup-runner", "docs-writer"]


def slots(cfg: dict, count: int) -> list[datetime]:
    """Timestamps walking backwards from the agent's last run. Never in the future."""
    out: list[datetime] = []
    if count == 0:
        return out
    at = cfg.get("at")
    weekdays = cfg.get("weekdays")
    hours = cfg.get("hours")
    if at:
        # daily/weekly job at a fixed time: most recent occurrence at or before now
        t = NOW.replace(hour=at[0], minute=at[1], second=0)
        if t > NOW:
            t -= timedelta(days=1)
        while len(out) < count:
            if weekdays is None or t.weekday() in weekdays:
                out.append(t)
            t -= timedelta(days=1)
        return out
    t = NOW - timedelta(minutes=cfg["last_min"])
    t = t.replace(second=0)
    while len(out) < count:
        if (weekdays is None or t.weekday() in weekdays) and \
           (hours is None or t.hour in hours):
            out.append(t)
        t -= timedelta(minutes=cfg["step"])
    return out


def build() -> dict:
    for sub in ("logs", "scripts", "locks",
                "queue/pending", "queue/running", "queue/done", "queue/failed"):
        (TARGET / sub).mkdir(parents=True, exist_ok=True)

    # ── agent specs ──────────────────────────────────────────────────
    for name, cfg in AGENTS.items():
        body = "\n".join([
            "---", f"name: {name}", f"description: {cfg['desc']}", "---", "",
            f"# {name}", "",
            "## Purpose", "", cfg["desc"] + ".", "",
            "## Inputs", "", "- Configuration from the ecosystem root", "",
            "## Outputs", "", "- A log file per run, recorded in runs.db", "",
        ])
        (TARGET / f"{name}.md").write_text(body)
        cfgfile = TARGET / f"{name}.json"
        if cfg["chat"]:
            cfgfile.write_text(json.dumps(
                {"name": name, "description": cfg["desc"],
                 "tools": ["fs_read", "fs_write", "execute_bash"],
                 "toolsSettings": {}}, indent=2))
        elif cfgfile.exists():
            cfgfile.unlink()

    # ── runs.db ──────────────────────────────────────────────────────
    db = TARGET / "runs.db"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, "
        "started_at TEXT, duration_sec INTEGER, status TEXT, exit_code INTEGER, "
        "log_path TEXT)")

    rows: list[tuple] = []
    summary: dict[str, dict] = {}
    week_ago = NOW - timedelta(days=7)
    day_ago_dt = NOW - timedelta(days=1)

    for name, cfg in AGENTS.items():
        ts = slots(cfg, cfg["total"])
        recent = [i for i, t in enumerate(ts) if t >= week_ago]
        older = [i for i, t in enumerate(ts) if t < week_ago]
        fail_idx: set[int] = set()
        # 7d failures: keep them OUT of the last 24h so the "failed runs" alert
        # stays to the single declared failure (data-syncer), and never on the
        # most recent run unless declared.
        pool_recent = [i for i in recent if i != 0 and ts[i] < day_ago_dt]
        fail_idx.update(random.sample(pool_recent, min(cfg["fails_7d"], len(pool_recent))))
        rest = cfg["fails"] - len(fail_idx)
        if rest > 0 and older:
            fail_idx.update(random.sample(older, min(rest, len(older))))
        if cfg.get("last_failed"):
            fail_idx.add(0)

        for i, t in enumerate(ts):
            failed = i in fail_idx
            dur = max(1, int(random.gauss(cfg["dur"], cfg["jitter"])))
            if failed and i == 0 and name == "data-syncer":
                dur = 76  # matches the alert card: "after 1m 16s"
            rows.append((name, t.strftime(FMT), dur,
                         "failed" if failed else "success",
                         1 if failed else 0,
                         f"logs/{name}-{t.strftime('%Y-%m-%d')}.log"))
        summary[name] = {
            "total": cfg["total"], "fails": len(fail_idx),
            "last": ts[0].strftime(FMT) if ts else None,
            "7d": len(recent), "7d_fails": len(fail_idx & set(recent)),
        }

    # insert oldest-first so id order == chronological order
    rows.sort(key=lambda r: r[1])
    conn.executemany(
        "INSERT INTO runs (job_id, started_at, duration_sec, status, exit_code, log_path) "
        "VALUES (?,?,?,?,?,?)", rows)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    day_ago = (NOW - timedelta(days=1)).strftime(FMT)
    ok24 = conn.execute("SELECT COUNT(*) FROM runs WHERE started_at > ? AND status='success'",
                        (day_ago,)).fetchone()[0]
    fail24 = conn.execute("SELECT COUNT(*) FROM runs WHERE started_at > ? AND status='failed'",
                          (day_ago,)).fetchone()[0]
    future = conn.execute("SELECT COUNT(*) FROM runs WHERE started_at > ?",
                          (NOW.strftime(FMT),)).fetchone()[0]
    today = conn.execute("SELECT COUNT(*) FROM runs WHERE date(started_at)=?",
                         (NOW.strftime("%Y-%m-%d"),)).fetchone()[0]
    conn.close()

    # ── schedule.json ────────────────────────────────────────────────
    jobs = []
    for name in SCHEDULED:
        cfg = AGENTS[name]
        jobs.append({"id": name, "script": f"{name}-auto.sh", "cron": cfg["cron"],
                     "enabled": cfg.get("enabled", True),
                     "timeout_sec": 1800,
                     "description": cfg["desc"]})
    (TARGET / "scripts" / "schedule.json").write_text(json.dumps(
        {"version": 1, "timezone": "America/Sao_Paulo", "memory_guard_mb": 1536,
         "max_concurrent": 2, "jobs": jobs}, indent=2))

    # ── logs (one per agent; the data-syncer one is the rich failing run) ──
    for old in (TARGET / "logs").glob("*.log"):
        old.unlink()
    for name, cfg in AGENTS.items():
        if cfg["total"] == 0:
            continue
        last = summary[name]["last"]
        day = last.split(" ")[0]
        t0 = datetime.strptime(last, FMT)

        def stamp(offset: int, t0=t0) -> str:
            return (t0 + timedelta(seconds=offset)).strftime(FMT)

        if name == "data-syncer":
            # a realistic failing run: progress, a warning, then the auth failure
            body = [
                (0, f"=== record-run start: job={name} cmd=./sync.py --incremental ==="),
                (0, "loading configuration from config/warehouse.yaml"),
                (1, "resolved credentials from profile 'analytics'"),
                (1, "source: events-api  target: warehouse.public.events"),
                (2, "discovering partitions since 2026-08-07T15:00:00"),
                (3, "found 6 partitions, 184320 rows to move"),
                (5, "batch 1/6 ok - 30720 rows in 1.8s"),
                (8, "batch 2/6 ok - 30720 rows in 2.1s"),
                (12, "batch 3/6 ok - 30720 rows in 1.9s"),
                (19, "WARN: batch 4/6 retried once (connection reset by peer)"),
                (21, "batch 4/6 ok - 30720 rows in 4.2s"),
                (26, "batch 5/6 ok - 30720 rows in 2.0s"),
                (31, "refreshing credentials before final batch"),
                (33, "ERROR: ExpiredToken: The security token included in the request is expired"),
                (33, "Traceback (most recent call last):"),
                (33, '  File "sync.py", line 212, in flush_batch'),
                (33, "    client.put_records(**payload)"),
                (33, '  File "botocore/client.py", line 1023, in _make_api_call'),
                (33, "    raise error_class(parsed_response, operation_name)"),
                (33, "botocore.exceptions.ClientError: An error occurred (ExpiredToken) "
                     "when calling the PutRecords operation"),
                (34, "WARN: batch 6/6 not attempted - 30720 rows left behind"),
                (35, "rolling back the staging table to keep the partition consistent"),
                (40, "rollback done, staging table dropped"),
                (76, f"=== record-run end: exit=1 status=failed duration=76s ==="),
            ]
        else:
            dur = cfg["dur"]
            body = [
                (0, f"=== record-run start: job={name} ==="),
                (0, "loading configuration"),
                (1, "preflight checks ok"),
                (max(1, dur // 3), "work in progress"),
                (max(2, (dur * 2) // 3), "work completed"),
                (dur, f"=== record-run end: exit=0 status=success duration={dur}s ==="),
            ]
        text = "\n".join(f"[{stamp(off)}] {msg}" for off, msg in body) + "\n"
        log_path = TARGET / "logs" / f"{name}-{day}.log"
        log_path.write_text(text)
        # mtime = end of that run, so the Logs list shows realistic ages
        end = (t0 + timedelta(seconds=body[-1][0])).timestamp()
        os.utime(log_path, (end, end))

    # ── a neutral HOME for the Console screenshot (no personal paths/prompt) ──
    home = TARGET.parent / "demo-home"
    (home / "projects" / "checkout-service").mkdir(parents=True, exist_ok=True)
    (home / "projects" / "events-pipeline").mkdir(parents=True, exist_ok=True)
    (home / ".bash_profile").write_text(
        # generic, hostname-free prompt so the screenshot exposes nothing
        'PS1="demo:\\W$ "\nexport PAGER=cat\nclear\n')
    (home / "projects" / "checkout-service" / "README.md").write_text("# checkout-service\n")
    (home / "projects" / "events-pipeline" / "README.md").write_text("# events-pipeline\n")

    # ── queue items ──────────────────────────────────────────────────
    for st in ("pending", "running", "done", "failed"):
        for old in (TARGET / "queue" / st).glob("*.json"):
            old.unlink()
    queue = [
        ("pending", "review-auth-refactor", "code-reviewer",
         "Review PR #482: token refresh refactor", "high", 25),
        ("pending", "digest-weekly-roundup", "news-digest",
         "Build the weekly roundup from the last 7 days of feeds", "medium", 90),
        ("pending", "scan-base-images", "security-scanner",
         "Rescan base images after the CVE feed update", "medium", 150),
        ("running", "sync-analytics-backfill", "data-syncer",
         "Backfill yesterday's analytics partition", "high", 12),
        ("failed", "release-1-8-0", "release-bot",
         "Cut release 1.8.0 and publish artifacts", "high", 320),
        ("done", "cost-review-august", "cost-optimizer",
         "Flag idle resources for the August cost review", "medium", 480),
        ("done", "standup-friday", "standup-reporter",
         "Compile Friday standup summary", "low", 700),
    ]
    for state, item_id, agent, text, prio, mins_ago in queue:
        created = (NOW - timedelta(minutes=mins_ago)).isoformat(timespec="seconds")
        item = {"id": item_id, "agent": agent, "input": text, "priority": prio,
                "created": created, "status": state}
        if state == "done":
            item["result"] = "Completed successfully"
            item["completedAt"] = (NOW - timedelta(minutes=mins_ago - 8)) \
                .isoformat(timespec="seconds")
        if state == "failed":
            item["result"] = "publish step failed: registry returned 401"
        (TARGET / "queue" / state / f"{item_id}.json").write_text(json.dumps(item, indent=2))

    return {"dir": str(TARGET), "total": total, "ok_24h": ok24, "fail_24h": fail24,
            "today": today, "future_runs": future, "agents": summary}


if __name__ == "__main__":
    out = build()
    print(json.dumps(out, indent=2))
    assert out["future_runs"] == 0, "FUTURE TIMESTAMPS PRESENT - this was the original bug"
    print("\nOK: no run is in the future.")
