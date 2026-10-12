"""High-level quality service: CSV + validator + workflow, DB optional."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from src.config.settings import Settings
from src.quality.validator import QualityValidator
from src.graph.workflow import run_workflow
from src.models.schemas import BatchValidationResult, WorkflowResult


class QualityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.validator = QualityValidator(settings.limits_path)

    def _resolve_csv(self, csv_path: str = "") -> Path:
        p = Path(csv_path or self.settings.csv_path)
        if not p.is_absolute():
            # try cwd-relative then repo-root-relative
            if p.exists():
                return p
            alt = Path(__file__).resolve().parents[3] / p
            if alt.exists():
                return alt
        return p

    def list_batches(self, csv_path: str = "") -> List[Dict[str, Any]]:
        p = self._resolve_csv(csv_path)
        df = self.validator.load_batches(p)
        return df.to_dict(orient="records")

    def validate_all(self, csv_path: str = "") -> List[BatchValidationResult]:
        p = self._resolve_csv(csv_path)
        return self.validator.validate_csv(p)

    def validate_one(self, batch_id: str, csv_path: str = "") -> BatchValidationResult:
        for r in self.validate_all(csv_path):
            if r.batch_id == batch_id:
                return r
        raise KeyError(f"Batch {batch_id} not found")

    def investigate(self, batch_id: str, csv_path: str = "") -> WorkflowResult:
        p = self._resolve_csv(csv_path)
        df = self.validator.load_batches(p)
        match = df[df["batch_id"] == batch_id]
        if match.empty:
            raise KeyError(f"Batch {batch_id} not found")
        row = match.iloc[0].to_dict()
        s = self.settings
        wf = run_workflow(
            row,
            limits_path=s.limits_path,
            sops_dir=s.sops_dir,
            max_retries=s.max_workflow_retries,
            chroma_dir=s.chroma_dir,
            provider=s.llm_provider if s.has_llm else "none",
            groq_api_key=s.groq_api_key,
            groq_model=s.groq_model,
        )
        # Persist the run (best-effort; offline/file mode still returns the workflow).
        try:
            from src.database.connection import get_engine, init_schema
            from src.database.repositories import RunRepository
            engine = get_engine(s.database_url)
            if engine is not None:
                init_schema(engine)
                wf.persisted = bool(RunRepository(engine).save_workflow(wf))
        except Exception:
            wf.persisted = False
        return wf

    def summary(self, csv_path: str = "") -> Dict[str, Any]:
        results = self.validate_all(csv_path)
        counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
        discrepancies = 0
        for r in results:
            counts[r.calculated_status] = counts.get(r.calculated_status, 0) + 1
            if r.discrepancy:
                discrepancies += 1
        return {"total": len(results), "counts": counts, "discrepancies": discrepancies, "results": results}

    def history(self, batch_id: str) -> Dict[str, Any]:
        # Re-runs validation + workflow on the current CSV (run records for
        # prior investigations are also queryable from SQLite when persisted).
        validation = self.validate_one(batch_id)
        workflow = self.investigate(batch_id)
        return {"batch_id": batch_id, "validation": validation, "workflow": workflow}
