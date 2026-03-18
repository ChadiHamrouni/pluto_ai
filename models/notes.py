from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class NoteCategory(str, Enum):
    teaching = "teaching"
    research = "research"
    career = "career"
    personal = "personal"
    ideas = "ideas"


class Note(BaseModel):
    id: Optional[int] = None
    title: str
    content: str
    category: NoteCategory
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    file_path: Optional[str] = None

    class Config:
        from_attributes = True


class NoteCreateRequest(BaseModel):
    title: str
    content: str
    category: NoteCategory
    tags: List[str] = Field(default_factory=list)


class NoteResponse(BaseModel):
    note: Note
    message: str
