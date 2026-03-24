"""
TTS routes

POST /tts
    Legacy: streams the full response as a single WAV (header + PCM chunks).
    Kept for backward compatibility.

POST /tts/sentences
    New sentence-level endpoint.  Streams one length-prefixed WAV blob per
    sentence so the frontend can start playing the first sentence (~300 ms)
    while the remainder are still generating.

    Binary protocol per sentence:
        [4 bytes uint32 LE: blob length] [N bytes: complete WAV file]
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from helpers.core.logger import get_logger
from helpers.tools import tts
from models.tts import TTSRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


def _check_ready():
    if not tts.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS model is not loaded yet — try again in a moment.",
        )


@router.post("")
async def text_to_speech(
    req: TTSRequest,
):
    """Legacy: synthesise text and stream back as a single WAV."""
    _check_ready()
    logger.info("TTS /tts request: %d chars", len(req.text))
    return StreamingResponse(
        tts.synthesize_stream(req.text),
        media_type="audio/wav",
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/sentences")
async def text_to_speech_sentences(
    req: TTSRequest,
):
    """Sentence-level: stream one length-prefixed WAV blob per sentence.

    The frontend reads 4-byte length then that many bytes, decodes + plays each
    sentence as it arrives — first audio in ~300 ms regardless of length.
    """
    _check_ready()
    logger.info("TTS /tts/sentences request: %d chars", len(req.text))
    return StreamingResponse(
        tts.synthesize_sentences(req.text),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )
