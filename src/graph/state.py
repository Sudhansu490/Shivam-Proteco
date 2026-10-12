"""Typed workflow state."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from src.models.schemas import BatchValidationResult, InvestigationResult, VerificationResult


class QualityState(BaseModel):
    batch_id: str
    row: dict = Field(default_factory=dict)
    validation: Optional[BatchValidationResult] = None
    investigation: Optional[InvestigationResult] = None
    verification: Optional[VerificationResult] = None
    iterations: int = 0
    max_retries: int = 3
    final_disposition: str = "REVIEW"
    requires_human_review: bool = True
    notes: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
