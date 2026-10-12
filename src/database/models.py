"""SQLAlchemy 2.x models for batches, results, runs, reviews.

Document chunk *metadata* may also be mirrored here; dense vectors
live in ChromaDB (see src/database/vector_store.py), not in SQL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BatchRecord(Base):
    __tablename__ = "batches"
    batch_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    product_type: Mapped[str] = mapped_column(String(100))
    purity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moisture_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    particle_size_um: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    defect_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inspection_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


class ValidationResultRecord(Base):
    __tablename__ = "validation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    calculated_status: Mapped[str] = mapped_column(String(20))
    recorded_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    discrepancy: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_checks: Mapped[dict] = mapped_column(JSON, default=list)
    missing_fields: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunkRecord(Base):
    __tablename__ = "document_chunks"
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(200))
    source_title: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    # Vectors are stored in ChromaDB, not here. No pgvector column.


class InvestigationRunRecord(Base):
    __tablename__ = "investigation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    facts: Mapped[dict] = mapped_column(JSON, default=list)
    hypotheses: Mapped[dict] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=list)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VerificationResultRecord(Base):
    __tablename__ = "verification_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    supported: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HumanReviewRecord(Base):
    __tablename__ = "human_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    decision: Mapped[str] = mapped_column(String(20))
    comments: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(200), default="human_reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
