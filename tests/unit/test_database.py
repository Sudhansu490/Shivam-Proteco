"""SQLite relational store tests: offline, temp dir."""
from __future__ import annotations

from src.database.connection import get_engine, init_schema, SQLITE_DEFAULT
from src.database.repositories import ReviewRepository
from src.config.settings import get_settings


def test_sqlite_default_url():
    assert SQLITE_DEFAULT.startswith("sqlite")
    s = get_settings()
    # SQLite-only project: the configured URL must always be SQLite.
    assert s.database_url.startswith("sqlite")


def test_non_sqlite_url_rejected():
    assert get_engine("postgresql+psycopg://u:p@localhost/db") is None


def test_sqlite_engine_init_and_review(tmp_path):
    url = f"sqlite:///{tmp_path}/quality.db"
    engine = get_engine(url)
    assert engine is not None
    init_schema(engine)
    # idempotent re-init must not fail or wipe
    init_schema(engine)
    repo = ReviewRepository(engine)
    saved = repo.save_review("B001", "PASS", "ok", "tester")
    assert saved["persisted"] is True
    assert saved["batch_id"] == "B001"
