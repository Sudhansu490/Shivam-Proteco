"""RAG tests: chunking, metadata, citations. Offline."""
from __future__ import annotations

from src.rag.ingestion import chunk_markdown, ingest_sops_dir
from src.rag.retriever import FakeRetriever


def test_chunking_splits_and_preserves_sections():
    md = "# Title\n\nSome intro.\n\n## Section A\n" + ("word " * 500) + "\n\n## Section B\nshort"
    chunks = chunk_markdown(md, max_chars=500, overlap=50)
    assert len(chunks) >= 3
    assert all(c["text"] and c["section"] for c in chunks)


def test_ingest_sops_has_metadata():
    chunks = ingest_sops_dir("data/sops")
    assert len(chunks) >= 4, "expected chunks from 2 SOP files"
    for c in chunks:
        assert c.document_id in ("sop_quality_inspection", "sop_nonconformance")
        assert c.source_title
        assert c.section
        assert c.version
        assert c.chunk_id


def test_ingest_idempotent():
    a = ingest_sops_dir("data/sops")
    b = ingest_sops_dir("data/sops")
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_retriever_returns_citations():
    r = FakeRetriever(sops_dir="data/sops")
    hits = r.retrieve("aluminium purity moisture inspection specification", top_k=2)
    assert len(hits) >= 1
    for h in hits:
        assert h.document_id
        assert h.source_title
        assert h.version
        assert h.chunk_id
        assert h.text_excerpt


def test_retriever_empty_on_nonsense():
    r = FakeRetriever(sops_dir="data/sops")
    hits = r.retrieve("zzzqqq xxyyzz_no_match_12345", top_k=3)
    assert hits == []
