"""Health adapter for the loopback Pizza Bot sidecar."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter

router = APIRouter(prefix="/api/pizza", tags=["pizza"])
_DEFAULT_URL = "http://127.0.0.1:7782"


def pizza_url() -> str:
    """Return the configured loopback sidecar URL without a trailing slash."""
    value = os.environ.get("DASHBOARD_PIZZA_URL", _DEFAULT_URL).rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("DASHBOARD_PIZZA_URL must be a loopback HTTP URL")
    return value


def _get_json(path: str) -> dict:
    req = Request(f"{pizza_url()}{path}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=2) as response:  # noqa: S310 - URL is loopback-validated above
        return json.loads(response.read(65_536))


def build_status() -> dict:
    """Probe both liveness and protocol compatibility, never returning fake health."""
    try:
        ping = _get_json("/ping")
        root = _get_json("/")
        healthy = ping.get("status") == "Healthy"
        compatible = root.get("service") == "pizza-bot" and root.get("protocolVersion") == 1
        return {
            "available": healthy and compatible,
            "healthy": healthy,
            "compatible": compatible,
            "detail": (
                None
                if healthy and compatible
                else "Pizza Bot is not ready or protocol v1 is unavailable"
            ),
            "service": root.get("service"),
            "protocol_version": root.get("protocolVersion"),
            "api_version": root.get("apiVersion"),
            "web_url": pizza_url(),
        }
    except (OSError, ValueError, json.JSONDecodeError, HTTPError, URLError) as exc:
        return {
            "available": False,
            "healthy": False,
            "compatible": False,
            "detail": str(exc),
            "service": None,
            "protocol_version": None,
            "api_version": None,
            "web_url": pizza_url() if isinstance(exc, OSError) else _DEFAULT_URL,
        }


@router.get("/status")
def get_status() -> dict:
    return build_status()
