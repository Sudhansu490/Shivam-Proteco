"""Repository classes. Safe no-op when engine is None (offline mode)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.engine import Engine
from sqlalchemy import select


class BatchRepository:
    def __init__(self, engine: Optional[Engine]) -> None:
        self.engine = engine

    def list_batches(self) -> List[Dict[str, Any]]:
        if self.engine is None:
            return []
        from src.database.models import BatchRecord
        from sqlalchemy.orm import Session
        with Session(self.engine) as s:
            rows = s.scalars(select(BatchRecord)).all()
            return [
                {
                    "batch_id": r.batch_id, "product_type": r.product_type,
                    "purity_pct": r.purity_pct, "moisture_pct": r.moisture_pct,
                    "particle_size_um": r.particle_size_um, "defect_count": r.defect_count,
                    "inspection_status": r.inspection_status,
                }
                for r in rows
            ]


class DocumentRepository:
    """SOP chunk metadata in SQL + vectors in ChromaDB.

    - upsert_chunks writes metadata to SQL (when engine given) and
      always tries ChromaDB (local persistent dir).
    - search tries ChromaDB first, falls back to SQL keyword search.
    """

    def __init__(self, engine: Optional[Engine], chroma_dir: str = "data/chroma") -> None:
        self.engine = engine
        self.chroma_dir = chroma_dir

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Idempotent upsert by chunk_id. Returns count written to ChromaDB."""
        written_sql = 0
        if self.engine is not None:
            from src.database.models import DocumentChunkRecord
            from sqlalchemy.orm import Session
            with Session(self.engine) as s:
                for c in chunks:
                    existing = s.get(DocumentChunkRecord, c["chunk_id"])
                    if existing is None:
                        s.add(DocumentChunkRecord(**{k: c.get(k) for k in
                            ("chunk_id", "document_id", "source_title", "section", "version", "text")}))
                        written_sql += 1
                s.commit()
        try:
            from src.database.vector_store import ChromaStore
            n = ChromaStore(persist_dir=self.chroma_dir).upsert_chunks(chunks)
            return n or written_sql
        except Exception:
            return written_sql

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """ChromaDB vector search first; SQL keyword fallback."""
        try:
            from src.database.vector_store import ChromaStore
            rows = ChromaStore(persist_dir=self.chroma_dir).query(query, top_k=top_k)
            if rows:
                return rows
        except Exception:
            pass
        if self.engine is None:
            return []
        with Session(self.engine) as s:
            rows = s.scalars(select(DocumentChunkRecord).limit(200)).all()
            scored = []
            q = [w for w in query.lower().split() if len(w) > 2]
            for r in rows:
                blob = f"{r.section} {r.text} {r.document_id}".lower()
                score = sum(1 for w in q if w in blob) / max(len(q), 1)
                if score > 0:
                    scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [
                {"chunk_id": r.chunk_id, "document_id": r.document_id,
                 "source_title": r.source_title, "section": r.section,
                 "version": r.version, "text": r.text, "score": sc}
                for sc, r in scored[:top_k]
            ]


class ReviewRepository:
    def __init__(self, engine: Optional[Engine]) -> None:
        self.engine = engine

    def save_review(self, batch_id: str, decision: str, comments: str, reviewer: str) -> Dict[str, Any]:
        if self.engine is None:
            return {"batch_id": batch_id, "decision": decision, "comments": comments,
                    "reviewer": reviewer, "persisted": False}
        from src.database.models import HumanReviewRecord
        from sqlalchemy.orm import Session
        with Session(self.engine) as s:
            rec = HumanReviewRecord(batch_id=batch_id, decision=decision, comments=comments, reviewer=reviewer)
            s.add(rec)
            s.commit()
            return {"batch_id": batch_id, "decision": decision, "comments": comments,
                    "reviewer": reviewer, "persisted": True}


class RunRepository:
    """Persists full workflow runs (validation + investigation + verification)."""

    def __init__(self, engine: Optional[Engine]) -> None:
        self.engine = engine

    def save_workflow(self, workflow) -> bool:
        """Write validation/investigation/verification rows. Returns True on success."""
        if self.engine is None:
            return False
        from src.database.models import (
            ValidationResultRecord, InvestigationRunRecord, VerificationResultRecord,
        )
        from sqlalchemy.orm import Session
        v = workflow.validation
        with Session(self.engine) as s:
            s.add(ValidationResultRecord(
                batch_id=v.batch_id,
                calculated_status=v.calculated_status,
                recorded_status=v.recorded_status,
                discrepancy=bool(v.discrepancy),
                failed_checks=[f.model_dump() for f in v.failed_checks],
                missing_fields=list(v.missing_fields),
            ))
            if workflow.investigation is not None:
                inv = workflow.investigation
                s.add(InvestigationRunRecord(
                    batch_id=inv.batch_id,
                    facts=list(inv.facts),
                    hypotheses=list(inv.hypotheses),
                    evidence=[e.model_dump() for e in inv.evidence],
                    iterations=int(workflow.iterations),
                ))
            if workflow.verification is not None:
                ver = workflow.verification
                s.add(VerificationResultRecord(
                    batch_id=ver.batch_id,
                    supported=bool(ver.supported),
                    reasons=list(ver.reasons),
                ))
            s.commit()
        return True
