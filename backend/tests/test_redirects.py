"""Moved routes: a page that used to live here must not become a dead end.

Born from a real defect. A route was removed from this repo (it rendered a
personal page and did not belong in a public product) and the page moved to
another local server. Everything worked - except for the person whose bookmark
still pointed here, who got the not-found page and no idea where the page went.
Removing an address is not enough: it has to forward.

The map is configuration, never code, so the destination URL (which is
site-specific) never enters this repo.
"""
import json

from fastapi.testclient import TestClient

from dashboard.config import build_settings
from dashboard.main import create_app


def _client(monkeypatch, redirects: dict[str, str] | None = None) -> TestClient:
    monkeypatch.setenv("DASHBOARD_REDIRECTS", json.dumps(redirects or {}))
    build_settings.cache_clear() if hasattr(build_settings, "cache_clear") else None
    from dashboard import config
    config.get_settings.cache_clear()
    # follow_redirects=False: we are asserting the redirect itself, not its target
    return TestClient(create_app(), follow_redirects=False)


def test_configured_path_redirects_to_its_new_home(monkeypatch):
    dest = "http://localhost:7781/mission-control"
    c = _client(monkeypatch, {"/mission-control": dest})
    r = c.get("/mission-control")
    assert r.status_code == 307, "moved page must forward, not 404 and not 200"
    assert r.headers["location"] == dest


def test_redirect_is_temporary_so_it_stays_reversible(monkeypatch):
    """A permanent redirect (301/308) is cached hard by browsers and is painful
    to undo - if the destination changes, the operator is stuck. Temporary keeps
    the decision reversible, which is the house rule."""
    c = _client(monkeypatch, {"/x": "http://localhost:7781/x"})
    assert c.get("/x").status_code == 307


def test_trailing_slash_is_the_same_page(monkeypatch):
    dest = "http://localhost:7781/mission-control"
    c = _client(monkeypatch, {"/mission-control": dest})
    assert c.get("/mission-control/").headers.get("location") == dest


def test_unconfigured_path_is_untouched(monkeypatch):
    """No config, no redirect: a fresh install must behave exactly as before."""
    c = _client(monkeypatch, {})
    r = c.get("/mission-control")
    assert r.status_code != 307, "nothing should redirect without configuration"


def test_api_routes_are_never_shadowed(monkeypatch):
    """A careless map entry must not be able to hijack the API."""
    c = _client(monkeypatch, {"/api/overview": "http://evil.example/x"})
    r = c.get("/api/overview")
    assert r.status_code != 307, "API routes must win over the redirect map"
