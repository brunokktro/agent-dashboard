"""Observability endpoints: duration percentiles, success timeline, day-hour heatmap."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from .config import Settings, get_settings
from .datastore import Datastore

router = APIRouter()


def _store(settings: Annotated[Settings, Depends(get_settings)]) -> Datastore:
    return Datastore(settings)

Store = Annotated[Datastore, Depends(_store)]


def _pct(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, round(p * (len(sorted_vals) - 1))))
    return sorted_vals[k]


@router.get("/api/observability/agent/{name}")
def agent_observability(name: str, store: Store, days: int = 30):
    """Per-day P50/P95/P99 duration + success rate for one agent (last N days)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with store.db() as conn:
        rows = conn.execute(
            "SELECT date(started_at) d, duration_sec, status FROM runs "
            "WHERE (job_id = ? OR job_id LIKE ?) AND started_at >= ? ORDER BY d",
            (name, f"{name}-%", cutoff),
        ).fetchall()
    by_day: dict[str, dict] = {}
    for r in rows:
        day = by_day.setdefault(r["d"], {"durs": [], "ok": 0, "fail": 0})
        if r["duration_sec"] is not None:
            day["durs"].append(r["duration_sec"])
        if r["status"] == "success":
            day["ok"] += 1
        elif r["status"] == "failed":
            day["fail"] += 1
    series = []
    for d in sorted(by_day):
        durs = sorted(by_day[d]["durs"])
        ok, fail = by_day[d]["ok"], by_day[d]["fail"]
        series.append({
            "date": d,
            "p50": _pct(durs, 0.50), "p95": _pct(durs, 0.95), "p99": _pct(durs, 0.99),
            "runs": ok + fail,
            "success_rate": round(ok * 100 / (ok + fail)) if (ok + fail) else None,
        })
    return {"agent": name, "days": days, "series": series}


@router.get("/api/observability/heatmap")
def heatmap(store: Store, days: int = 30):
    """Day-of-week x hour matrix of run counts + failures (Datadog-style)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with store.db() as conn:
        rows = conn.execute(
            "SELECT strftime('%w', started_at) dow, strftime('%H', started_at) hour, "
            "COUNT(*) n, SUM(status='failed') fails FROM runs WHERE started_at >= ? "
            "GROUP BY dow, hour", (cutoff,),
        ).fetchall()
    cells = [{"dow": int(r["dow"]), "hour": int(r["hour"]),
              "runs": r["n"], "fails": r["fails"] or 0} for r in rows]
    return {"days": days, "cells": cells}
