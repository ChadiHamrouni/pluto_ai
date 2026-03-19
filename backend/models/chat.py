from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class Attachment(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = Field(default_factory=list)
    context_category: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    attachments: List[Attachment] = Field(default_factory=list)
