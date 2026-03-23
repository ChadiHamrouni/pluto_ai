"""
Text-to-speech backed by Qwen3-TTS (Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice).

Exposes two synthesis modes:

  synthesize_stream(text)
      Legacy: streams a single WAV for the full text.
      Used by POST /tts.

  synthesize_sentences(text)
      Splits text into sentences and yields one length-prefixed WAV blob
      per sentence.  Protocol: 4-byte little-endian uint32 length followed by
      that many bytes of a complete WAV file.  This lets the frontend start
      playing the first sentence while the rest are still generating.
      Used by POST /tts/sentences.

Dependencies (in requirements.txt):
    qwen-tts
    soundfile
    torch
"""

from __future__ import annotations

import io
import re
import struct
import wave
from typing import Generator

import numpy as np

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

_model = None
_sample_rate: int = 12000  # Qwen3-TTS outputs 12 kHz
_ready: bool = False

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|(?<=\n)\n+")


def is_ready() -> bool:
    return _ready


def load_model() -> None:
    """Eagerly load Qwen3-TTS model. Safe to call multiple times."""
    _load_model()


def _load_model():
    global _model, _sample_rate, _ready
    if _model is not None:
        return _model

    try:
        import torch
        from qwen_tts import Qwen3TTSModel
    except ImportError as e:
        logger.error("qwen-tts not installed. Add 'qwen-tts' to requirements.txt.")
        raise RuntimeError("qwen-tts not installed") from e

    config = load_config()
    model_name = config.get("tts", {}).get("model", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")

    logger.info("Loading TTS model '%s' ...", model_name)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    _model = Qwen3TTSModel.from_pretrained(
        model_name,
        device_map=device,
        dtype=dtype,
    )
    _ready = True
    logger.info("TTS model loaded. Device: %s", device)
    return _model


# ── WAV helpers ───────────────────────────────────────────────────────────────


def _wav_complete(pcm_float: np.ndarray, sample_rate: int) -> bytes:
    """Build a complete WAV file from a float32 numpy array (range -1..1)."""
    pcm_int16 = (np.clip(pcm_float, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_int16.tobytes())
    return buf.getvalue()


def _synthesize_to_wav(text: str) -> bytes:
    """Synthesise a text fragment to a complete WAV bytes blob."""
    model = _load_model()
    config = load_config()
    speaker = config.get("tts", {}).get("speaker", "Ryan")
    instruct = config.get("tts", {}).get("instruct", "")

    kwargs = dict(
        text=text,
        language="English",
        speaker=speaker,
    )
    if instruct:
        kwargs["instruct"] = instruct

    wavs, sr = model.generate_custom_voice(**kwargs)
    audio = wavs[0]  # numpy float32 array
    return _wav_complete(audio, sr)


# ── Public synthesis functions ────────────────────────────────────────────────


def synthesize_stream(text: str) -> Generator[bytes, None, None]:
    """
    Legacy: yield a single complete WAV for the full text.
    Used by POST /tts — kept for backward compatibility.
    """
    wav = _synthesize_to_wav(text)
    yield wav


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering out empty fragments."""
    parts = _SENTENCE_RE.split(text.strip())
    return [s.strip() for s in parts if s.strip()]


def synthesize_sentences(text: str) -> Generator[bytes, None, None]:
    """
    Sentence-level synthesis: yields one length-prefixed WAV blob per sentence.

    Binary protocol per sentence:
        [4 bytes: uint32 LE — length of WAV blob] [N bytes: complete WAV file]

    The frontend reads the 4-byte length, reads that many bytes, decodes and
    plays the WAV, while the next sentence is still generating.
    """
    sentences = split_sentences(text)
    if not sentences:
        return

    for sentence in sentences:
        try:
            wav = _synthesize_to_wav(sentence)
        except Exception as exc:
            logger.warning("TTS failed for sentence %r: %s", sentence[:40], exc)
            continue
        if not wav:
            continue
        length_prefix = struct.pack("<I", len(wav))
        yield length_prefix + wav
