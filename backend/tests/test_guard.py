"""guard.require_same_origin: writes are refused unless Host AND Origin are ours.

The attack it stops is a page in the user's own browser (cross-site form or
DNS rebinding) posting to the loopback server. Each test forges one header.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.config import Settings, get_settings
from dashboard.guard import AllowedHost, SameOrigin, allowed_hosts

OK = {"host": "localhost:7780", "origin": "http://localhost:7780"}


def _client(**settings) -> TestClient:
    app = FastAPI()

    @app.post("/w", dependencies=[SameOrigin])
    def write():
        return {"ok": True}

    @app.get("/r", dependencies=[AllowedHost])
    def read():
        return {"ok": True}

    app.dependency_overrides[get_settings] = lambda: Settings(**settings)
    return TestClient(app)


def test_same_origin_post_is_accepted():
    assert _client().post("/w", headers=OK).status_code == 200


def test_loopback_ip_form_is_accepted():
    h = {"host": "127.0.0.1:7780", "origin": "http://127.0.0.1:7780"}
    assert _client().post("/w", headers=h).status_code == 200


def test_foreign_origin_is_refused():
    r = _client().post("/w", headers={**OK, "origin": "http://evil.example"})
    assert r.status_code == 403
    assert "Origin" in r.json()["detail"]


def test_missing_origin_is_refused_fail_closed():
    assert _client().post("/w", headers={"host": "localhost:7780"}).status_code == 403


def test_rebinding_host_is_refused_even_with_matching_origin():
    """DNS rebinding: the page and the Host header both carry the attacker name."""
    h = {"host": "evil.example:7780", "origin": "http://evil.example:7780"}
    assert _client().post("/w", headers=h).status_code == 403


def test_other_port_is_refused():
    h = {"host": "localhost:7781", "origin": "http://localhost:7781"}
    assert _client().post("/w", headers=h).status_code == 403


def test_https_or_null_origin_is_refused():
    for o in ("https://localhost:7780", "null"):
        assert _client().post("/w", headers={**OK, "origin": o}).status_code == 403


def test_write_hosts_override_replaces_the_default():
    c = _client(write_hosts=["crew.local:9000"])
    assert c.post("/w", headers={"host": "crew.local:9000",
                                 "origin": "http://crew.local:9000"}).status_code == 200
    assert c.post("/w", headers=OK).status_code == 403


def test_default_follows_the_configured_port():
    assert allowed_hosts(Settings(port=8123)) == {"localhost:8123", "127.0.0.1:8123"}


def test_guarded_read_refuses_a_rebinding_host_but_needs_no_origin():
    c = _client()
    assert c.get("/r", headers={"host": "localhost:7780"}).status_code == 200
    assert c.get("/r", headers={"host": "evil.example:7780"}).status_code == 403


# ── WebSocket handshakes (cross-site WebSocket hijacking) ────────────
import pytest  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402


@pytest.mark.parametrize("path", ["/ws/terminal?session=guard-test", "/ws/events"])
@pytest.mark.parametrize("headers", [
    {"host": "localhost:7780", "origin": "http://evil.example"},
    {"host": "evil.example:7780", "origin": "http://localhost:7780"},
    {"host": "evil.example:7780"},
    {"host": "localhost:7780", "origin": "null"},
])
def test_websocket_from_another_site_is_refused(client, path, headers):
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(path, headers=headers):
        pass
    assert exc.value.code == 1008


def test_websocket_events_same_origin_is_accepted(client):
    with client.websocket_connect("/ws/events", headers={
            "host": "localhost:7780", "origin": "http://localhost:7780"}) as ws:
        ws.send_text("ping")
