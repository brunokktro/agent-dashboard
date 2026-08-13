"""Pipe mode v2: relay a prompt through a chain of agents - VERBOSE and durable.

- Output streams incrementally: the UI shows what the agent is doing (tool
  calls, progress) while it runs, not just the final answer.
- Jobs persist to disk (<agents_dir>/pipe-jobs/), surviving backend restarts.
- Each step has a hard deadline (STEP_TIMEOUT).
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import pty as _pty
import re
import struct
import termios
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .datastore import Datastore

router = APIRouter()

_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|[\r\x08]")
_jobs: dict[str, dict] = {}

STEP_TIMEOUT = 600  # 10 min per agent
MAX_OUT = 12_000
# A fresh pty is born 0x0. A CLI that wraps to the terminal width then breaks
# its output into one-word lines (a 25-line answer became 237 "lines"), so the
# window has to be set explicitly before the child starts.
PTY_ROWS, PTY_COLS = 50, 200


def _set_pty_size(fd: int, rows: int = PTY_ROWS, cols: int = PTY_COLS) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class PipeRequest(BaseModel):
    prompt: str = Field(min_length=1)
    agents: list[str] = Field(min_length=1, max_length=4)


def _jobs_dir(settings: Settings):
    d = settings.agents_dir / "pipe-jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _persist(settings: Settings, job_id: str) -> None:
    with contextlib.suppress(OSError):
        (_jobs_dir(settings) / f"{job_id}.json").write_text(json.dumps(_jobs[job_id]))


def _clean(raw: str) -> str:
    text = _ANSI.sub("", raw)
    return "\n".join(ln for ln in text.splitlines()
                     if not re.match(r"\s*▸\s*Credits:", ln)).strip()


async def _run_chain(settings: Settings, job_id: str) -> None:
    job = _jobs[job_id]
    current_prompt = job["prompt"]
    for step in job["steps"]:
        step["status"] = "running"
        step["started"] = time.time()
        if step is not job["steps"][0]:
            step["received"] = current_prompt[:600]
        _persist(settings, job_id)
        raw = b""
        master = None
        try:
            # PTY: kiro-cli line-buffers only on a tty -> real live streaming
            master, slave = _pty.openpty()
            _set_pty_size(slave)  # 0x0 would wrap the output one word per line
            proc = await asyncio.create_subprocess_exec(
                "kiro-cli", "chat", "--agent", step.get("cli_name") or step["agent"],
                "--no-interactive", "--trust-all-tools",
                stdin=asyncio.subprocess.PIPE,
                stdout=slave, stderr=slave,
            )
            os.close(slave)
            proc.stdin.write(current_prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            transport, _ = await loop.connect_read_pipe(
                lambda reader=reader: asyncio.StreamReaderProtocol(reader), os.fdopen(master, "rb"))
            master = None  # owned by transport now
            deadline = time.time() + STEP_TIMEOUT
            last_flush = 0.0
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    proc.kill()
                    transport.close()
                    raise TimeoutError
                try:
                    chunk = await asyncio.wait_for(reader.read(4096),
                                                   timeout=min(remaining, 1))
                except TimeoutError:
                    continue  # no output yet - keep waiting until deadline
                except OSError:
                    break  # pty closed on process exit
                if not chunk:
                    break
                raw += chunk
                # stream to UI at most twice a second
                if time.time() - last_flush > 0.5:
                    step["output"] = _clean(raw.decode(errors="replace"))[-MAX_OUT:]
                    _persist(settings, job_id)
                    last_flush = time.time()
            await proc.wait()
            output = _clean(raw.decode(errors="replace"))
            step["output"] = output[-MAX_OUT:]
            if proc.returncode != 0:
                step["status"] = "failed"
                job["status"] = "failed"
                _persist(settings, job_id)
                return
            step["status"] = "done"
            _persist(settings, job_id)
            current_prompt = (
                f"The previous agent ({step['agent']}) produced this output:\n\n{output}\n\n"
                f"Original request: {job['prompt']}\nContinue the work from your own role."
            )
        except TimeoutError:
            step["status"] = "failed"
            step["output"] = ((step.get("output") or "") +
                              f"\n\n[timed out after {STEP_TIMEOUT}s]").strip()
            job["status"] = "failed"
            _persist(settings, job_id)
            return
        except Exception as e:  # noqa: BLE001 - surface anything to the UI
            step["status"] = "failed"
            step["output"] = str(e)
            job["status"] = "failed"
            _persist(settings, job_id)
            return
        finally:
            if master is not None:
                with contextlib.suppress(OSError):
                    os.close(master)
    job["status"] = "done"
    _persist(settings, job_id)


@router.post("/api/pipe/start")
async def pipe_start(body: PipeRequest, settings: Annotated[Settings, Depends(get_settings)]):
    # kiro-cli resolves --agent by the name INSIDE the json config, which can
    # differ from the dashboard's name (the filename stem). Resolve here so
    # the chain runs; the step keeps the dashboard name for display.
    agents = Datastore(settings).load_agents()
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "running",
        "prompt": body.prompt,
        "steps": [{"agent": a, "status": "pending", "output": "",
                   "cli_name": agents.get(a, {}).get("cli_name", a)}
                  for a in body.agents],
    }
    _persist(settings, job_id)
    asyncio.get_event_loop().create_task(_run_chain(settings, job_id))
    return {"id": job_id}


@router.get("/api/pipe/{job_id}")
def pipe_status(job_id: str, settings: Annotated[Settings, Depends(get_settings)]):
    job = _jobs.get(job_id)
    if not job:
        # disk fallback: job from before a backend restart
        path = _jobs_dir(settings) / f"{job_id}.json"
        if path.exists():
            job = json.loads(path.read_text())
            if job.get("status") == "running":
                # the process died with the old backend - mark honestly
                job["status"] = "lost"
                for s in job["steps"]:
                    if s["status"] == "running":
                        s["status"] = "failed"
                        s["output"] = ((s.get("output") or "") +
                                       "\n\n[backend restarted - job lost, run again]").strip()
                path.write_text(json.dumps(job))
            return job
        raise HTTPException(404, "job not found")
    return job
