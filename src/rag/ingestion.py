"""SOP ingestion: markdown -> chunks with metadata. Idempotent file-based store + optional SQLite."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    source_title: str
    section: str
    version: str
    text: str
    token_count: int = 0


def _doc_id_for(path: Path) -> str:
    return path.stem  # e.g. sop_quality_inspection


def _title_for(path: Path, first_heading: str = "") -> str:
    return first_heading or path.stem.replace("_", " ").title()


def chunk_markdown(text: str, max_chars: int = 1200, overlap: int = 150) -> List[Dict[str, str]]:
    """Split markdown by headings, then by size. Returns [{section, text}]."""
    sections: List[Dict[str, str]] = []
    current_section = "Introduction"
    current_buf: List[str] = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)", line.strip())
        if m:
            if current_buf:
                sections.append({"section": current_section, "text": "\n".join(current_buf).strip()})
                current_buf = []
            current_section = m.group(1).strip()
        current_buf.append(line)
    if current_buf:
        sections.append({"section": current_section, "text": "\n".join(current_buf).strip()})

    chunks: List[Dict[str, str]] = []
    overlap = max(0, min(overlap, max_chars - 1))
    for s in sections:
        body = s["text"]
        if len(body) <= max_chars:
            if body.strip():
                chunks.append(s)
        else:
            start = 0
            while start < len(body):
                piece = body[start:start + max_chars]
                # avoid cutting mid-line
                if len(piece) == max_chars:
                    nl = piece.rfind("\n")
                    if nl > max_chars * 0.5:
                        piece = piece[:nl]
                if piece.strip():
                    chunks.append({"section": s["section"], "text": piece.strip()})
                if len(piece) < max_chars:
                    break  # last chunk; avoid stall when remainder <= overlap
                step = max(len(piece) - overlap, 1)
                start += step
                if start <= 0:
                    break
    return [c for c in chunks if c["text"]]


def ingest_sop_file(path: Path) -> List[DocumentChunk]:
    text = path.read_text(encoding="utf-8")
    heading = ""
    for line in text.splitlines():
        m = re.match(r"^#\s+(.*)", line.strip())
        if m:
            heading = m.group(1).strip()
            break
    # version: look for Version: x.y
    version = "1.0"
    vm = re.search(r"[Vv]ersion:\s*([\d.]+)", text)
    if vm:
        version = vm.group(1)
    document_id = _doc_id_for(path)
    title = _title_for(path, heading)
    out: List[DocumentChunk] = []
    for c in chunk_markdown(text):
        raw = f"{document_id}::{c['section']}::{c['text'][:200]}"
        cid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        out.append(DocumentChunk(
            chunk_id=cid,
            document_id=document_id,
            source_title=title,
            section=c["section"],
            version=version,
            text=c["text"],
            token_count=len(c["text"].split()),
        ))
    return out


def ingest_sops_dir(sops_dir: str | Path) -> List[DocumentChunk]:
    p = Path(sops_dir)
    chunks: List[DocumentChunk] = []
    if not p.exists():
        return chunks
    for md in sorted(p.glob("*.md")):
        chunks.extend(ingest_sop_file(md))
    return chunks


def chunks_to_dicts(chunks: List[DocumentChunk]) -> List[Dict[str, Any]]:
    return [asdict(c) for c in chunks]
