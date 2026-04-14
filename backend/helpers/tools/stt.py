from __future__ import annotations

import asyncio
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = get_logger(__name__)

_model: "WhisperModel | None" = None
_model_lock = threading.Lock()


def _get_model() -> "WhisperModel":
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel

                cfg = load_config().get("stt", {})
                model_name = cfg.get("model", "large-v3-turbo")
                device = cfg.get("device", "auto")
                compute_type = cfg.get("compute_type", "auto")
                logger.info(
                    "Loading Faster-Whisper model '%s' (device=%s, compute_type=%s) — "
                    "first run will download ~1.5 GB from HuggingFace Hub",
                    model_name,
                    device,
                    compute_type,
                )
                _model = WhisperModel(model_name, device=device, compute_type=compute_type)
                logger.info("Faster-Whisper model loaded.")
    return _model


_MIN_AUDIO_BYTES = 1_000  # anything smaller is just a container header with no audio


def _transcribe_sync(audio_bytes: bytes, filename: str) -> str:
    """Synchronous transcription — runs in a thread to avoid blocking the event loop."""
    if len(audio_bytes) < _MIN_AUDIO_BYTES:
        raise ValueError(
            f"Audio payload too small ({len(audio_bytes)} bytes) — recording may be empty."
        )

    suffix = Path(filename).suffix or ".webm"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        model = _get_model()
        segments, _info = model.transcribe(str(tmp_path), beam_size=1, language="en")
        text = " ".join(seg.text for seg in segments).strip()
        return text
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Transcribe speech from raw audio bytes. Offloads blocking inference to a thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, audio_bytes, filename)
