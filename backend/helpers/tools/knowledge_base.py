"""
ChromaDB-backed knowledge base for local RAG.

Ingests text/markdown/PDF files into a persistent vector store,
then retrieves relevant chunks via **hybrid search**: semantic similarity
(ChromaDB cosine) + lexical BM25, fused with Reciprocal Rank Fusion (RRF).

Embeddings are generated via Ollama (qwen3-embedding:0.6b) using the
existing helpers/tools/embedder.py helper — no new model dependencies.
BM25 runs entirely in-process via rank-bm25, no extra server needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb import Collection
from rank_bm25 import BM25Okapi

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.embedder import embed_text
from models.knowledge_base import KnowledgeChunk
from tools.rag import chunk_text

logger = get_logger(__name__)

_collection: Optional[Collection] = None

# BM25 index — rebuilt lazily whenever the collection changes
_bm25: Optional[BM25Okapi] = None
_bm25_corpus: list[str] = []   # parallel to ChromaDB doc order
_bm25_ids: list[str] = []      # chunk ids parallel to corpus

# RRF constant — standard value, balances precision vs recall
_RRF_K = 60


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    return load_config()["knowledge_base"]


def get_collection() -> Collection:
    """Return (and lazily initialise) the persistent ChromaDB collection."""
    global _collection
    if _collection is not None:
        return _collection

    cfg = _get_config()
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


def _invalidate_bm25() -> None:
    """Mark the BM25 index as stale so it is rebuilt on next search."""
    global _bm25, _bm25_corpus, _bm25_ids
    _bm25 = None
    _bm25_corpus = []
    _bm25_ids = []


def _get_bm25() -> tuple[BM25Okapi, list[str], list[str]]:
    """
    Return a (bm25_index, corpus, ids) triple, rebuilding from ChromaDB if stale.

    The corpus is ordered identically to ChromaDB's internal document list so
    ranks can be correlated back to chunk ids.
    """
    global _bm25, _bm25_corpus, _bm25_ids

    if _bm25 is not None:
        return _bm25, _bm25_corpus, _bm25_ids

    col = get_collection()
    result = col.get(include=["documents", "metadatas"])
    docs: list[str] = result.get("documents") or []
    ids: list[str] = result.get("ids") or []

    if not docs:
        # Empty collection — return a dummy index
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


def _rrf_merge(
    semantic_hits: list[KnowledgeChunk],
    bm25_hits: list[KnowledgeChunk],
    top_k: int,
) -> list[KnowledgeChunk]:
    """
    Merge two ranked lists with Reciprocal Rank Fusion.

    RRF score for each chunk:  Σ  1 / (k + rank_i)
    where the sum is over all lists in which the chunk appears.
    Chunks not present in a list are simply not given a contribution from it.
    """
    # Build lookup by (source, chunk_index) → KnowledgeChunk
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

    # Attach rrf_score and sort
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
# File helpers
# ---------------------------------------------------------------------------

def get_ingested_files() -> set[str]:
    """Return the set of source filenames already present in the collection."""
    try:
        col = get_collection()
        result = col.get(include=["metadatas"])
        sources = {m["source"] for m in result["metadatas"] if m and "source" in m}
        return sources
    except Exception as exc:
        logger.warning("Could not fetch ingested files: %s", exc)
        return set()


def _read_file(file_path: str) -> str:
    """Read plain text from .txt, .md, or .pdf files."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        try:
            import fitz  # PyMuPDF

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

def ingest_file(file_path: str) -> dict:
    """
    Ingest a document into the knowledge base.

    Reads the file, chunks it, embeds all chunks via Ollama, and upserts
    them into ChromaDB. Invalidates the BM25 index so it is rebuilt on the
    next search.

    Returns:
        {"filename": str, "chunks_stored": int, "total_chars": int}
    """
    path = Path(file_path)
    filename = path.name

    text = _read_file(file_path)
    if not text.strip():
        logger.warning("Empty or unreadable file: %s", filename)
        return {"filename": filename, "chunks_stored": 0, "total_chars": 0}

    rag_cfg = load_config()["rag"]
    chunks = chunk_text(text, rag_cfg["chunk_size"], rag_cfg["chunk_overlap"])
    if not chunks:
        return {"filename": filename, "chunks_stored": 0, "total_chars": len(text)}

    logger.info("Ingesting %s — %d chunks", filename, len(chunks))

    col = get_collection()

    # Remove stale chunks for this file
    try:
        col.delete(where={"source": filename})
    except Exception:
        pass

    ids = [f"{filename}::{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

    # Batch embed — one VRAM swap for the whole file
    embeddings = [embed_text(chunk) for chunk in chunks]

    col.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    _invalidate_bm25()
    logger.info("Ingested %s: %d chunks stored", filename, len(chunks))
    return {"filename": filename, "chunks_stored": len(chunks), "total_chars": len(text)}


# ---------------------------------------------------------------------------
# Search — hybrid (semantic + BM25 + RRF)
# ---------------------------------------------------------------------------

def search_knowledge(query: str, top_k: int = 5) -> list[KnowledgeChunk]:
    """
    Hybrid search: semantic similarity (ChromaDB) + BM25 lexical, fused via RRF.

    Steps:
      1. Semantic: embed query → ChromaDB cosine search → top_k * 2 candidates
      2. Lexical: tokenise query → BM25Okapi.get_top_n → top_k * 2 candidates
      3. RRF: merge both ranked lists → return top_k final results

    Returns a list of KnowledgeChunk with semantic_score, bm25_score, and rrf_score.
    """
    col = get_collection()
    if col.count() == 0:
        return []

    cfg = load_config()["rag"]
    threshold: float = cfg.get("similarity_threshold", 0.3)
    # Fetch more candidates per path so RRF has room to work
    fetch_k = max(top_k * 2, 10)

    # ------------------------------------------------------------------
    # 1. Semantic path
    # ------------------------------------------------------------------
    semantic_hits: list[KnowledgeChunk] = []
    try:
        query_vec = embed_text(query)
        result = col.query(
            query_embeddings=[query_vec],
            n_results=min(fetch_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs = result["documents"][0] if result["documents"] else []
        metas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []

        for doc, meta, dist in zip(docs, metas, distances):
            score = round(1.0 - dist, 4)  # cosine similarity
            if score >= threshold:
                semantic_hits.append(KnowledgeChunk(
                    content=doc,
                    source=meta.get("source", "unknown"),
                    chunk_index=meta.get("chunk_index", 0),
                    semantic_score=score,
                ))
    except Exception as exc:
        logger.warning("Semantic search failed: %s", exc)

    # ------------------------------------------------------------------
    # 2. BM25 lexical path
    # ------------------------------------------------------------------
    bm25_hits: list[KnowledgeChunk] = []
    try:
        bm25_index, corpus, ids = _get_bm25()
        if corpus:
            tokenised_query = query.lower().split()
            scores: list[float] = bm25_index.get_scores(tokenised_query).tolist()

            # Normalise scores to [0, 1]
            max_score = max(scores) if scores else 0.0
            if max_score > 0:
                # Pair (score, idx), filter zero scores, sort descending
                ranked = sorted(
                    [(s / max_score, i) for i, s in enumerate(scores) if s > 0],
                    key=lambda x: x[0],
                    reverse=True,
                )[:fetch_k]

                # Fetch metadata for each top BM25 chunk from ChromaDB
                hit_ids = [ids[i] for _, i in ranked]
                meta_result = col.get(ids=hit_ids, include=["documents", "metadatas"])
                id_to_meta: dict[str, dict] = {}
                id_to_doc: dict[str, str] = {}
                for doc_id, doc, meta in zip(
                    meta_result["ids"],
                    meta_result["documents"],
                    meta_result["metadatas"],
                ):
                    id_to_meta[doc_id] = meta
                    id_to_doc[doc_id] = doc

                for norm_score, idx in ranked:
                    chunk_id = ids[idx]
                    meta = id_to_meta.get(chunk_id, {})
                    doc = id_to_doc.get(chunk_id, corpus[idx])
                    bm25_hits.append(KnowledgeChunk(
                        content=doc,
                        source=meta.get("source", "unknown"),
                        chunk_index=meta.get("chunk_index", 0),
                        bm25_score=round(norm_score, 4),
                    ))
    except Exception as exc:
        logger.warning("BM25 search failed: %s", exc)

    # ------------------------------------------------------------------
    # 3. RRF fusion
    # ------------------------------------------------------------------
    if not semantic_hits and not bm25_hits:
        return []

    # If one path failed completely, fall back to the other
    if not semantic_hits:
        return bm25_hits[:top_k]
    if not bm25_hits:
        return semantic_hits[:top_k]

    return _rrf_merge(semantic_hits, bm25_hits, top_k)


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def delete_source(filename: str) -> int:
    """Delete all chunks for a given source filename. Returns number of chunks deleted."""
    col = get_collection()
    existing = col.get(where={"source": filename}, include=["metadatas"])
    count = len(existing["ids"])
    if count:
        col.delete(where={"source": filename})
        _invalidate_bm25()
        logger.info("Deleted %d chunks for source: %s", count, filename)
    return count
