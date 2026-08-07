"""App factory. Serves the API plus the built frontend (frontend/dist) when present."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router
from .config import get_settings
from .events import router as events_router
from .observability import router as obs_router
from .pipe import router as pipe_router
from .streams import router as streams_router

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Dashboard", version=__version__)
    app.include_router(router)
    app.include_router(streams_router)
    app.include_router(obs_router)
    app.include_router(events_router)
    app.include_router(pipe_router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            """Serve the SPA for any non-API route (client-side routing)."""
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run("dashboard.main:app", host=s.host, port=s.port)


if __name__ == "__main__":
    main()
