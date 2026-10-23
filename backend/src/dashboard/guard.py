"""Same-origin guard for write endpoints.

Binding to 127.0.0.1 keeps other machines out, but not other WEBSITES: any
page open in the browser can POST to http://localhost:<port>, and a DNS
rebinding page can even make its own hostname resolve to 127.0.0.1. Two
headers close both doors:

- ``Host`` must be one of ours. A rebinding page talks to us under ITS name,
  so the Host header carries the attacker's hostname.
- ``Origin`` must be one of ours. A cross-site form or fetch carries the
  other site's origin. Browsers always send Origin on a POST, so a missing
  Origin is refused too (fail closed): the only clients that omit it are
  local scripts, and those can set the header explicitly.

Used as a router/endpoint dependency, never as middleware: it must apply to
the endpoints that write, and only to them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings


def allowed_hosts(settings: Settings) -> set[str]:
    """``host:port`` pairs this server answers writes for."""
    if settings.write_hosts:
        return {h.strip().lower() for h in settings.write_hosts if h.strip()}
    return {f"localhost:{settings.port}", f"127.0.0.1:{settings.port}"}


def require_allowed_host(request: Request,
                         settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Refuse (403) a READ whose Host is not ours.

    For reads that aggregate personal data. A cross-site page cannot read our
    responses (no CORS headers), but a DNS-rebinding page can: to the browser
    it is same-origin. Its Host header still carries the attacker's name.
    """
    if (request.headers.get("host") or "").lower() not in allowed_hosts(settings):
        raise HTTPException(403, "read refused: Host not allowed")


def require_same_origin(request: Request,
                        settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Refuse (403) any write whose Host or Origin is not ours, or that is not a POST."""
    if request.method != "POST":
        raise HTTPException(405, "writes are POST only")
    hosts = allowed_hosts(settings)
    host = (request.headers.get("host") or "").lower()
    if host not in hosts:
        raise HTTPException(403, "write refused: Host not allowed")
    origin = (request.headers.get("origin") or "").lower()
    if origin not in {f"http://{h}" for h in hosts}:
        raise HTTPException(403, "write refused: Origin missing or not allowed")


def websocket_allowed(headers, settings: Settings) -> bool:
    """Same-origin check for a WebSocket handshake (cross-site WebSocket hijacking).

    Browsers do not apply CORS to WebSockets: any page can open
    ``ws://localhost:<port>/...`` and the handshake carries that page's Origin.
    ``/ws/terminal`` is a shell, so an unchecked handshake is remote code
    execution from any website. Host must be ours (DNS rebinding); Origin must be
    ours when present. A browser ALWAYS sends Origin on a WebSocket handshake, so
    allowing it to be absent only admits local non-browser clients.
    """
    hosts = allowed_hosts(settings)
    if (headers.get("host") or "").lower() not in hosts:
        return False
    origin = headers.get("origin")
    return origin is None or origin.lower() in {f"http://{h}" for h in hosts}


SameOrigin = Depends(require_same_origin)
AllowedHost = Depends(require_allowed_host)
