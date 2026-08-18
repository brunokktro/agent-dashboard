"""App factory. Serves the API plus the built frontend (frontend/dist) when present."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router
from .config import get_settings
from .events import router as events_router
from .observability import router as obs_router
from .pipe import router as pipe_router
from .streams import router as streams_router

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

# Cache policy for a hashed-asset SPA, and the reason it matters here: without
# it the browser heuristically caches index.html, keeps pointing at the PREVIOUS
# bundle hash, and the user stays on the old app after an update - which would
# quietly defeat the update-check button ("update available" -> pull -> still
# the old UI). So the shell always revalidates (cheap: ETag answers 304), while
# the fingerprinted assets are immutable by construction.
_HTML_CACHE = "no-cache"                          # revalidate every load
_ASSET_CACHE = "public, max-age=31536000, immutable"  # the hash IS the version


class _HashedAssets(StaticFiles):
    """StaticFiles that marks fingerprinted files as immutable."""

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = _ASSET_CACHE
        return resp


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Dashboard", version=__version__)
    app.include_router(router)
    app.include_router(streams_router)
    app.include_router(obs_router)
    app.include_router(events_router)
    app.include_router(pipe_router)

    # A page this dashboard no longer serves forwards to its new home. This is
    # middleware, not a route, for a concrete reason: the SPA fallback is already
    # a catch-all (`/{full_path:path}`), so a second catch-all would either
    # shadow it (404-ing the whole UI) or have to duplicate it. Middleware runs
    # before routing and only acts on a configured path, leaving everything else
    # untouched. Temporary (307) on purpose: a permanent redirect is cached hard
    # by browsers and painful to undo if the destination moves again.
    @app.middleware("http")
    async def forward_moved_pages(request, call_next):
        redirects = get_settings().redirects
        if redirects:
            path = "/" + request.url.path.strip("/")
            dest = redirects.get(path)
            # never let a map entry shadow the API or the built assets
            if dest and not path.startswith(("/api/", "/assets/")):
                return RedirectResponse(dest, status_code=307)
        return await call_next(request)

    if FRONTEND_DIST.exists():
        app.mount("/assets", _HashedAssets(directory=FRONTEND_DIST / "assets"),
                  name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            """Serve the SPA for any non-API route (client-side routing)."""
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                # non-hashed extras (favicon, help screenshots): revalidate too,
                # they are replaced in place by a rebuild
                return FileResponse(candidate, headers={"Cache-Control": _HTML_CACHE})
            return FileResponse(FRONTEND_DIST / "index.html",
                                headers={"Cache-Control": _HTML_CACHE})

    return app


app = create_app()


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("dashboard.main:app", host=s.host, port=s.port)


if __name__ == "__main__":
    main()
