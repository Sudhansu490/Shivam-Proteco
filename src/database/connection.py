"""Relational DB helper (SQLite only, file-based, no server needed).

Vectors live in ChromaDB (src/database/vector_store.py), not in SQL.
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

SQLITE_DEFAULT = "sqlite:///data/quality.db"


def get_engine(database_url: str = "") -> Optional[Engine]:
    """Create a SQLite engine. Non-SQLite URLs are rejected (SQLite-only project)."""
    url = (database_url or "").strip() or SQLITE_DEFAULT
    if not url.startswith("sqlite"):
        return None
    try:
        # Ensure parent dir exists (e.g. data/) for file-based SQLite.
        path = url.split("sqlite:///", 1)[-1].split("?", 1)[0]
        if path and path != ":memory:":
            from pathlib import Path
            parent = Path(path).parent
            if str(parent) and str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
        return engine
    except Exception:
        return None


def init_schema(engine: Engine) -> None:
    """Create tables if missing. Never drops data (no destructive reset)."""
    from src.database.models import Base
    Base.metadata.create_all(engine, checkfirst=True)
