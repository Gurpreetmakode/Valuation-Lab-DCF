import sys
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


# Serve Vite assets: /assets/...
if FRONTEND_ASSETS.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_ASSETS)),
        name="assets",
    )


@app.get("/")
def serve_frontend_root():
    index_file = FRONTEND_DIST / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "detail": "frontend/dist/index.html not found. Vercel build may not have run.",
    }


@app.get("/{full_path:path}")
def serve_frontend_spa(full_path: str):
    """
    Serve React SPA routes.

    Existing /api/... routes from backend/app/main.py should match before this.
    If no static file exists, return index.html for client-side routing.
    """
    requested_file = FRONTEND_DIST / full_path

    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = FRONTEND_DIST / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "detail": "frontend/dist/index.html not found. Vercel build may not have run.",
    }