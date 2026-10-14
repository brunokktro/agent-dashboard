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
