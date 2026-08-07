"""Real-time event channel (/ws/events).

A single server-side watcher polls the ecosystem artifacts every second
(runs.db max id, queue dir state, active locks) and broadcasts typed
events to all connected clients. No supervisor changes required - the
dashboard stays a pure consumer.

Event schema: {"type": str, "ts": iso8601, "payload": dict}
Types: run.finished · queue.changed · agents.running_changed
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .config import get_settings
from .datastore import Datastore

router = APIRouter()
_clients: set[WebSocket] = set()
_watcher_task: asyncio.Task | None = None


async def _broadcast(event_type: str, payload: dict) -> None:
    msg = json.dumps({"type": event_type, "ts": datetime.now().isoformat(), "payload": payload})
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            _clients.discard(ws)


async def _watcher() -> None:
    store = Datastore(get_settings())
    last_run_id: int | None = None
    last_queue: dict[str, int] | None = None
    last_running: set[str] = set()
    while True:
        await asyncio.sleep(1)
        with contextlib.suppress(Exception):
            # new finished runs
            with store.db() as conn:
                row = conn.execute("SELECT MAX(id) m FROM runs").fetchone()
                max_id = row["m"] or 0
                if last_run_id is not None and max_id > last_run_id:
                    new = conn.execute(
                        "SELECT id, job_id, status, duration_sec FROM runs WHERE id > ?",
                        (last_run_id,)).fetchall()
                    for r in new:
                        await _broadcast("run.finished", dict(r))
                last_run_id = max_id
            # queue counts
            counts = store.queue_counts()
            if last_queue is not None and counts != last_queue:
                await _broadcast("queue.changed", counts)
            last_queue = counts
            # running agents (locks)
            running = set(store.active_locks())
            if running != last_running:
                await _broadcast("agents.running_changed", {"running": sorted(running)})
            last_running = running


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    global _watcher_task
    await ws.accept()
    _clients.add(ws)
    if _watcher_task is None or _watcher_task.done():
        _watcher_task = asyncio.create_task(_watcher())
    try:
        while True:
            await ws.receive_text()  # keepalive pings from client
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        _clients.discard(ws)
