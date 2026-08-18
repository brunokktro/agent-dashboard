"""App factory. Serves the API plus the built frontend (frontend/dist) when present."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
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

    @app.get("/mission-control", response_class=HTMLResponse, include_in_schema=False)
    async def mission_control_page() -> HTMLResponse:
        """Central de Comandos - NOC pessoal, renderizada ao vivo.

        Precisa vir ANTES do catch-all da SPA: "/{full_path:path}" casa TUDO, e sem esta
        rota o /mission-control devolvia o index.html do frontend com HTTP 200 - falha
        silenciosa que so aparece lendo o <title> (era "frontend", nao "Central de Comandos").

        O renderer e a MESMA fonte que o v2 usa (mission-control-render.py), carregado por
        path em vez de import: o nome tem hifens, entao nao e um modulo importavel.
        """
        import importlib.util as _il

        script = get_settings().scripts_dir / "mission-control-render.py"
        if not script.exists():
            raise HTTPException(status_code=503,
                                detail=f"renderer ausente: {script}")
        spec = _il.spec_from_file_location("mission_control_render", str(script))
        if spec is None or spec.loader is None:
            raise HTTPException(status_code=503, detail="renderer nao carregavel")
        mod = _il.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return HTMLResponse(mod.render(mod.gather()),
                            headers={"Cache-Control": _HTML_CACHE})

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
