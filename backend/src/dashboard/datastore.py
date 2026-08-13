"""Read layer over the agent ecosystem's data sources.

The dashboard is a CONSUMER of these artifacts - the supervisor and the
agent scripts own them. This module reads runs.db (SQLite), the queue
directories, schedule.json, lock files and agent markdown specs. The only
writes performed anywhere are queue transitions and alert acks (see api.py).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .config import Settings

QUEUE_STATES = ("pending", "running", "done", "failed")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DESCRIPTION_RE = re.compile(r"description:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)


class Datastore:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    # ── Agents registry ─────────────────────────────────────────────
    def load_agents(self) -> dict[str, dict[str, Any]]:
        """Agents come in two shapes, both first-class:

        - ``.md`` spec with YAML frontmatter carrying a ``name`` field
          (this ecosystem's convention);
        - bare ``.json`` kiro-cli agent config with ``name`` + ``tools``
          (kiro-cli's native format - some installs have ONLY these).

        An ``.md`` + ``.json`` pair is ONE agent, described by the ``.md``.
        """
        agents: dict[str, dict[str, Any]] = {}
        for md in sorted(self.s.agents_dir.glob("*.md")):
            try:
                text = md.read_text(errors="replace")
            except OSError:
                continue
            fm = _FRONTMATTER_RE.match(text)
            if not fm or not re.search(r"^name:\s*\S", fm.group(1), re.MULTILINE):
                continue
            desc_m = _DESCRIPTION_RE.search(fm.group(1))
            desc = desc_m.group(1).strip().rstrip("\"'") if desc_m else ""
            if desc in {">", "|", ">-", "|-"}:
                # YAML folded/literal block: description is on the following indented lines
                lines = fm.group(1).splitlines()
                idx = next((i for i, ln in enumerate(lines)
                            if ln.lstrip().startswith("description:")), None)
                block: list[str] = []
                if idx is not None:
                    for ln in lines[idx + 1:]:
                        if ln.startswith((" ", "\t")) and ln.strip():
                            block.append(ln.strip())
                        elif ln.strip():
                            break
                desc = " ".join(block)
            agents[md.stem] = {
                "name": md.stem,
                "description": desc,
                "has_config": (self.s.agents_dir / f"{md.stem}.json").exists(),
            }
        # JSON-only agents: a .json is an agent config (not policy/state noise)
        # when it parses AND carries both "name" and "tools" keys.
        for cfg in sorted(self.s.agents_dir.glob("*.json")):
            if cfg.stem in agents:
                continue  # already described by its .md spec
            try:
                data = json.loads(cfg.read_text(errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict) or "name" not in data or "tools" not in data:
                continue
            agents[cfg.stem] = {
                "name": cfg.stem,
                "description": str(data.get("description", "")).strip(),
                "has_config": True,
            }
        if self.s.include_agents:
            agents = {n: a for n, a in agents.items()
                      if any(fnmatch(n, pat) for pat in self.s.include_agents)}
        if self.s.exclude_agents:
            agents = {n: a for n, a in agents.items()
                      if not any(fnmatch(n, pat) for pat in self.s.exclude_agents)}
        return agents

    def resolve_agent(self, job_id: str) -> str:
        """Map a schedule job id to its agent name."""
        if job_id in self.s.job_agent_overrides:
            return self.s.job_agent_overrides[job_id]
        base = re.sub(r"-(morning|afternoon|evening|daily|weekly)$", "", job_id)
        return self.s.job_agent_overrides.get(base, base)

    # ── runs.db ─────────────────────────────────────────────────────
    @contextlib.contextmanager
    def db(self):
        first_time = not self.s.db_path.exists()
        self.s.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.s.db_path)
        conn.row_factory = sqlite3.Row
        if first_time:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "job_id TEXT, started_at TEXT, duration_sec INTEGER, status TEXT, "
                "exit_code INTEGER, log_path TEXT)")
            conn.commit()
        try:
            yield conn
        finally:
            conn.close()

    def agent_run_stats(self, conn: sqlite3.Connection, name: str) -> dict[str, Any]:
        # A run stamped in the future (clock skew, UTC container, bad seed) must
        # never become the "last run": it renders a negative relative time and
        # diverges from views that order by id. NULL started_at rows are kept.
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT status, duration_sec, started_at FROM runs "
            "WHERE (job_id = ? OR job_id LIKE ?) "
            "AND (started_at IS NULL OR started_at <= ?) "
            "ORDER BY started_at DESC, id DESC",
            (name, f"{name}-%", now),
        ).fetchall()
        if not rows:
            return {"total": 0, "ok": 0, "fail": 0, "avg_dur": 0, "last": None,
                    "trend": "none", "score": 0, "recent": []}
        total = len(rows)
        ok = sum(1 for r in rows if r["status"] == "success")
        durations = [r["duration_sec"] for r in rows if r["duration_sec"]]
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent_7 = [r for r in rows if r["started_at"] and r["started_at"] >= week_ago]
        if recent_7:
            score = sum(1 for r in recent_7 if r["status"] == "success") * 100 // len(recent_7)
        else:
            score = ok * 100 // total
        last5 = [r["status"] for r in rows[:5]]
        prev5 = [r["status"] for r in rows[5:10]]
        if not prev5:
            trend = "none"
        else:
            ok_last = sum(1 for s in last5 if s == "success")
            ok_prev = sum(1 for s in prev5 if s == "success")
            trend = "up" if ok_last > ok_prev else ("down" if ok_last < ok_prev else "flat")
        return {
            "total": total, "ok": ok, "fail": total - ok,
            "avg_dur": sum(durations) // len(durations) if durations else 0,
            "last": dict(rows[0]), "trend": trend, "score": score,
            "recent": [dict(r) for r in rows[:10]],
        }

    def runs_for_agent(self, conn: sqlite3.Connection, name: str, limit: int = 20) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM runs WHERE job_id = ? OR job_id LIKE ? "
            "ORDER BY started_at DESC, id DESC LIMIT ?",
            (name, f"{name}-%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def timeline(self, conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)).fetchall()]

    def daily_chart(self, conn: sqlite3.Connection, days: int = 7) -> list[dict]:
        now = datetime.now()
        out = []
        for i in range(days - 1, -1, -1):
            d = now - timedelta(days=i)
            ds = d.strftime("%Y-%m-%d")
            ok = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE date(started_at)=? AND status='success'", (ds,)
            ).fetchone()[0]
            fail = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE date(started_at)=? AND status='failed'", (ds,)
            ).fetchone()[0]
            out.append({"day": d.strftime("%a"), "date": ds, "ok": ok, "fail": fail})
        return out

    # ── Schedule / locks ────────────────────────────────────────────
    def load_schedule(self) -> dict[str, Any]:
        if self.s.schedule_path.exists():
            return json.loads(self.s.schedule_path.read_text())
        return {"jobs": []}

    def job_for_agent(self, sched: dict, name: str) -> dict | None:
        jobs = sched.get("jobs", [])
        for j in jobs:
            if j["id"] == name or j["id"].startswith(f"{name}-"):
                return j
        for j in jobs:
            if j.get("script", "").startswith(name):
                return j
        return None

    def active_locks(self) -> list[str]:
        if not self.s.lock_dir.exists():
            return []
        active = []
        for lock in self.s.lock_dir.glob("*.lock"):
            try:
                pid = int(lock.read_text().strip())
                os.kill(pid, 0)
                active.append(lock.stem)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass
        return active

    # ── Queue ───────────────────────────────────────────────────────
    def queue_counts(self) -> dict[str, int]:
        return {st: len(list((self.s.queue_dir / st).glob("*.json")))
                if (self.s.queue_dir / st).exists() else 0
                for st in QUEUE_STATES}

    def load_queue_items(self, done_within_hours: int | None = 24) -> list[dict]:
        items: list[dict] = []
        cutoff = (datetime.now() - timedelta(hours=done_within_hours or 0)).isoformat()
        for state in QUEUE_STATES:
            d = self.s.queue_dir / state
            if not d.exists():
                continue
            for f in d.glob("*.json"):
                try:
                    item = json.loads(f.read_text(errors="replace"))
                except (json.JSONDecodeError, OSError):
                    continue
                item["status"] = state  # directory is the source of truth
                item.setdefault("priority", "medium")
                item["_state"] = state
                if state == "done" and done_within_hours:
                    completed = item.get("completedAt", item.get("created", ""))
                    if completed and completed < cutoff:
                        continue
                items.append(item)
        order = {"running": 0, "pending": 1, "failed": 2, "done": 3}
        items.sort(key=lambda x: (order.get(x["_state"], 9), x.get("created", "")), reverse=False)
        # newest first within each state
        items.sort(key=lambda x: (order.get(x["_state"], 9),))
        grouped: list[dict] = []
        for state in ("running", "pending", "failed", "done"):
            block = [i for i in items if i["_state"] == state]
            block.sort(key=lambda x: x.get("created", ""), reverse=True)
            grouped.extend(block)
        return grouped

    def queue_stuck_items(self) -> list[str]:
        d = self.s.queue_dir / "running"
        if not d.exists():
            return []
        cutoff = (datetime.now() - timedelta(minutes=self.s.stuck_after_minutes)).isoformat()
        stuck = []
        for f in d.glob("*.json"):
            try:
                item = json.loads(f.read_text(errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue
            if item.get("created", "") < cutoff:
                stuck.append(item.get("id", f.stem))
        return stuck

    def queue_item_path(self, state: str, item_id: str) -> Path:
        """Target path for writing an item into a state dir."""
        if state not in QUEUE_STATES:
            raise ValueError(f"invalid queue state: {state}")
        safe = Path(item_id).name  # strip any path components
        return self.s.queue_dir / state / f"{safe}.json"

    def find_queue_item(self, state: str, item_id: str) -> Path | None:
        """Locate an item by id: filename match first, then the id FIELD inside
        each json (real queues have files whose name differs from the id)."""
        direct = self.queue_item_path(state, item_id)
        if direct.exists():
            return direct
        d = self.s.queue_dir / state
        if not d.exists():
            return None
        for f in d.glob("*.json"):
            try:
                if json.loads(f.read_text(errors="replace")).get("id") == item_id:
                    return f
            except (json.JSONDecodeError, OSError):
                continue
        return None

    # ── Alerts / acks ───────────────────────────────────────────────
    @property
    def _ack_path(self) -> Path:
        return self.s.log_dir / "ack-alerts.json"

    def load_acked(self) -> set[str]:
        if self._ack_path.exists():
            try:
                return set(json.loads(self._ack_path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        return set()

    def save_acked(self, acked: set[str]) -> None:
        self._ack_path.parent.mkdir(parents=True, exist_ok=True)
        self._ack_path.write_text(json.dumps(sorted(acked)))

    def big_logs(self) -> list[tuple[str, int]]:
        if not self.s.log_dir.exists():
            return []
        limit = self.s.big_log_mb * 1024 * 1024
        return [(f.name, f.stat().st_size // (1024 * 1024))
                for f in self.s.log_dir.glob("*.log") if f.stat().st_size > limit]

    def log_files(self, limit: int = 30) -> list[dict]:
        if not self.s.log_dir.exists():
            return []
        logs = sorted(self.s.log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"name": p.name, "size_kb": p.stat().st_size // 1024,
                 "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat()}
                for p in logs[:limit]]
