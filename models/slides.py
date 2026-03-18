from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SlideRequest(BaseModel):
    title: str
    content: str
    theme: str = Field(default="default")
    output_format: Literal["pdf", "html"] = "pdf"


class SlideResponse(BaseModel):
    file_path: str
    title: str
    message: str
