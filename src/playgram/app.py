from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from playgram.api.routes import router as api_router
from playgram.db.core import init_db

app = FastAPI(title="playgram", version="0.1.0")

app.include_router(api_router)

# UI is served from packaged static folder
app.mount("/ui", StaticFiles(packages=[("playgram", "ui")], html=True), name="ui")


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    path = Path(__file__).resolve().parents[2] / "favicon.ico"
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.get("/favicon.svg", include_in_schema=False)
def favicon_svg():
    path = Path(__file__).resolve().parents[2] / "favicon.svg"
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path)


