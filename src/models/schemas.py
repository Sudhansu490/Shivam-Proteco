"""Pydantic schemas for validation, workflow, API and review."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

Status = Literal["PASS", "FAIL", "REVIEW"]


class FailedCheck(BaseModel):
    check: str
    measured: Optional[float] = None
    limit: Optional[float] = None
    message: str


class BatchValidationResult(BaseModel):
    batch_id: str
    product_type: str
    calculated_status: Status
    recorded_status: Optional[str] = None
    discrepancy: bool = False
    failed_checks: List[FailedCheck] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    limits_used: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class EvidenceCitation(BaseModel):
    source_title: str
    section: str = ""
    document_id: str = ""
    version: str = ""
    chunk_id: str = ""
    score: float = 0.0
    text_excerpt: str = ""


class InvestigationResult(BaseModel):
    batch_id: str
    facts: List[str] = Field(default_factory=list)
    hypotheses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    evidence: List[EvidenceCitation] = Field(default_factory=list)
    summary: str = ""
    demo_mode: bool = True
    llm_model: str = ""


class VerificationResult(BaseModel):
    batch_id: str
    supported: bool
    reasons: List[str] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    batch_id: str
    validation: BatchValidationResult
    investigation: Optional[InvestigationResult] = None
    verification: Optional[VerificationResult] = None
    iterations: int = 0
    final_disposition: Status = "REVIEW"
    requires_human_review: bool = True
    persisted: bool = False
    notes: List[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    decision: Status
    comments: str = ""
    reviewer: str = "human_reviewer"


class ReviewRecord(BaseModel):
    batch_id: str
    decision: Status
    comments: str = ""
    reviewer: str = ""
