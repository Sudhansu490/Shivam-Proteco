"""ChromaDB vector store tests: offline, temp dir, no server."""
from __future__ import annotations

import pytest

chromadb = pytest.importorskip("chromadb")

from src.database.vector_store import ChromaStore, hash_embedding
from src.rag.ingestion import ingest_sops_dir, chunks_to_dicts


def test_hash_embedding_deterministic():
    a = hash_embedding("purity moisture inspection", 64)
    b = hash_embedding("purity moisture inspection", 64)
    assert a == b
    assert len(a) == 64


def test_chroma_upsert_and_query(tmp_path):
    chunks = chunks_to_dicts(ingest_sops_dir("data/sops"))
    assert len(chunks) >= 4
    store = ChromaStore(persist_dir=str(tmp_path / "chroma"))
    n = store.upsert_chunks(chunks)
    assert n == len(chunks)
    assert store.count() == len(chunks)
    # idempotent re-upsert keeps same count
    store.upsert_chunks(chunks)
    assert store.count() == len(chunks)
    hits = store.query("aluminium purity moisture inspection specification", top_k=2)
    assert len(hits) >= 1
    for h in hits:
        assert h["chunk_id"] and h["document_id"] and h["text"]


def test_chroma_empty_query_returns_empty(tmp_path):
    store = ChromaStore(persist_dir=str(tmp_path / "chroma_empty"))
    assert store.query("anything", top_k=3) == []
