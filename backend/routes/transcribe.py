from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from helpers.core.logger import get_logger
from helpers.routes.dependencies import get_current_user
from helpers.tools.stt import transcribe_audio
from models.transcribe import TranscribeResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/transcribe", tags=["stt"])

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
_ALLOWED_AUDIO_EXTS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".flac"}


@router.post("", response_model=TranscribeResponse, summary="Transcribe audio")
async def transcribe(
    file: UploadFile = File(..., description="Audio file (WebM, WAV, MP3, etc.)"),
    _user: str = Depends(get_current_user),
):
    """Transcribe speech from an uploaded audio file using Faster-Whisper."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type '{ext}'. Allowed: {sorted(_ALLOWED_AUDIO_EXTS)}",
        )

    data = await file.read(_MAX_AUDIO_BYTES + 1)
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file exceeds the 25 MB limit.",
        )

    logger.info("POST /transcribe — file='%s' size=%d bytes", file.filename, len(data))

    try:
        text = await transcribe_audio(data, file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed.",
        )

    logger.info("Transcription complete: %r", text[:60])
    return TranscribeResponse(text=text)
