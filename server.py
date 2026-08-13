"""KiroCrew app entry point (ASGI shim).

KiroCrew's gateway spawns `uvicorn server:app --port <auto>` from the app
root (backend.type: "asgi" in app.json). The real application lives in
backend/src (src-layout), so this shim just puts it on sys.path and exposes
the FastAPI() instance. Standalone usage is unchanged:
`cd backend && uv run uvicorn dashboard.main:app`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend" / "src"))

from dashboard.main import create_app  # noqa: E402

app = create_app()
