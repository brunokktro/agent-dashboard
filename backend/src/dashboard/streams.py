"""Streaming endpoints: SSE log tail + persistent PTY terminal sessions.

Terminal sessions are registered server-side by id. A page refresh or WS
drop does NOT kill the PTY: the client reconnects with the same session id
and reattaches (receiving the recent output buffer). Idle detached sessions
are reaped after IDLE_TTL.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import struct
import termios
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .config import Settings, get_settings

router = APIRouter()

IDLE_TTL = 15 * 60  # keep detached PTYs for 15 minutes
BUFFER_BYTES = 200_000
# A pty is born 0x0, so anything the shell prints before xterm.js sends its
# first resize would wrap one word per line. Start from a sane window.
INITIAL_ROWS, INITIAL_COLS = 24, 100


# ── Log endpoints ────────────────────────────────────────────────────


def _safe_log(settings: Settings, name: str):
    if "/" in name or ".." in name or not name.endswith(".log"):
        raise HTTPException(400, "invalid log name")
    path = settings.log_dir / name
    if not path.is_file():
        raise HTTPException(404, "log not found")
    return path


@router.get("/api/logs/{name}/tail")
def log_tail(name: str, settings: Annotated[Settings, Depends(get_settings)], lines: int = 200):
    path = _safe_log(settings, name)
    content = path.read_text(errors="replace").splitlines()
    return {"name": name, "lines": content[-lines:], "size_kb": path.stat().st_size // 1024}


@router.get("/logs/stream/{name}")
async def log_stream(name: str, settings: Annotated[Settings, Depends(get_settings)]):
    path = _safe_log(settings, name)

    async def generate():
        lines = path.read_text(errors="replace").splitlines()
        for line in lines[-100:]:
            yield f"data: {line}\n\n"
        last_size = path.stat().st_size
        while True:
            await asyncio.sleep(1)
            try:
                size = path.stat().st_size
            except OSError:
                break
            if size < last_size:
                last_size = 0
            if size > last_size:
                with path.open(errors="replace") as f:
                    f.seek(last_size)
                    for line in f.read().splitlines():
                        yield f"data: {line}\n\n"
                last_size = size

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ── Persistent terminal sessions ─────────────────────────────────────


@dataclass
class PtySession:
    fd: int
    pid: int
    buffer: deque[bytes] = field(default_factory=lambda: deque(maxlen=400))
    buffer_size: int = 0
    client: WebSocket | None = None
    detached_at: float | None = None
    reading: bool = False


_sessions: dict[str, PtySession] = {}
_reaper: asyncio.Task | None = None


def _spawn(session_id: str) -> PtySession:
    shell = os.environ.get("SHELL", "/bin/zsh")
    pid, fd = pty.fork()
    if pid == 0:  # child
        # set the window before exec so the first prompt is not wrapped at 0 cols
        with contextlib.suppress(OSError):
            fcntl.ioctl(0, termios.TIOCSWINSZ,
                        struct.pack("HHHH", INITIAL_ROWS, INITIAL_COLS, 0, 0))
        os.chdir(Path.home())
        os.execvp(shell, [shell, "-l"])
        raise SystemExit(0)
    sess = PtySession(fd=fd, pid=pid)
    _sessions[session_id] = sess
    return sess


def _kill(session_id: str) -> None:
    sess = _sessions.pop(session_id, None)
    if not sess:
        return
    loop = asyncio.get_event_loop()
    with contextlib.suppress(Exception):
        loop.remove_reader(sess.fd)
    with contextlib.suppress(OSError):
        os.close(sess.fd)
    with contextlib.suppress(OSError, ProcessLookupError):
        os.kill(sess.pid, 15)


async def _reap_idle() -> None:
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for sid, sess in list(_sessions.items()):
            if sess.client is None and sess.detached_at and now - sess.detached_at > IDLE_TTL:
                _kill(sid)


def _attach_reader(session_id: str) -> None:
    """One reader per PTY, forever: fills the buffer and forwards to the live client."""
    sess = _sessions[session_id]
    if sess.reading:
        return
    loop = asyncio.get_event_loop()

    def on_readable():
        try:
            data = os.read(sess.fd, 65536)
        except OSError:
            _kill(session_id)
            return
        if not data:
            _kill(session_id)
            return
        sess.buffer.append(data)
        sess.buffer_size = sum(len(b) for b in sess.buffer)
        while sess.buffer_size > BUFFER_BYTES and len(sess.buffer) > 1:
            sess.buffer_size -= len(sess.buffer.popleft())
        if sess.client is not None:
            ws = sess.client
            asyncio.ensure_future(_safe_send(ws, data, session_id))

    loop.add_reader(sess.fd, on_readable)
    sess.reading = True


async def _safe_send(ws: WebSocket, data: bytes, session_id: str) -> None:
    try:
        await ws.send_bytes(data)
    except Exception:
        sess = _sessions.get(session_id)
        if sess and sess.client is ws:
            sess.client = None
            sess.detached_at = time.time()


@router.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket, session: str = ""):
    global _reaper
    await ws.accept()
    if _reaper is None or _reaper.done():
        _reaper = asyncio.create_task(_reap_idle())

    session_id = session or f"anon-{id(ws)}"
    existing = _sessions.get(session_id)
    if existing:
        # reattach: replay recent buffer
        existing.client = ws
        existing.detached_at = None
        for chunk in list(existing.buffer):
            with contextlib.suppress(Exception):
                await ws.send_bytes(chunk)
        await ws.send_bytes(b"\r\n\x1b[2m[reattached]\x1b[0m\r\n")
        sess = existing
        is_new = False
    else:
        sess = _spawn(session_id)
        sess.client = ws
        is_new = True

    _attach_reader(session_id)
    with contextlib.suppress(Exception):
        await ws.send_text('{"control":"ready","new":%s}' % ("true" if is_new else "false"))

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes") or (msg.get("text") or "").encode()
            if data.startswith(b"\x01"):  # resize
                with contextlib.suppress(ValueError, OSError):
                    cols, rows = map(int, data[1:].decode().split(","))
                    fcntl.ioctl(sess.fd, termios.TIOCSWINSZ,
                                struct.pack("HHHH", rows, cols, 0, 0))
                continue
            if data.startswith(b"\x02kill"):  # explicit close from UI
                _kill(session_id)
                break
            with contextlib.suppress(OSError):
                os.write(sess.fd, data)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        cur = _sessions.get(session_id)
        if cur and cur.client is ws:
            cur.client = None
            cur.detached_at = time.time()
