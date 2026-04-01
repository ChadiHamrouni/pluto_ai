from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: str
    content_type: str       # file | note | memory | obsidian | image
    title: str
    snippet: str            # ≤150 chars
    source: str             # bare filename or obsidian::-prefixed path
    file_url: Optional[str] = None  # /files/<filename> or None (memory has no file)
    score: float
    created_at: Optional[str] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    content_type_filter: Optional[str] = None
    total: int
