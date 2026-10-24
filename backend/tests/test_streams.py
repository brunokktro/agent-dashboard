"""Terminal retention policy tests."""

from dashboard import streams


def _session(*, detached_at: float | None = 100.0, attached: bool = False) -> streams.PtySession:
    return streams.PtySession(
        fd=7,
        pid=42,
        client=object() if attached else None,  # type: ignore[arg-type]
        detached_at=detached_at,
    )


def test_attached_session_is_never_reaped(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_has_foreground_process", lambda _session: False)
    assert not streams._should_reap(_session(attached=True), 100.0 + streams.IDLE_TTL + 1)


def test_idle_detached_shell_uses_short_lease(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_has_foreground_process", lambda _session: False)
    session = _session()
    assert not streams._should_reap(session, 100.0 + streams.IDLE_TTL)
    assert streams._should_reap(session, 100.0 + streams.IDLE_TTL + 1)


def test_active_detached_process_gets_full_turn_lease(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_has_foreground_process", lambda _session: True)
    session = _session()
    assert not streams._should_reap(session, 100.0 + streams.IDLE_TTL + 1)
    assert not streams._should_reap(session, 100.0 + streams.ACTIVE_TTL)
    assert streams._should_reap(session, 100.0 + streams.ACTIVE_TTL + 1)


def test_never_attached_session_is_not_reaped(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_has_foreground_process", lambda _session: False)
    assert not streams._should_reap(_session(detached_at=None), 10_000.0)


# ── Child reaping (issue #9 follow-up, 14/10/2026): closing a session must leave no <defunct> ──
import asyncio  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="PTY sessions are POSIX-only")


def _waitable(pid: int) -> bool:
    """True while `pid` is still our child, alive OR zombie. Collecting it here counts as a leak:
    the code under test should have waited for it already."""
    try:
        os.waitpid(pid, os.WNOHANG)
        return True
    except ChildProcessError:
        return False


def _run_loop(seconds: float) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(asyncio.sleep(seconds))
    finally:
        loop.close()


@posix_only
def test_explicit_close_reaps_shell_and_jobs(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_sessions", {})
    sess = streams._spawn("reap-close")
    os.write(sess.fd, b"sleep 61 &\nsleep 62\n")
    time.sleep(0.5)
    pgid = sess.pid
    streams._kill("reap-close")
    _run_loop(1.5)  # outside a loop _finish runs inline; this drains nothing left behind
    assert not _waitable(sess.pid), "the PTY shell stayed as a waitable child"
    left = os.popen(f"ps -A -o pgid=,stat= | awk '$1=={pgid} && $2 !~ /Z/'").read().strip()
    assert left == "", f"processes survived in the session group: {left!r}"


@posix_only
def test_shell_ignoring_hup_and_term_is_killed_after_grace(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_sessions", {})
    monkeypatch.setattr(streams, "REAP_GRACE", 0.5)
    sess = streams._spawn("reap-stubborn")
    os.write(sess.fd, b'trap "" HUP TERM; sleep 63\n')
    time.sleep(0.5)
    started = time.monotonic()
    streams._kill("reap-stubborn")
    assert not _waitable(sess.pid)
    assert time.monotonic() - started < 3, "reaping must be bounded"


@posix_only
def test_idle_reaper_path_reaps_too(monkeypatch) -> None:
    monkeypatch.setattr(streams, "_sessions", {})
    sess = streams._spawn("reap-idle")
    sess.detached_at = time.time() - streams.IDLE_TTL - 1
    assert streams._should_reap(sess, time.time())
    streams._kill("reap-idle")  # what _reap_idle calls for an expired session
    assert not _waitable(sess.pid)
