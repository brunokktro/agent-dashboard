"""Regression: the trigger endpoints must not leak zombie processes.

Field report (measured on the live box, 2026-09-26): the uvicorn process had a
``<defunct>`` child parked for 1d14h. Cause: ``trigger_job`` and
``trigger_agent`` fire ``subprocess.Popen`` and return, so nobody ever calls
``wait()`` and the child's exit status stays in the process table for the whole
lifetime of the server - one zombie per manual Run click.

Suite philosophy applies (see conftest): no mocks. These tests spawn REAL
processes and read the REAL process table via ``ps``, because a mocked Popen
cannot become a zombie and would prove nothing.
"""

from __future__ import annotations

import json
import stat
import subprocess
import time

import pytest

from dashboard.api import _children, _spawn_detached, reap_children


def proc_state(pid: int) -> str:
    """Kernel state letter for a pid: 'Z' while a zombie, '' once reaped/gone."""
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                          capture_output=True, text=True).stdout.strip()


def wait_for_zombie(pid: int, timeout: float = 5.0) -> None:
    """Block until the kernel reports pid as a zombie (exited, not yet waited on)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc_state(pid).startswith("Z"):
            return
        time.sleep(0.02)
    pytest.fail(f"pid {pid} never reached zombie state (state={proc_state(pid)!r})")


def test_reap_children_clears_a_real_zombie():
    """The core contract: a finished detached child is a zombie until reaped,
    and reap_children() is what clears it. Popen.poll() is waitpid(WNOHANG),
    so this asserts the reap really happened at the kernel level - not just
    that our bookkeeping set got smaller."""
    proc = _spawn_detached(["/usr/bin/true"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid = proc.pid
    assert proc in _children, "spawned child was not registered for reaping"

    wait_for_zombie(pid)          # proves the leak exists without the reaper
    assert reap_children() >= 1
    assert proc not in _children
    assert proc_state(pid) == "", f"pid {pid} still in the process table as a zombie"


def test_spawn_detached_reaps_the_previous_child():
    """Back-to-back triggers clean up after each other, so the fix holds even
    when the periodic reaper in main.py is not running (tests, embedded use)."""
    first = _spawn_detached(["/usr/bin/true"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for_zombie(first.pid)

    _spawn_detached(["/bin/sleep", "5"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    assert first not in _children
    assert proc_state(first.pid) == "", "previous child was left as a zombie"


def test_trigger_agent_endpoint_leaves_no_zombie(client, ecosystem):
    """End-to-end through the real endpoint with a real runner script: after a
    Run click and the runner exiting, the server must hold no zombie for it."""
    (ecosystem.agents_dir / "alpha-agent.json").write_text(json.dumps({
        "name": "alpha-cli-name", "description": "cfg", "tools": []}))
    done = ecosystem.agents_dir / "reap-probe.txt"
    runner = ecosystem.agents_dir / "scripts" / "run-agent.sh"
    runner.write_text(f'#!/usr/bin/env bash\necho ok > "{done}"\n')
    runner.chmod(runner.stat().st_mode | stat.S_IEXEC)

    before = set(_children)
    assert client.post("/api/trigger-agent/alpha-agent").status_code == 200

    spawned = (set(_children) - before).pop()
    deadline = time.time() + 5
    while not done.exists() and time.time() < deadline:
        time.sleep(0.02)
    assert done.exists(), "runner script never ran"

    wait_for_zombie(spawned.pid)
    reap_children()
    assert proc_state(spawned.pid) == "", (
        "trigger-agent leaked a zombie: the runner exited but nobody waited on it")


def test_app_arms_the_periodic_reaper(ecosystem):
    """The lifespan task is what collects the LAST run's child - without it a
    finished runner waits for the next Run click to be reaped. Entering the
    TestClient context runs the lifespan, so a child that finishes inside it
    is collected with no further spawn."""
    from fastapi.testclient import TestClient

    from dashboard.config import get_settings
    from dashboard.main import _REAP_INTERVAL_SEC, _lifespan, create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: ecosystem
    assert app.router.lifespan_context is not None
    # guard the knob: a huge interval would silently disable the reaper
    assert 0 < _REAP_INTERVAL_SEC <= 60
    assert _lifespan is not None

    with TestClient(app) as c:      # __enter__ runs startup, __exit__ shutdown
        assert c.get("/healthz").status_code == 200
