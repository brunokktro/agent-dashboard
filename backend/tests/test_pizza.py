"""Pizza Bot sidecar health integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard import pizza
from dashboard.main import create_app


def test_status_reports_healthy_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PIZZA_URL", "http://127.0.0.1:7782")
    monkeypatch.setattr(
        pizza,
        "_get_json",
        lambda path: {"status": "Healthy"}
        if path == "/ping"
        else {"service": "pizza-bot", "protocolVersion": 1, "apiVersion": "1"},
    )

    status = pizza.build_status()

    assert status["available"] is True
    assert status["healthy"] is True
    assert status["compatible"] is True
    assert status["web_url"] == "http://127.0.0.1:7782"


def test_status_rejects_wrong_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PIZZA_URL", "http://localhost:7782")
    monkeypatch.setattr(
        pizza,
        "_get_json",
        lambda path: {"status": "Healthy"}
        if path == "/ping"
        else {"service": "pizza-bot", "protocolVersion": 2, "apiVersion": "2"},
    )

    status = pizza.build_status()

    assert status["available"] is False
    assert status["healthy"] is True
    assert status["compatible"] is False
    assert status["detail"]


def test_status_degrades_when_sidecar_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PIZZA_URL", "http://127.0.0.1:7782")

    def down(_path: str) -> dict:
        raise ConnectionRefusedError("sidecar unavailable")

    monkeypatch.setattr(pizza, "_get_json", down)
    status = pizza.build_status()

    assert status["available"] is False
    assert status["healthy"] is False
    assert "sidecar unavailable" in status["detail"]


def test_url_must_stay_on_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PIZZA_URL", "https://example.com")
    with pytest.raises(ValueError, match="loopback"):
        pizza.pizza_url()


def test_api_route_is_not_shadowed_by_spa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PIZZA_URL", "http://127.0.0.1:7782")
    monkeypatch.setattr(
        pizza,
        "build_status",
        lambda: {"available": True, "healthy": True, "compatible": True},
    )
    client = TestClient(create_app())

    response = client.get("/api/pizza/status")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["available"] is True
