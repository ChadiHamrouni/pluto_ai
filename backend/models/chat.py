from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(
        description="Message role.",
        examples=["user"],
    )
    content: str = Field(description="Message text content.")


class Attachment(BaseModel):
    filename: str = Field(description="Original filename of the uploaded file.")
    mime_type: str = Field(
        description="MIME type detected from the file extension.", examples=["image/png"]
    )
    size_bytes: int = Field(description="File size in bytes.")


class ChatRequest(BaseModel):
    message: str = Field(description="The user's message text.")
    history: List[ChatMessage] = Field(
        default_factory=list, description="Prior conversation turns."
    )
    context_category: Optional[str] = Field(None, description="Optional memory category filter.")


class ChatResponse(BaseModel):
    response: str = Field(
        description="The assistant's reply.",
        examples=["Here is a summary of your notes from this week."],
    )
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Metadata for any files attached to the request.",
    )
    tools_used: List[str] = Field(
        default_factory=list,
        description="Names of every tool called during this turn.",
        examples=[["web_search", "store_memory"]],
    )
    agents_trace: List[str] = Field(
        default_factory=list,
        description="Ordered list of agent names that handled this turn.",
        examples=[["Orchestrator", "SlidesAgent"]],
    )
    file_url: Optional[str] = Field(
        None,
        description="Download URL for a generated file (e.g. slides PDF)."
        " Null if no file was produced.",
        examples=["/files/presentation_ai_2025.pdf"],
    )
    latency_ms: Optional[int] = Field(
        None,
        description="Total wall-clock time for the request in milliseconds.",
    )
    user_file_urls: List[str] = Field(
        default_factory=list,
        description="Serve URLs for uploaded user attachments (PDFs/images) stored server-side.",
    )
