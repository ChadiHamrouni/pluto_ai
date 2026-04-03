"""
ChromaDB-backed knowledge base — core service.

Provides ingestion, hybrid search (semantic + BM25 + RRF), and deletion.
Used by: tools/rag.py, tools/notes.py, helpers/cron/ingestion_job.py, routes/search.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb import Collection
from rank_bm25 import BM25Okapi

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.embedder import embed_text
from models.knowledge_base import KnowledgeChunk

logger = get_logger(__name__)

_collection: Optional[Collection] = None

# BM25 index — rebuilt lazily whenever the collection changes
_bm25: Optional[BM25Okapi] = None
_bm25_corpus: list[str] = []
_bm25_ids: list[str] = []

_RRF_K = 60


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping character-bounded chunks on word boundaries."""
    if not text:
        return []

    words = text.split()
    chunks: List[str] = []
    start = 0

    while start < len(words):
        current_words: List[str] = []
        current_chars = 0

        for i in range(start, len(words)):
            word = words[i]
            if (
                current_chars + len(word) + (1 if current_words else 0) > chunk_size
                and current_words
            ):
                break
            current_words.append(word)
            current_chars += len(word) + (1 if len(current_words) > 1 else 0)

        chunk = " ".join(current_words)
        chunks.append(chunk)

        advance_chars = max(chunk_size - overlap, 1)
        consumed = 0
        step = 0
        for w in current_words:
            consumed += len(w) + (1 if step > 0 else 0)
            step += 1
            if consumed >= advance_chars:
                break

        start += max(step, 1)

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# ChromaDB collection
# ---------------------------------------------------------------------------

def get_collection() -> Collection:
    """Return (and lazily initialise) the persistent ChromaDB collection."""
    global _collection
    if _collection is not None:
        return _collection

    cfg = load_config()["knowledge_base"]
    chroma_path = cfg.get("chroma_path", "data/chroma")
    collection_name = cfg.get("collection_name", "knowledge_base")

    os.makedirs(chroma_path, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_path)
    _collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("ChromaDB collection '%s' loaded from %s", collection_name, chroma_path)
    return _collection


# ---------------------------------------------------------------------------
# BM25 index
# ---------------------------------------------------------------------------

def _invalidate_bm25() -> None:
    global _bm25, _bm25_corpus, _bm25_ids
    _bm25 = None
    _bm25_corpus = []
    _bm25_ids = []


def _get_bm25() -> tuple[BM25Okapi, list[str], list[str]]:
    global _bm25, _bm25_corpus, _bm25_ids

    if _bm25 is not None:
        return _bm25, _bm25_corpus, _bm25_ids

    col = get_collection()
    result = col.get(include=["documents", "metadatas"])
    docs: list[str] = result.get("documents") or []
    ids: list[str] = result.get("ids") or []

    if not docs:
        _bm25_corpus = []
        _bm25_ids = []
        _bm25 = BM25Okapi([[""]])
        return _bm25, _bm25_corpus, _bm25_ids

    tokenised = [doc.lower().split() for doc in docs]
    _bm25 = BM25Okapi(tokenised)
    _bm25_corpus = docs
    _bm25_ids = ids
    logger.debug("BM25 index rebuilt over %d chunks", len(docs))
    return _bm25, _bm25_corpus, _bm25_ids


# ---------------------------------------------------------------------------
# RRF merge
# ---------------------------------------------------------------------------

def _rrf_merge(
    semantic_hits: list[KnowledgeChunk],
    bm25_hits: list[KnowledgeChunk],
    top_k: int,
) -> list[KnowledgeChunk]:
    chunks: dict[tuple[str, int], KnowledgeChunk] = {}
    rrf_scores: dict[tuple[str, int], float] = {}

    def _key(c: KnowledgeChunk) -> tuple[str, int]:
        return (c.source, c.chunk_index)

    for rank, chunk in enumerate(semantic_hits, start=1):
        k = _key(chunk)
        chunks[k] = chunk
        rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (_RRF_K + rank)

    for rank, chunk in enumerate(bm25_hits, start=1):
        k = _key(chunk)
        if k not in chunks:
            chunks[k] = chunk
        rrf_scores[k] = rrf_scores.get(k, 0.0) + 1.0 / (_RRF_K + rank)

    merged: list[KnowledgeChunk] = []
    for key, score in rrf_scores.items():
        c = chunks[key]
        merged.append(KnowledgeChunk(
            content=c.content,
            source=c.source,
            chunk_index=c.chunk_index,
            semantic_score=c.semantic_score,
            bm25_score=c.bm25_score,
            rrf_score=round(score, 6),
        ))

    merged.sort(key=lambda x: x.rrf_score, reverse=True)
    return merged[:top_k]


# ---------------------------------------------------------------------------
# Ingested file tracking
# ---------------------------------------------------------------------------

def get_ingested_files() -> set[str]:
    """Return the set of source keys already present in the collection."""
    try:
        col = get_collection()
        result = col.get(include=["metadatas"])
        return {m["source"] for m in result["metadatas"] if m and "source" in m}
    except Exception as exc:
        logger.warning("Could not fetch ingested files: %s", exc)
        return set()


def get_ingested_files_with_timestamps() -> dict[str, float]:
    """Return {source_key: ingested_at mtime} for all unique sources."""
    try:
        col = get_collection()
        result = col.get(include=["metadatas"])
        seen: dict[str, float] = {}
        for m in result["metadatas"]:
            if not m or "source" not in m:
                continue
            src = m["source"]
            ts = float(m.get("ingested_at", 0.0))
            if src not in seen or ts > seen[src]:
                seen[src] = ts
        return seen
    except Exception as exc:
        logger.warning("Could not fetch ingested file timestamps: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def _read_file(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n".join(pages)
        except Exception as exc:
            logger.warning("PDF extraction failed for %s: %s", path.name, exc)
            return ""

    logger.warning("Unsupported file type: %s", suffix)
    return ""


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_file(file_path: str, content_type: str = "file", source_prefix: str = "", source_key: str = "") -> dict:
    """Ingest a document: chunk → embed → upsert into ChromaDB.

    source_key overrides the auto-generated key. Pass it when the caller
    already knows the relative-path key (e.g. ingestion_job uses relative paths
    to avoid filename collisions across subdirectories).
    """
    path = Path(file_path)
    if not source_key:
        source_key = f"{source_prefix}{path.name}"

    text = _read_file(file_path)
    if not text.strip():
        logger.warning("Empty or unreadable file: %s", source_key)
        return {"filename": source_key, "chunks_stored": 0, "total_chars": 0}

    rag_cfg = load_config()["rag"]
    chunks = chunk_text(text, rag_cfg["chunk_size"], rag_cfg["chunk_overlap"])
    if not chunks:
        return {"filename": source_key, "chunks_stored": 0, "total_chars": len(text)}

    logger.info("Ingesting %s (%s) — %d chunks", source_key, content_type, len(chunks))

    col = get_collection()
    try:
        col.delete(where={"source": source_key})
    except Exception:
        pass

    ingested_at = path.stat().st_mtime
    ids = [f"{source_key}::{i}" for i in range(len(chunks))]
    metadatas = [
        {"source": source_key, "chunk_index": i, "content_type": content_type, "ingested_at": ingested_at}
        for i in range(len(chunks))
    ]
    embeddings = [embed_text(chunk) for chunk in chunks]

    col.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    _invalidate_bm25()
    logger.info("Ingested %s: %d chunks stored", source_key, len(chunks))
    return {"filename": source_key, "chunks_stored": len(chunks), "total_chars": len(text)}


# ---------------------------------------------------------------------------
# Search — hybrid semantic + BM25 + RRF
# ---------------------------------------------------------------------------

def list_by_type(content_type: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """Return up to top_k chunks for a given content_type without a search query."""
    col = get_collection()
    if col.count() == 0:
        return []
    try:
        result = col.get(
            where={"content_type": content_type},
            include=["documents", "metadatas"],
        )
        chunks = []
        # Deduplicate by source — one representative chunk per file
        seen_sources: set[str] = set()
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        for doc, meta in zip(docs, metas):
            src = meta.get("source", "unknown")
            if src in seen_sources:
                continue
            seen_sources.add(src)
            chunks.append(KnowledgeChunk(
                content=doc,
                source=src,
                chunk_index=meta.get("chunk_index", 0),
                content_type=meta.get("content_type", content_type),
            ))
            if len(chunks) >= top_k:
                break
        return chunks
    except Exception as exc:
        logger.warning("list_by_type failed: %s", exc)
        return []


def search_by_source(query: str, content_type_filter: Optional[str] = None, top_k: int = 10) -> list[KnowledgeChunk]:
    """Return chunks whose source key contains the query string (case-insensitive filename search)."""
    col = get_collection()
    if col.count() == 0:
        return []
    try:
        get_kwargs: dict = {"include": ["documents", "metadatas"]}
        if content_type_filter:
            get_kwargs["where"] = {"content_type": content_type_filter}
        result = col.get(**get_kwargs)
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []

        q_lower = query.lower()
        seen_sources: set[str] = set()
        chunks = []
        for doc, meta in zip(docs, metas):
            src = meta.get("source", "")
            # Strip obsidian:: prefix for matching
            bare = src.replace("obsidian::", "")
            if q_lower not in bare.lower():
                continue
            if src in seen_sources:
                continue
            seen_sources.add(src)
            chunks.append(KnowledgeChunk(
                content=doc,
                source=src,
                chunk_index=meta.get("chunk_index", 0),
                content_type=meta.get("content_type", content_type_filter or "file"),
            ))
            if len(chunks) >= top_k:
                break
        return chunks
    except Exception as exc:
        logger.warning("search_by_source failed: %s", exc)
        return []


def search_knowledge(
    query: str,
    top_k: int = 5,
    content_type_filter: Optional[str] = None,
) -> list[KnowledgeChunk]:
    """Hybrid search: ChromaDB cosine + BM25, fused via RRF."""
    if not query.strip():
        if content_type_filter:
            return list_by_type(content_type_filter, top_k)
        return []

    col = get_collection()
    if col.count() == 0:
        return []

    full_cfg = load_config()
    kb_cfg = full_cfg.get("knowledge_base", {})
    rag_cfg = full_cfg["rag"]
    threshold: float = kb_cfg.get(
        "search_similarity_threshold", rag_cfg.get("similarity_threshold", 0.3)
    )
    fetch_k = max(top_k * 2, 10)
    where_clause = {"content_type": content_type_filter} if content_type_filter else None

    # 1. Semantic
    semantic_hits: list[KnowledgeChunk] = []
    try:
        query_vec = embed_text(query)
        query_kwargs: dict = {
            "query_embeddings": [query_vec],
            "n_results": min(fetch_k, col.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where_clause:
            query_kwargs["where"] = where_clause

        result = col.query(**query_kwargs)
        docs = result["documents"][0] if result["documents"] else []
        metas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []

        for doc, meta, dist in zip(docs, metas, distances):
            score = round(1.0 - dist, 4)
            if score >= threshold:
                semantic_hits.append(KnowledgeChunk(
                    content=doc,
                    source=meta.get("source", "unknown"),
                    chunk_index=meta.get("chunk_index", 0),
                    semantic_score=score,
                    content_type=meta.get("content_type", "file"),
                ))
    except Exception as exc:
        logger.warning("Semantic search failed: %s", exc)

    # 2. BM25
    bm25_hits: list[KnowledgeChunk] = []
    try:
        bm25_index, corpus, ids = _get_bm25()
        if corpus:
            tokenised_query = query.lower().split()
            scores: list[float] = bm25_index.get_scores(tokenised_query).tolist()
            max_score = max(scores) if scores else 0.0
            if max_score > 0:
                ranked = sorted(
                    [(s / max_score, i) for i, s in enumerate(scores) if s > 0],
                    key=lambda x: x[0],
                    reverse=True,
                )[:fetch_k]

                hit_ids = [ids[i] for _, i in ranked]
                meta_result = col.get(ids=hit_ids, include=["documents", "metadatas"])
                id_to_meta = {doc_id: meta for doc_id, meta in zip(meta_result["ids"], meta_result["metadatas"])}
                id_to_doc = {doc_id: doc for doc_id, doc in zip(meta_result["ids"], meta_result["documents"])}

                for norm_score, idx in ranked:
                    chunk_id = ids[idx]
                    meta = id_to_meta.get(chunk_id, {})
                    if content_type_filter and meta.get("content_type") != content_type_filter:
                        continue
                    bm25_hits.append(KnowledgeChunk(
                        content=id_to_doc.get(chunk_id, corpus[idx]),
                        source=meta.get("source", "unknown"),
                        chunk_index=meta.get("chunk_index", 0),
                        bm25_score=round(norm_score, 4),
                        content_type=meta.get("content_type", "file"),
                    ))
    except Exception as exc:
        logger.warning("BM25 search failed: %s", exc)

    # 3. RRF fusion
    if not semantic_hits and not bm25_hits:
        return []
    if not semantic_hits:
        return bm25_hits[:top_k]
    if not bm25_hits:
        return semantic_hits[:top_k]

    return _rrf_merge(semantic_hits, bm25_hits, top_k)


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def delete_source(filename: str) -> int:
    """Delete all chunks for a given source key. Returns number deleted."""
    col = get_collection()
    existing = col.get(where={"source": filename}, include=["metadatas"])
    count = len(existing["ids"])
    if count:
        col.delete(where={"source": filename})
        _invalidate_bm25()
        logger.info("Deleted %d chunks for source: %s", count, filename)
    return count
