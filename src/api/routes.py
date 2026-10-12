"""REST endpoints with Pydantic schemas and safe path handling."""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException
from src.config.settings import get_settings
from src.services.quality_service import QualityService
from src.models.schemas import ReviewRequest
from src.rag.ingestion import ingest_sops_dir, chunks_to_dicts
from src.database.connection import get_engine, init_schema
from src.database.repositories import DocumentRepository, ReviewRepository

router = APIRouter()


def _service() -> QualityService:
    return QualityService(get_settings())


def _safe_sops_subpath(name: str) -> str:
    # Validate upload paths: only allow simple filenames, no traversal.
    p = Path(name).name
    if not p.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md filenames allowed")
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid document path")
    return p


@router.get("/health")
def health():
    s = get_settings()
    return {"status": "ok", "llm_provider": s.llm_provider, "has_database": s.has_database,
            "demo": True, "disclaimer": "Synthetic demo data only."}


@router.get("/batches")
def list_batches():
    svc = _service()
    try:
        return {"batches": svc.list_batches(), "disclaimer": "Synthetic demo data."}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/summary")
def validation_summary():
    """Aggregate validation over the whole CSV (powers the web frontend cards)."""
    svc = _service()
    try:
        s = svc.summary()
        return {
            "total": s["total"],
            "counts": s["counts"],
            "discrepancies": s["discrepancies"],
            "results": [r.model_dump() for r in s["results"]],
            "disclaimer": "Synthetic demo data.",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    svc = _service()
    try:
        v = svc.validate_one(batch_id)
        return v.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")


@router.post("/batches/{batch_id}/validate")
def validate_batch(batch_id: str):
    return get_batch(batch_id)


@router.post("/batches/{batch_id}/investigate")
def investigate_batch(batch_id: str):
    svc = _service()
    try:
        wf = svc.investigate(batch_id)
        return wf.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")


@router.get("/batches/{batch_id}/history")
def batch_history(batch_id: str):
    svc = _service()
    try:
        h = svc.history(batch_id)
        return {"batch_id": batch_id,
                "validation": h["validation"].model_dump(),
                "workflow": h["workflow"].model_dump()}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")


@router.post("/batches/{batch_id}/review")
def review_batch(batch_id: str, req: ReviewRequest):
    s = get_settings()
    engine = get_engine(s.database_url) if s.has_database else None
    if engine is not None:
        init_schema(engine)  # ensure tables exist on fresh SQLite files
    repo = ReviewRepository(engine)
    # validate batch exists first
    svc = _service()
    try:
        svc.validate_one(batch_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    saved = repo.save_review(batch_id, req.decision, req.comments, req.reviewer)
    return saved


@router.post("/documents/ingest")
def ingest_documents():
    s = get_settings()
    chunks = ingest_sops_dir(s.sops_dir)
    payload = chunks_to_dicts(chunks)
    persisted = 0
    try:
        engine = get_engine(s.database_url) if s.has_database else None
        if engine is not None:
            init_schema(engine)
        persisted = DocumentRepository(engine, chroma_dir=s.chroma_dir).upsert_chunks(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chroma ingest failed: {e}")
    # Validate a sample filename to demonstrate safe-path handling (no-op)
    _safe_sops_subpath("sop_quality_inspection.md")
    return {"chunks": len(chunks), "persisted": persisted,
            "documents": sorted({c["document_id"] for c in payload}),
            "note": "Fictional SOPs only. Idempotent ChromaDB ingest."}
