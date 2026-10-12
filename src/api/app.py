"""FastAPI app factory. No DB/server started on import."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config.settings import get_settings
from src.api.routes import router

# Project root: src/api/app.py -> parents[0]=api, [1]=src, [2]=root
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Manufacturing Quality Intelligence — Agentic AI (Demo)",
        description="Fictional demo for aluminium powder / plastic component inspection. All data synthetic.",
        version="1.0.0",
    )
    app.state.settings = settings
    # Local-dev CORS so index.html also works when opened from disk (?api=...).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    # Static HTML/CSS/JS frontend at / (API routes take precedence).
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()
