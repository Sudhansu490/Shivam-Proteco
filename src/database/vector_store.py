"""ChromaDB vector store for SOP chunks (replaces pgvector).

- Persistent local store, no server required.
- Deterministic hash embeddings by default so tests run offline
  (no model download). Swap in sentence-transformers for production.
- Idempotent upsert by chunk_id. Never invents citations:
  empty query results return [].
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Dict, List

_WORD_RE = re.compile(r"[a-z0-9]+")


def hash_embedding(text: str, dim: int = 64) -> List[float]:
    vec = [0.0] * dim
    for w in _WORD_RE.findall(text.lower()):
        h = int(hashlib.sha256(w.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class HashEmbeddingFunction:
    """Chroma-compatible embedding function (hash-based, offline deterministic)."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "hash-embedding"

    def is_legacy(self) -> bool:
        return False

    def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002 (chroma API)
        return [hash_embedding(t, self.dim) for t in input]

    def embed_documents(self, ids: List[str], documents: List[str]) -> List[List[float]]:  # type: ignore[no-untyped-def]
        return [hash_embedding(d, self.dim) for d in documents]

    def embed_query(self, input: List[str]) -> List[List[float]]:  # noqa: A002 (chroma API)
        return [hash_embedding(t, self.dim) for t in input]

    def get_config(self) -> Dict[str, Any]:
        return {"dim": self.dim}

    @classmethod
    def build_from_config(cls, config: Dict[str, Any]) -> "HashEmbeddingFunction":
        return cls(dim=int(config.get("dim", 64)))

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> List[str]:
        return ["cosine", "l2", "ip"]


class ChromaStore:
    """Thin wrapper over a persistent ChromaDB collection."""

    COLLECTION = "sop_chunks"

    def __init__(self, persist_dir: str = "data/chroma", dim: int = 64) -> None:
        self.persist_dir = persist_dir
        self.dim = dim
        self._client = None
        self._collection = None

    def _ensure(self):
        if self._collection is not None:
            return self._collection
        import chromadb  # ImportError if not installed -> caller falls back
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION,
            embedding_function=HashEmbeddingFunction(dim=self.dim),
        )
        return self._collection

    @property
    def available(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:
            return False

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Idempotent upsert. Returns number of chunks passed (Chroma upserts)."""
        if not chunks:
            return 0
        col = self._ensure()
        ids = [c["chunk_id"] for c in chunks]
        docs = [c.get("text", "") for c in chunks]
        metas = [
            {
                "document_id": c.get("document_id", ""),
                "source_title": c.get("source_title", ""),
                "section": c.get("section", ""),
                "version": c.get("version", ""),
            }
            for c in chunks
        ]
        embs = [hash_embedding(d, self.dim) for d in docs]
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        return len(ids)

    def count(self) -> int:
        col = self._ensure()
        return col.count()

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        col = self._ensure()
        if col.count() == 0:
            return []
        res = col.query(
            query_texts=[query_text],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        out: List[Dict[str, Any]] = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for i, doc in enumerate(docs):
            dist = float(dists[i]) if i < len(dists) else 1.0
            score = round(max(0.0, 1.0 - dist), 3)
            meta = metas[i] if i < len(metas) else {}
            out.append(
                {
                    "chunk_id": ids[i] if i < len(ids) else "",
                    "document_id": meta.get("document_id", ""),
                    "source_title": meta.get("source_title", ""),
                    "section": meta.get("section", ""),
                    "version": meta.get("version", ""),
                    "text": doc or "",
                    "score": score,
                }
            )
        # Drop zero-overlap results to stay honest (hash cosine can be 0)
        query_words = set(_WORD_RE.findall(query_text.lower()))
        filtered = []
        for r in out:
            doc_words = set(_WORD_RE.findall((r["text"] + " " + r["section"]).lower()))
            if query_words & doc_words:
                filtered.append(r)
        return filtered
