from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import gcp_client

app = FastAPI(title="RAPIRO Dashboard", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/events")
def events(limit: int = 50):
    try:
        return gcp_client.get_recent_events(limit=min(limit, 100))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stats")
def stats():
    try:
        return gcp_client.get_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/images")
def images(limit: int = 20):
    try:
        return gcp_client.get_unknown_images(limit=min(limit, 50))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/clear")
def clear():
    try:
        deleted = gcp_client.clear_all_events()
        return {"deleted": deleted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", "8080"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
