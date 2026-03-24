from __future__ import annotations

from pydantic import BaseModel, Field

_MAX_TEXT_LEN = 10_000


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_TEXT_LEN)
