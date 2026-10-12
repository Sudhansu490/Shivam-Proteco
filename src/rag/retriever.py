"""Retrievers: offline FakeRetriever (default) + file-based keyword retriever.

Never invent citations. If nothing matches, return empty list and let
callers state that no evidence was found.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.models.schemas import EvidenceCitation
from src.rag.ingestion import ingest_sops_dir


def _score(query: str, text: str) -> float:
    q = [w for w in query.lower().split() if len(w) > 2]
    t = text.lower()
    if not q:
        return 0.0
    hits = sum(1 for w in q if w in t)
    return hits / len(q)


@dataclass
class FakeRetriever:
    """Deterministic keyword retriever over local SOP markdown chunks. No network, no DB."""

    sops_dir: str = "data/sops"

    def _load(self):  # lazy to keep import light
        return ingest_sops_dir(self.sops_dir)

    def retrieve(self, query: str, top_k: int = 3) -> List[EvidenceCitation]:
        chunks = self._load()
        scored = []
        for c in chunks:
            s = _score(query, f"{c.section} {c.text} {c.document_id}")
            # small boost for relevant doc
            if "nonconformance" in query.lower() and "nonconformance" in c.document_id:
                s += 0.1
            if "inspection" in query.lower() and "inspection" in c.document_id:
                s += 0.1
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[EvidenceCitation] = []
        for score, c in scored[:top_k]:
            if score <= 0:
                continue
            out.append(EvidenceCitation(
                source_title=c.source_title,
                section=c.section,
                document_id=c.document_id,
                version=c.version,
                chunk_id=c.chunk_id,
                score=round(float(score), 3),
                text_excerpt=c.text[:500],
            ))
        return out


class Retriever:
    """Facade: tries ChromaDB vector store first, else FakeRetriever keyword search."""

    def __init__(self, sops_dir: str = "data/sops", chroma_dir: str = "data/chroma") -> None:
        self.sops_dir = sops_dir
        self.chroma_dir = chroma_dir
        self._fake = FakeRetriever(sops_dir=sops_dir)

    def retrieve(self, query: str, top_k: int = 3) -> List[EvidenceCitation]:
        # ChromaDB path first (local persistent store, no server needed).
        try:
            from src.database.vector_store import ChromaStore
            store = ChromaStore(persist_dir=self.chroma_dir)
            if store.available and store.count() > 0:
                rows = store.query(query, top_k=top_k)
                if rows:
                    return [
                        EvidenceCitation(
                            source_title=r.get("source_title", ""),
                            section=r.get("section", ""),
                            document_id=r.get("document_id", ""),
                            version=r.get("version", ""),
                            chunk_id=r.get("chunk_id", ""),
                            score=float(r.get("score", 0.0)),
                            text_excerpt=r.get("text", "")[:500],
                        )
                        for r in rows
                    ]
        except Exception:
            pass
        return self._fake.retrieve(query, top_k=top_k)
