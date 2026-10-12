"""Integration placeholder: API + DB tests (skipped without server/DB)."""
from __future__ import annotations

import pytest


def test_api_health_placeholder():
    pytest.skip("Requires running FastAPI server; run manually: python main.py api")


def test_sqlite_placeholder():
    pytest.skip("Requires SQLite DB + ChromaDB ingest; run: python main.py ingest, then python main.py api")
