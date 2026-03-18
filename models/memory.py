from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    teaching = "teaching"
    research = "research"
    career = "career"
    personal = "personal"
    ideas = "ideas"


class MemoryEntry(BaseModel):
    id: Optional[int] = None
    content: str
    category: MemoryCategory
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    relevance_score: Optional[float] = None

    class Config:
        from_attributes = True


class MemorySearchRequest(BaseModel):
    query: str
    category: Optional[MemoryCategory] = None
    top_k: int = Field(default=5, ge=1, le=50)


class MemorySearchResult(BaseModel):
    entries: List[MemoryEntry]
    query: str


class MemoryStoreRequest(BaseModel):
    content: str
    category: MemoryCategory
    tags: List[str] = Field(default_factory=list)
