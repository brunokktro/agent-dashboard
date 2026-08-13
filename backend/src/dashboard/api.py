"""API routes. All responses are JSON - the React frontend is the only view layer."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel

from .config import Settings, get_settings
from .datastore import Datastore

router = APIRouter()


def _store(settings: Annotated[Settings, Depends(get_settings)]) -> Datastore:
    return Datastore(settings)

Store = Annotated[Datastore, Depends(_store)]


def _runner_capabilities(settings: Settings) -> dict[str, bool]:
    """Which Run actions the observed ecosystem can actually perform.

    Triggering delegates to run-agent.sh / run-scheduled.sh, which belong to
    the ecosystem (this dashboard only observes). The UI uses this to disable
    a button instead of offering a click that can only fail with 503.
    """
    return {
        "run_agent": (settings.scripts_dir / "run-agent.sh").is_file(),
        "run_job": (settings.scripts_dir / "run-scheduled.sh").is_file(),
    }


# ── Read endpoints ───────────────────────────────────────────────────
@router.get("/healthz")
def api_health_liveness(settings: Annotated[Settings, Depends(get_settings)]):
    """Liveness probe (supervisors like KiroCrew poll this). Reports the
    effective port - under a managed runtime the port is injected via the
    PORT env var and differs from the configured default.

    Deliberately NOT at ``/health``: that path belongs to the SPA's Health page,
    and registering an API route there made a page reload answer JSON instead of
    the app. ``/healthz`` is the conventional spelling for exactly this reason.
    """
    import os
    port = int(os.environ.get("PORT", settings.port))
    return {"status": "ok", "port": port}


@router.get("/api/apphost")
def api_apphost(settings: Annotated[Settings, Depends(get_settings)]):
    """Same payload as /health, but under /api/ - app-shell proxies (KiroCrew
    forwards /apps/<name>/api/* to /api/*) can only reach /api/ paths, and the
    embedding wrapper needs the effective port to point its iframe."""
    return api_health_liveness(settings)


def _fetch_upstream_version(url: str, timeout: int = 8) -> str:
    """Read the upstream app.json and return its version. Network only.

    Deliberately uses raw.githubusercontent (no rate limit, no token) rather
    than the REST API (60 calls/hour unauthenticated). The trade-off is a CDN
    cache of a few minutes per branch, so a check right after a release can
    still report the previous version - acceptable for an update notice, and
    the reason the button never claims to be authoritative about "now".
    """
    import json as _json
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "agent-dashboard"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https host
        return str(_json.loads(r.read()).get("version", "")).strip()


def _newer(latest: str, current: str) -> bool:
    """Is `latest` a newer version than `current`?

    Dependency-free comparison of semver/PEP440-ish strings:
      * numeric release parts first (3.0.1 > 3.0.0);
      * same release, one has no pre-release suffix -> that one wins
        (3.0.0 > 3.0.0-alpha.1);
      * both pre-release -> compare the suffix as (label, numbers), so
        alpha.2 > alpha.1 and beta > alpha. This case matters: a project
        living on -alpha.N would otherwise never see an update.
    """
    import re as _re

    def split(v: str) -> tuple[list[int], str, list[int]]:
        head, _, tail = v.strip().partition("-")
        nums = [int(x) for x in _re.findall(r"\d+", head)] or [0]
        label = "".join(_re.findall(r"[A-Za-z]+", tail))
        tnums = [int(x) for x in _re.findall(r"\d+", tail)]
        return nums, label, tnums

    lnum, llabel, ltnums = split(latest)
    cnum, clabel, ctnums = split(current)
    if lnum != cnum:
        return lnum > cnum
    if not llabel and clabel:      # released beats pre-release
        return True
    if llabel and not clabel:      # pre-release never beats released
        return False
    if llabel != clabel:           # beta > alpha, rc > beta
        return llabel > clabel
    return ltnums > ctnums         # alpha.2 > alpha.1


@router.get("/api/version")
def api_version(response: Response,
                settings: Annotated[Settings, Depends(get_settings)], check: int = 0):
    """Version, and (only when ``check=1``) whether the upstream has a newer one.

    The call to GitHub happens ONLY on an explicit check, so the dashboard makes
    no background network requests. A check that fails is reported as an error -
    never as "up to date", which would be a silent false negative.

    Sends ``no-store``: without it the browser heuristically caches this GET and
    a second click on the button answers from cache without ever asking again -
    a check that silently stops checking is worse than no check.
    """
    response.headers["Cache-Control"] = "no-store"
    from . import __version__
    out: dict[str, object] = {"current": __version__, "latest": None,
                              "update_available": False, "checked": False,
                              "error": None, "repo": settings.upstream_repo,
                              "url": (f"https://github.com/{settings.upstream_repo}"
                                      if settings.upstream_repo else None)}
    if not check:
        return out
    out["checked"] = True
    if not settings.upstream_repo:
        out["error"] = "update check disabled (DASHBOARD_UPSTREAM_REPO is empty)"
        return out
    url = f"https://raw.githubusercontent.com/{settings.upstream_repo}/main/app.json"
    try:
        latest = _fetch_upstream_version(url)
    except Exception as exc:  # noqa: BLE001 - any failure is a failed check, not a verdict
        out["error"] = f"could not reach the upstream repo: {exc}"
        return out
    if not latest:
        out["error"] = "upstream app.json has no version field"
        return out
    out["latest"] = latest
    out["update_available"] = _newer(latest, __version__)
    return out


@router.get("/api/overview")
def api_overview(store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    agents = store.load_agents()
    running = store.active_locks()
    sched = store.load_schedule()
    with store.db() as conn:
        day_ago = (datetime.now().timestamp() - 86400)
        day_ago_s = datetime.fromtimestamp(day_ago).strftime("%Y-%m-%d %H:%M:%S")
        total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        ok_24h = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE started_at > ? AND status='success'", (day_ago_s,)
        ).fetchone()[0]
        fail_24h = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE started_at > ? AND status='failed'", (day_ago_s,)
        ).fetchone()[0]

        alerts = []
        if big := store.big_logs():
            alerts.append({"type": "warn",
                           "message": f"Large log(s): {', '.join(f'{n} ({m}MB)' for n, m in big)}"})
        if running:
            alerts.append({"type": "info", "message": f"Running now: {', '.join(running)}"})
        failures = conn.execute(
            "SELECT id, job_id, started_at, exit_code, duration_sec, log_path FROM runs "
            "WHERE started_at > ? AND status='failed' ORDER BY id DESC LIMIT 10", (day_ago_s,)
        ).fetchall()
        acked = store.load_acked()
        unacked = [dict(f) for f in failures if str(f["id"]) not in acked]
        if unacked:
            alerts.append({"type": "fail",
                           "message": f"{len(unacked)} failed run(s) in last 24h",
                           "items": unacked,
                           "ids": ",".join(str(f["id"]) for f in unacked)})

        def is_running(name: str) -> bool:
            return any(r == name or r.startswith(f"{name}-") for r in running)

        agents_data = []
        for name, info in agents.items():
            stats = store.agent_run_stats(conn, name)
            job = store.job_for_agent(sched, name)
            agents_data.append({
                "name": name, "description": info["description"], "stats": stats,
                "has_config": info["has_config"],
                "cli_name": info["cli_name"],
                "is_running": is_running(name),
                "job": {"id": job["id"], "cron": job["cron"]} if job else None,
            })
        # running first, then most-recent run, then never-ran
        agents_data.sort(key=lambda a: (
            not a["is_running"],
            a["stats"]["total"] == 0,
            -(datetime.fromisoformat(a["stats"]["last"]["started_at"]).timestamp()
              if a["stats"]["last"] and a["stats"]["last"]["started_at"] else 0),
        ))

        schedule = []
        for j in sched.get("jobs", []):
            last = conn.execute(
                "SELECT started_at, status FROM runs WHERE job_id=? ORDER BY id DESC LIMIT 1",
                (j["id"],),
            ).fetchone()
            schedule.append({k: v for k, v in j.items() if k != "script"}
                            | {"last_run": dict(last) if last else None,
                               "is_running": j["id"] in running})

        return {
            "agents": agents_data,
            "metrics": {"total_runs": total, "ok_24h": ok_24h,
                        "fail_24h": fail_24h, "running": running},
            "alerts": alerts,
            "timeline": store.timeline(conn),
            "schedule": schedule,
            "chart": store.daily_chart(conn),
            "capabilities": _runner_capabilities(settings),
        }


@router.get("/api/agent/{name}")
def api_agent(name: str, store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    agents = store.load_agents()
    if name not in agents:
        raise HTTPException(404, "agent not found")
    info = agents[name]
    sched = store.load_schedule()
    job = store.job_for_agent(sched, name)
    md_path = settings.agents_dir / f"{name}.md"
    data_dir = settings.agents_dir / f"{name}-data"
    with store.db() as conn:
        stats = store.agent_run_stats(conn, name)
        runs = store.runs_for_agent(conn, name)
    md_lines = (len(md_path.read_text(errors="replace").splitlines())
                if md_path.exists() else 0)
    return {
        "info": {
            "name": name,
            "cli_name": info["cli_name"],
            "description": info["description"],
            "md_lines": md_lines,
            "has_json": info["has_config"],
            "data_files": len(list(data_dir.glob("*"))) if data_dir.exists() else 0,
            "deps": settings.agent_deps.get(name, ""),
        },
        "stats": stats,
        "runs": runs,
        "job": ({"id": job["id"], "cron": job["cron"],
                 "timeout_sec": job.get("timeout_sec", 1800)} if job else None),
        "capabilities": _runner_capabilities(settings),
    }


@router.get("/api/queue")
def api_queue(store: Store):
    items = store.load_queue_items(done_within_hours=None)
    return {
        "counts": store.queue_counts(),
        "stuck": store.queue_stuck_items(),
        "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items],
    }


@router.get("/api/health")
def api_health(store: Store):
    agents = store.load_agents()
    out = []
    with store.db() as conn:
        for name in sorted(agents):
            s = store.agent_run_stats(conn, name)
            out.append({"name": name, "score": s["score"], "total": s["total"], "ok": s["ok"],
                        "fail": s["fail"], "avg_dur": s["avg_dur"], "trend": s["trend"],
                        "last_run": s["last"]["started_at"] if s["last"] else None})
    # unhealthy first, then worst score
    out.sort(key=lambda a: (a["total"] == 0, a["score"]))
    return {"agents": out}


@router.get("/api/supervisor")
def api_supervisor(store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    status, pid, uptime = "unknown", None, None
    if settings.supervisor_service:
        try:
            result = subprocess.run(["launchctl", "list"],
                                    capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if settings.supervisor_service in line:
                    first = line.split()[0]
                    pid = first if first != "-" else None
                    status = "running" if pid else "loaded"
                    break
            else:
                status = "stopped"
        except (OSError, subprocess.SubprocessError):
            status = "unknown"
        if pid:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                uptime = subprocess.check_output(
                    ["ps", "-o", "etime=", "-p", pid], text=True, timeout=5).strip()
    sched = store.load_schedule()
    with store.db() as conn:
        today = datetime.now().strftime("%Y-%m-%d")
        today_runs = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE date(started_at)=?", (today,)).fetchone()[0]
        total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        schedule = []
        for j in sched.get("jobs", []):
            last = conn.execute(
                "SELECT started_at, status FROM runs WHERE job_id=? ORDER BY id DESC LIMIT 1",
                (j["id"],)).fetchone()
            schedule.append({**j, "last_run": dict(last) if last else None})
    return {"status": status, "pid": pid, "uptime": uptime,
            "capabilities": _runner_capabilities(settings),
            "today_runs": today_runs, "total_runs": total_runs, "schedule": schedule}


@router.get("/api/logs")
def api_logs(store: Store):
    return {"files": store.log_files()}


# ── Actions (JSON in / JSON out) ─────────────────────────────────────
class EnqueueBody(BaseModel):
    agent: str
    input: str
    priority: str = "medium"


@router.post("/api/trigger/{job_id}")
def trigger_job(job_id: str, store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    sched = store.load_schedule()
    job = next((j for j in sched.get("jobs", []) if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "job not found")
    runner = settings.scripts_dir / "run-scheduled.sh"
    if not runner.is_file():
        raise HTTPException(
            503,
            f"runner script not found: {runner}. Scheduled jobs are executed by "
            "your ecosystem's run-scheduled.sh (this dashboard only observes); "
            "see README 'Runner scripts' for the expected contract.")
    subprocess.Popen(
        [str(runner), job["id"], job["script"], str(job.get("timeout_sec", 1800))],
        start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "agent": store.resolve_agent(job["id"])}


@router.post("/api/trigger-agent/{name}")
def trigger_agent(name: str, store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    agents = store.load_agents()
    if name not in agents:
        raise HTTPException(404, "agent not found")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    log_path = settings.log_dir / f"adhoc-{name}-{stamp}.log"
    runner = settings.scripts_dir / "run-agent.sh"
    if not runner.is_file():
        raise HTTPException(
            503,
            f"runner script not found: {runner}. Ad-hoc runs are executed by "
            "your ecosystem's run-agent.sh (this dashboard only observes); "
            "see README 'Runner scripts' for the expected contract.")
    # The positional arg stays the filename stem - it is the dashboard
    # identity (record-run keys the run by it). kiro-cli resolves --agent by
    # the config's INTERNAL name, so the resolvable name rides an env var the
    # scaffolded runner consumes as ${AGENT_CLI_NAME:-$AGENT}. Custom runners
    # that ignore it keep working unchanged.
    env = {**os.environ, "AGENT_CLI_NAME": agents[name]["cli_name"]}
    with log_path.open("w") as lf:
        subprocess.Popen([str(runner), name, "run", "--no-interactive"],
                         start_new_session=True, stdout=lf, stderr=lf, env=env)
    return {"ok": True, "log": log_path.name}


@router.post("/api/alerts/ack")
def ack_alerts(store: Store, ids: Annotated[list[str], Body(embed=True)]):
    acked = store.load_acked()
    acked.update(str(i).strip() for i in ids)
    store.save_acked(acked)
    return {"ok": True, "acked": len(acked)}


@router.post("/api/queue/retry/{item_id}")
def queue_retry(item_id: str, store: Store):
    src = store.find_queue_item("failed", item_id)
    if not src:
        raise HTTPException(404, "item not found in failed")
    item = json.loads(src.read_text())
    item["status"] = "pending"
    item.pop("result", None)
    item.pop("completedAt", None)
    dst = store.queue_item_path("pending", item_id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(item, indent=2))
    src.unlink()
    return {"ok": True}


@router.post("/api/queue/cancel/{item_id}")
def queue_cancel(item_id: str, store: Store):
    src = store.find_queue_item("pending", item_id)
    if not src:
        raise HTTPException(404, "item not found in pending")
    item = json.loads(src.read_text())
    item.update(status="cancelled", result="Cancelled via dashboard",
                completedAt=datetime.now().isoformat())
    dst = store.queue_item_path("done", item_id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(item, indent=2))
    src.unlink()
    return {"ok": True}


@router.post("/api/queue/enqueue")
def queue_enqueue(body: EnqueueBody, store: Store):
    if not body.agent.strip() or not body.input.strip():
        raise HTTPException(422, "agent and input are required")
    item_id = f"manual-{int(time.time())}-{body.agent.strip()}"
    item = {"id": item_id, "agent": body.agent.strip(), "input": body.input.strip(),
            "priority": body.priority, "created": datetime.now().isoformat(),
            "status": "pending"}
    dst = store.queue_item_path("pending", item_id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(item, indent=2))
    return {"ok": True, "id": item_id}


EXIT_MEANINGS = {
    1: "generic error - check the log for the failing command",
    2: "shell usage error (bad arguments)",
    124: "TIMEOUT - the run exceeded its timeout_sec and was killed",
    126: "command found but not executable (permissions)",
    127: "command not found (PATH problem in the scheduled environment)",
    130: "interrupted (SIGINT)",
    137: "killed (SIGKILL - possibly out of memory)",
    143: "terminated (SIGTERM)",
}

_ERR_RE = None


@router.get("/api/runs/{run_id}/diagnose")
def diagnose_run(run_id: int, store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    """Failure explanation: the run's own log segment + known-pattern detection."""
    import re as _re
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    with store.db() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "run not found")
    run = dict(run)
    exit_code = run.get("exit_code")
    meaning = EXIT_MEANINGS.get(exit_code or 0, "")

    segment: list[str] = []
    log_name = None
    if run.get("log_path"):
        log_name = run["log_path"].split("/")[-1]
        path = settings.log_dir / log_name
        if path.is_file():
            lines = path.read_text(errors="replace").splitlines()
            # isolate THIS run's window using the [YYYY-MM-DD HH:MM:SS] stamps
            try:
                start = _dt.strptime(run["started_at"], "%Y-%m-%d %H:%M:%S")
                end = start + _td(seconds=(run.get("duration_sec") or 0) + 90)
                stamp = _re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
                in_window, current = False, None
                for ln in lines:
                    m = stamp.match(ln)
                    if m:
                        current = _dt.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    if current is not None:
                        in_window = start - _td(seconds=5) <= current <= end
                    if in_window:
                        segment.append(ln)
            except (ValueError, TypeError):
                pass
            if not segment:
                segment = lines[-60:]

    # known failure patterns -> targeted hints (generic; site-specific ones
    # come from settings.extra_hints so internal tool names stay out of code)
    text = "\n".join(segment)
    hints: list[str] = []
    for pat, hint in [
        (r"ExpiredToken|AccessDenied|InvalidClientTokenId|credentials",
         "AWS credentials issue - refresh the profile used by this job"),
        (r"ModuleNotFoundError|ImportError", "Python dependency missing in the job's environment"),
        (r"command not found|No such file",
         "Missing binary or wrong path (scheduler PATH differs from your shell)"),
        (r"AUTH_ERROR|429|rate.?limit", "Rate limited - the job should back off and retry"),
        (r"BrokenPipeError|MCP error|Connection closed",
         "An MCP server failed to start or dropped - check its auth/registry"),
        (r"timed out|TimeoutExpired", "A step inside the run timed out"),
        (r"Traceback", "Python exception - the traceback below has the root cause"),
        *[(p, h) for p, h in settings.extra_hints],
    ]:
        if _re.search(pat, text, _re.IGNORECASE):
            hints.append(hint)

    # exit-code based hints come first (log text may not mention the cause)
    if exit_code == 124:
        hints.insert(0, f'TIMEOUT: the run hit its timeout and was killed after '
                        f'{run.get("duration_sec")}s - raise timeout_sec or investigate the hang')
    elif exit_code == 137:
        hints.insert(0, 'SIGKILL (137): likely out of memory or force-killed')
    elif exit_code == 127:
        hints.insert(0, 'Command not found (127): PATH in the scheduler differs from your shell')

    err = _re.compile(r"error|fail|exception|traceback|denied|timed.?out|fatal|no such|BLOCKER",
                      _re.IGNORECASE)
    error_lines = [ln.strip()[:300] for ln in segment if err.search(ln)][-20:]
    return {"run": run, "exit_meaning": meaning, "hints": hints,
            "error_lines": error_lines, "segment_tail": segment[-40:], "log": log_name}


@router.get("/api/backlog")
def api_backlog(settings: Annotated[Settings, Depends(get_settings)]):
    """Backlog kanban: reads backlog/*.md frontmatter (v2 parity)."""
    import re as _re
    base = settings.agents_dir / "backlog"
    out = {"active": [], "done": [], "review_notes": []}
    for bucket, d in (("active", base), ("done", base / "done"),
                      ("review_notes", base / "review-notes")):
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            text = f.read_text(errors="replace")
            fm = _re.match(r"^---\s*\n(.*?)\n---", text, _re.DOTALL)
            meta = {}
            if fm:
                for ln in fm.group(1).splitlines():
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        meta[k.strip()] = v.strip()
            title_m = _re.search(r"^#\s+(.+)$", text, _re.MULTILINE)
            out[bucket].append({
                "file": f.name,
                "title": title_m.group(1) if title_m else f.stem,
                "autonomy": meta.get("autonomy", ""),
                "agent": meta.get("agent", ""),
                "priority": meta.get("priority", ""),
                "created": meta.get("created", ""),
                "order": meta.get("order", ""),
            })

    def _order_key(item: dict) -> tuple:
        try:
            return (0, int(item["order"]), item["file"])
        except (ValueError, TypeError):
            return (1, 0, item["file"])

    out["active"].sort(key=_order_key)
    return out


@router.post("/api/supervisor/job/{job_id}/toggle")
def toggle_job(job_id: str, store: Store, settings: Annotated[Settings, Depends(get_settings)]):
    """Enable/disable a scheduled job (writes schedule.json, v2 parity)."""
    sched = store.load_schedule()
    job = next((j for j in sched.get("jobs", []) if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "job not found")
    job["enabled"] = not job.get("enabled", True)
    settings.schedule_path.write_text(json.dumps(sched, indent=2, ensure_ascii=False))
    return {"ok": True, "enabled": job["enabled"]}


class CronBody(BaseModel):
    cron: str


@router.post("/api/supervisor/job/{job_id}/cron")
def edit_cron(job_id: str, body: CronBody, store: Store,
              settings: Annotated[Settings, Depends(get_settings)]):
    """Inline cron editing (v2 parity). Validates 5-field cron shape."""
    import re as _re
    cron = body.cron.strip()
    if not _re.fullmatch(r"[\d*,/\-]+(\s+[\d*,/\-]+){4}", cron):
        raise HTTPException(422, "invalid cron expression (expected 5 fields)")
    sched = store.load_schedule()
    job = next((j for j in sched.get("jobs", []) if j["id"] == job_id), None)
    if not job:
        raise HTTPException(404, "job not found")
    job["cron"] = cron
    settings.schedule_path.write_text(json.dumps(sched, indent=2, ensure_ascii=False))
    return {"ok": True, "cron": cron}


# ── Backlog actions (v2 parity: decide on review notes from the UI) ─


class BacklogFileBody(BaseModel):
    file: str


class AutonomyBody(BacklogFileBody):
    autonomy: str


class DiscussBody(BacklogFileBody):
    feedback: str


class RejectBody(BacklogFileBody):
    reason: str = ""


class DeleteBody(BacklogFileBody):
    bucket: str = "active"


def _safe_md(file: str) -> str:
    """Reject path traversal; backlog files are bare *.md names."""
    from pathlib import Path as _P
    if file != _P(file).name or not file.endswith(".md"):
        raise HTTPException(400, "invalid filename")
    return file


def _set_frontmatter_field(path, field: str, value: str) -> None:
    """Set (replace or append) one frontmatter field, creating the block if absent."""
    import re as _re
    text = path.read_text(errors="replace")
    fm = _re.match(r"^---\s*\n(.*?)\n---\s*\n", text, _re.DOTALL)
    if fm:
        body = fm.group(1)
        if _re.search(rf"^{field}:\s*.*$", body, _re.MULTILINE):
            new_body = _re.sub(rf"^{field}:\s*.*$", f"{field}: {value}", body,
                               count=1, flags=_re.MULTILINE)
        else:
            new_body = body.rstrip() + f"\n{field}: {value}"
        text = text.replace(fm.group(0), f"---\n{new_body}\n---\n", 1)
    else:
        text = f"---\n{field}: {value}\n---\n\n" + text
    path.write_text(text)


def _set_note_feedback(path, label: str, message: str) -> None:
    """Replace or append the '## Human feedback' section of a review note."""
    import re as _re
    text = path.read_text(errors="replace")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"## Human feedback\n\n> {label} {stamp}:\n\n{message}\n"
    if _re.search(r"^## Human feedback\b", text, _re.MULTILINE):
        text = _re.sub(r"^## Human feedback\n.*?(?=^## |\Z)", block + "\n",
                       text, count=1, flags=_re.DOTALL | _re.MULTILINE)
    else:
        text = text.rstrip() + "\n\n" + block
    path.write_text(text)


@router.post("/api/backlog/autonomy")
def backlog_autonomy(body: AutonomyBody,
                     settings: Annotated[Settings, Depends(get_settings)]):
    """Change a backlog item's autonomy via its frontmatter (auto/review/blocked)."""
    value = body.autonomy.strip().lower()
    if value not in ("auto", "review", "blocked"):
        raise HTTPException(422, "invalid autonomy (use auto/review/blocked)")
    path = settings.agents_dir / "backlog" / _safe_md(body.file)
    if not path.is_file():
        raise HTTPException(404, "backlog item not found")
    _set_frontmatter_field(path, "autonomy", value)
    return {"ok": True, "autonomy": value}


@router.post("/api/backlog/review-note/approve")
def review_note_approve(body: BacklogFileBody,
                        settings: Annotated[Settings, Depends(get_settings)]):
    """Approve: flip the BACKLOG ITEM's autonomy to auto. Next meta-agent run applies."""
    path = settings.agents_dir / "backlog" / _safe_md(body.file)
    if not path.is_file():
        raise HTTPException(404, "backlog item not found")
    _set_frontmatter_field(path, "autonomy", "auto")
    return {"ok": True, "message": "approved - will apply on next meta-agent run"}


@router.post("/api/backlog/review-note/discuss")
def review_note_discuss(body: DiscussBody,
                        settings: Annotated[Settings, Depends(get_settings)]):
    """Send feedback: note status -> discussing + Human feedback section."""
    if not body.feedback.strip():
        raise HTTPException(422, "feedback is required")
    path = settings.agents_dir / "backlog" / "review-notes" / _safe_md(body.file)
    if not path.is_file():
        raise HTTPException(404, "review note not found")
    _set_frontmatter_field(path, "status", "discussing")
    _set_note_feedback(path, "Added", body.feedback.strip())
    return {"ok": True, "message": "feedback saved - will regenerate on next meta-agent run"}


@router.post("/api/backlog/review-note/reject")
def review_note_reject(body: RejectBody,
                       settings: Annotated[Settings, Depends(get_settings)]):
    """Reject: note status -> rejected. The agent will NOT regenerate it."""
    path = settings.agents_dir / "backlog" / "review-notes" / _safe_md(body.file)
    if not path.is_file():
        raise HTTPException(404, "review note not found")
    _set_frontmatter_field(path, "status", "rejected")
    if body.reason.strip():
        _set_note_feedback(path, "Rejected", body.reason.strip())
    return {"ok": True, "message": "rejected - agent will not regenerate"}


@router.post("/api/backlog/delete")
def backlog_delete(body: DeleteBody,
                   settings: Annotated[Settings, Depends(get_settings)]):
    """Soft-delete: move the item (and its review note, if any) to deleted/ folders."""
    file = _safe_md(body.file)
    base = settings.agents_dir / "backlog"
    src = (base / "done" / file) if body.bucket == "done" else (base / file)
    if not src.is_file():
        raise HTTPException(404, "backlog item not found")
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    stem = file[:-3]
    deleted = base / "deleted"
    deleted.mkdir(parents=True, exist_ok=True)
    src.rename(deleted / f"{stem}-{ts}.md")
    note = base / "review-notes" / file
    note_moved = False
    if note.is_file():
        note_deleted = base / "review-notes" / "deleted"
        note_deleted.mkdir(parents=True, exist_ok=True)
        note.rename(note_deleted / f"{stem}-{ts}.md")
        note_moved = True
    return {"ok": True, "note_moved": note_moved}


class ReorderBody(BaseModel):
    files: list[str]


@router.post("/api/backlog/reorder")
def backlog_reorder(body: ReorderBody,
                    settings: Annotated[Settings, Depends(get_settings)]):
    """Persist the kanban order: write `order: <index>` into each item's frontmatter.

    Missing files are skipped silently (the board may be stale); the response
    says how many were actually updated.
    """
    if not body.files:
        raise HTTPException(422, "files is required")
    base = settings.agents_dir / "backlog"
    safe = [_safe_md(f) for f in body.files]  # reject traversal BEFORE any write
    updated = 0
    for idx, fname in enumerate(safe):
        path = base / fname
        if not path.is_file():
            continue
        _set_frontmatter_field(path, "order", str(idx))
        updated += 1
    return {"ok": True, "updated": updated}


@router.get("/api/backlog/item")
def backlog_item(bucket: str, file: str,
                 settings: Annotated[Settings, Depends(get_settings)]):
    """Full markdown content of a backlog/review-note item."""
    dirs = {"active": "", "done": "done", "review_notes": "review-notes"}
    if bucket not in dirs or "/" in file or ".." in file or not file.endswith(".md"):
        raise HTTPException(400, "invalid bucket or file")
    path = settings.agents_dir / "backlog" / dirs[bucket] / file
    if not path.is_file():
        raise HTTPException(404, "item not found")
    text = path.read_text(errors="replace")
    # strip frontmatter for the body (meta is already in the list payload)
    import re as _re
    body = _re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=_re.DOTALL)
    return {"file": file, "bucket": bucket, "content": body}
