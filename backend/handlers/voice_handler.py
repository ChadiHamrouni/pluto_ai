from __future__ import annotations

import time
from pathlib import Path

from helpers.core.logger import get_logger
from models.chat import ChatMessage

logger = get_logger(__name__)


async def voice_handler(
    audio_path: Path,
    history: list[ChatMessage],
) -> tuple[str, float]:
    """
    Voice-in / voice-out handler.

    Flow (to be implemented):
      1. STT  — transcribe audio_path → text
      2. TEXT — pass transcript through text_handler
      3. TTS  — synthesise response text → audio bytes
      4. Return audio bytes (and/or transcript text)
    """
    t0 = time.perf_counter()
    raise NotImplementedError("Voice handler not yet implemented")
    return "", time.perf_counter() - t0  # noqa: F821
