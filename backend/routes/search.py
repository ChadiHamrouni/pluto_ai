"""Unified content search endpoint: GET /search"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.routes.dependencies import get_current_user
from helpers.tools import knowledge_base as kb
from helpers.tools import memory as mem
from helpers.tools.diagram_meta import search_diagram_meta
from models.search import SearchResponse, SearchResult

logger = get_logger(__name__)
router = APIRouter(prefix="/search", tags=["search"])

# Maps CLI prefix → content_type used in ChromaDB metadata
_PREFIX_MAP: dict[str, str] = {
    "-note":     "note",
    "-notes":    "note",
    "-pdf":      "file",
    "-file":     "file",
    "-memory":   "memory",
    "-mem":      "memory",
    "-obsidian": "obsidian",
    "-obs":      "obsidian",
    "-img":      "image",
    "-image":    "image",
    "-diagram":  "image",
}

# content_type values that live in ChromaDB (not handled separately)
_KB_TYPES = {"file", "note", "memory", "obsidian"}


def _parse_query(raw: str) -> tuple[str, Optional[str]]:
    """
    Extract a type prefix and return (clean_query, content_type_filter).

    Examples:
        "-img redis"   → ("redis", "image")
        "-note master" → ("master", "note")
        "redis"        → ("redis", None)
    """
    raw = raw.strip()
    lower = raw.lower()
    for prefix, ctype in _PREFIX_MAP.items():
        if lower.startswith(prefix + " ") or lower == prefix:
            return raw[len(prefix):].strip(), ctype
    return raw, None


def _make_snippet(text: str, max_len: int = 150) -> str:
    text = text.strip().replace("\n", " ")
    return text[:max_len] + ("…" if len(text) > max_len else "")


def _title_from_source(source: str) -> str:
    """Turn a filename like '20260101T120000-my-redis-notes.md' into 'My Redis Notes'."""
    name = re.sub(r"^\d{8}T\d{6}-", "", source)
    name = re.sub(r"\.(md|pdf|txt|png)$", "", name, flags=re.IGNORECASE)
    return name.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Async wrappers (all underlying calls are sync — run in thread pool)
# ---------------------------------------------------------------------------

async def _search_knowledge_async(
    query: str, content_type_filter: Optional[str], top_k: int
) -> list[SearchResult]:
    loop = asyncio.get_event_loop()

    def _run() -> list[SearchResult]:
        chunks = kb.search_knowledge(query, top_k=top_k, content_type_filter=content_type_filter)
        results = []
        for c in chunks:
            bare_name = c.source.replace("obsidian::", "")
            file_url: Optional[str] = None
            if bare_name.endswith((".pdf", ".png", ".md", ".txt")):
                file_url = f"/files/{bare_name}"
            results.append(SearchResult(
                id=f"kb::{c.source}::{c.chunk_index}",
                content_type=c.content_type,
                title=_title_from_source(bare_name),
                snippet=_make_snippet(c.content),
                source=c.source,
                file_url=file_url,
                score=c.rrf_score,
            ))
        return results

    return await loop.run_in_executor(None, _run)


async def _search_memories_async(query: str, top_k: int) -> list[SearchResult]:
    loop = asyncio.get_event_loop()

    def _run() -> list[SearchResult]:
        db_path = load_config()["memory"]["db_path"]
        rows = mem.search_memories(db_path, query, top_k=top_k)
        results = []
        for r in rows:
            results.append(SearchResult(
                id=f"mem::{r['id']}",
                content_type="memory",
                title=f"Memory · {r.get('category', 'general').title()}",
                snippet=_make_snippet(r["content"]),
                source=r.get("category", "memory"),
                file_url=None,
                score=0.5,  # FTS5 rank is not normalised to [0,1]; fixed mid-value
                created_at=str(r["created_at"]) if r.get("created_at") else None,
            ))
        return results

    return await loop.run_in_executor(None, _run)


async def _search_images_async(query: str, top_k: int) -> list[SearchResult]:
    loop = asyncio.get_event_loop()

    def _run() -> list[SearchResult]:
        hits = search_diagram_meta(query, top_k=top_k)
        results = []
        for h in hits:
            results.append(SearchResult(
                id=f"img::{h['filename']}",
                content_type="image",
                title=h.get("title", h["filename"]),
                snippet=_make_snippet(h.get("mermaid_source", "")),
                source=h["filename"],
                file_url=f"/files/{h['filename']}",
                score=0.6,
                created_at=h.get("created_at"),
            ))
        return results

    return await loop.run_in_executor(None, _run)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    top_k: int = Query(default=10, ge=1, le=30),
    _user: str = Depends(get_current_user),
) -> SearchResponse:
    """
    Unified content search across files, notes, memory, Obsidian vault, and diagrams.

    Supports type filter prefixes in the query:
      -note / -notes     → notes only
      -pdf / -file       → uploaded files only
      -memory / -mem     → memory facts only
      -obsidian / -obs   → Obsidian vault only
      -img / -image / -diagram → diagrams only

    Examples:
      GET /search?q=redis+diagram
      GET /search?q=-img+redis
      GET /search?q=-note+master+plan
    """
    clean_query, type_filter = _parse_query(q)

    if not clean_query:
        return SearchResponse(results=[], query=q, content_type_filter=type_filter, total=0)

    # Fan out to relevant backends in parallel
    tasks = []

    if type_filter == "image":
        tasks.append(_search_images_async(clean_query, top_k))
    elif type_filter == "memory":
        tasks.append(_search_memories_async(clean_query, top_k))
    elif type_filter in _KB_TYPES:
        tasks.append(_search_knowledge_async(clean_query, type_filter, top_k))
    else:
        # No filter — search everything simultaneously
        tasks.append(_search_knowledge_async(clean_query, None, top_k))
        tasks.append(_search_memories_async(clean_query, max(top_k // 2, 3)))
        tasks.append(_search_images_async(clean_query, max(top_k // 2, 3)))

    result_lists = await asyncio.gather(*tasks, return_exceptions=True)

    merged: list[SearchResult] = []
    for r in result_lists:
        if isinstance(r, list):
            merged.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Search backend error: %s", r)

    # De-duplicate by id, sort by score descending
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for item in sorted(merged, key=lambda x: x.score, reverse=True):
        if item.id not in seen:
            seen.add(item.id)
            deduped.append(item)

    return SearchResponse(
        results=deduped[:top_k],
        query=q,
        content_type_filter=type_filter,
        total=len(deduped),
    )
