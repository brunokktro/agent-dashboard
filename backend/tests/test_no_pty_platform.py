"""Platform without a pty (native Windows): regression tests for PR #7.

Run on every OS. The Windows conditions are simulated the way the platform presents them: the
POSIX-only modules are absent at import time, and the capability flag is off at runtime. The real
Windows host validation is recorded on PR #7; these keep the three contracts from regressing.
"""

from __future__ import annotations

import asyncio
import os
import stat
import subprocess
import sys
import textwrap

import pytest
from starlette.websockets import WebSocketDisconnect

from dashboard import pipe, streams

SAME_ORIGIN = {"host": "localhost:7780", "origin": "http://localhost:7780"}


def test_backend_imports_and_serves_without_posix_modules(tmp_path) -> None:
    """The whole app imports and /healthz answers when fcntl, pty and termios do not exist."""
    probe = textwrap.dedent(
        """
        import sys
        class Block:
            def find_spec(self, name, path=None, target=None):
                if name in ("fcntl", "pty", "termios"):
                    raise ModuleNotFoundError(f"No module named {name!r}")
                return None
        sys.meta_path.insert(0, Block())
        for m in ("fcntl", "pty", "termios"):
            sys.modules.pop(m, None)
        from fastapi.testclient import TestClient
        from dashboard import pipe, streams
        from dashboard.main import create_app
        assert streams._HAS_PTY is False and pipe._HAS_PTY is False
        r = TestClient(create_app()).get("/healthz", headers={"host": "localhost:7780"})
        print(r.status_code)
        """
    )
    env = {**os.environ, "HOME": str(tmp_path), "DASHBOARD_AGENTS_DIR": str(tmp_path / "agents")}
    (tmp_path / "agents").mkdir()
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "200"


def test_terminal_websocket_says_unsupported_and_closes_1011(client, monkeypatch) -> None:
    monkeypatch.setattr(streams, "_HAS_PTY", False)
    with client.websocket_connect("/ws/terminal?session=no-pty", headers=SAME_ORIGIN) as ws:
        first = ws.receive_bytes()
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_bytes()
    assert b"not supported on this platform" in first
    assert exc.value.code == 1011


@pytest.mark.skipif(sys.platform == "win32", reason="the fixture kiro-cli is a POSIX shell script")
def test_pipe_chain_runs_over_plain_stdio(ecosystem, tmp_path, monkeypatch) -> None:
    """The no-pty branch feeds the prompt on stdin and captures stdout, step by step."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "kiro-cli"
    fake.write_text('#!/bin/sh\nread line\necho "agent=$3 got: $line"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(pipe, "_HAS_PTY", False)
    job_id = "no-pty-job"
    monkeypatch.setitem(pipe._jobs, job_id, {
        "status": "running", "prompt": "hello",
        "steps": [{"agent": "a1", "status": "pending", "output": "", "cli_name": "a1"},
                  {"agent": "a2", "status": "pending", "output": "", "cli_name": "a2"}],
    })
    asyncio.run(asyncio.wait_for(pipe._run_chain(ecosystem, job_id), timeout=30))
    job = pipe._jobs[job_id]
    assert job["status"] == "done", job
    assert "agent=a1 got: hello" in job["steps"][0]["output"]
    assert job["steps"][1]["status"] == "done"
    assert "agent=a2 got:" in job["steps"][1]["output"]
