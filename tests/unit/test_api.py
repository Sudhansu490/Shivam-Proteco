"""API contract tests: routes, persistence, review round-trip. Offline.

Uses throwaway SQLite + Chroma dirs via env overrides (get_settings reads
env dynamically, so monkeypatch works). No server, no network.
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("LLM_PROVIDER", "none")
    from src.api.app import create_app
    return TestClient(create_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["demo"] is True


def test_summary_counts(client):
    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 50
    assert body["counts"]["PASS"] + body["counts"]["FAIL"] + body["counts"]["REVIEW"] == 50
    assert len(body["results"]) == 50


def test_get_batch_and_404(client):
    r = client.get("/batches/B002")
    assert r.status_code == 200
    assert r.json()["calculated_status"] == "FAIL"
    assert client.get("/batches/NOPE").status_code == 404


def test_investigate_has_recommendations_and_persists(client):
    r = client.post("/batches/B002/investigate")
    assert r.status_code == 200
    wf = r.json()
    assert wf["validation"]["calculated_status"] == "FAIL"
    assert wf["requires_human_review"] is True
    assert wf["investigation"]["demo_mode"] is True
    assert len(wf["investigation"]["recommendations"]) >= 1
    assert any("human approval" in x for x in wf["investigation"]["recommendations"])
    assert wf["persisted"] is True


def test_review_round_trip(client):
    r = client.post("/batches/B002/review", json={
        "decision": "REVIEW", "comments": "contract test", "reviewer": "tester"})
    assert r.status_code == 200
    body = r.json()
    assert body["persisted"] is True
    assert body["decision"] == "REVIEW"
    assert client.post("/batches/NOPE/review", json={"decision": "FAIL"}).status_code == 404


def test_history(client):
    r = client.get("/batches/B001/history")
    assert r.status_code == 200
    body = r.json()
    assert body["validation"]["calculated_status"] == "PASS"
    assert body["workflow"]["requires_human_review"] is True


def test_ingest_idempotent(client):
    first = client.post("/documents/ingest").json()
    second = client.post("/documents/ingest").json()
    assert first["chunks"] == second["chunks"] >= 4
    assert set(first["documents"]) == {"sop_quality_inspection", "sop_nonconformance"}
