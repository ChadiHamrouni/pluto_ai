from __future__ import annotations

from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    text: str = Field(
        description="Transcribed text from the uploaded audio file.",
        examples=["What is the capital of France?"],
    )
