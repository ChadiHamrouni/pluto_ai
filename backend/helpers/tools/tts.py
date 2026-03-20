"""
Text-to-speech backed by CosyVoice2-0.5B (FunAudioLLM).

Exposes two synthesis modes:

  synthesize_stream(text)
      Legacy: streams a single WAV (header + PCM chunks) for the full text.
      Used by POST /tts.

  synthesize_sentences(text)
      New: splits text into sentences and yields one length-prefixed WAV blob
      per sentence.  Protocol: 4-byte little-endian uint32 length followed by
      that many bytes of a complete WAV file.  This lets the frontend start
      playing the first sentence (~300 ms) while the rest are still generating.
      Used by POST /tts/sentences.

Dependencies (add to requirements.txt):
    torchaudio
    onnxruntime
    WeTextProcessing
CosyVoice is cloned in the Dockerfile and added to PYTHONPATH.
"""

from __future__ import annotations

import io
import re
import struct
import wave
from typing import Generator

import torch

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

_model = None
_sample_rate: int = 22050
_ready: bool = False

# Sentence boundary pattern — split after . ! ? followed by space/newline,
# or on newline pairs.  Keeps the punctuation attached to the sentence.
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=\n)\n+')


def is_ready() -> bool:
    return _ready


def load_model() -> None:
    """Eagerly load CosyVoice2-0.5B. Safe to call multiple times."""
    _load_model()


def _load_model():
    global _model, _sample_rate, _ready
    if _model is not None:
        return _model

    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2
    except ImportError as e:
        logger.error(
            "CosyVoice2 not installed. Clone FunAudioLLM/CosyVoice and add to PYTHONPATH."
        )
        raise RuntimeError("CosyVoice2 not installed") from e

    config = load_config()
    model_name = config.get("tts", {}).get("model", "FunAudioLLM/CosyVoice2-0.5B")

    logger.info("Loading TTS model '%s' ...", model_name)
    _model = CosyVoice2(model_name, load_jit=False, load_trt=False)
    _sample_rate = _model.sample_rate
    _ready = True
    logger.info("TTS model loaded. Sample rate: %d Hz", _sample_rate)
    return _model


# ── WAV helpers ───────────────────────────────────────────────────────────────

def _wav_header_streaming(sample_rate: int, num_channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """WAV header with max data size — for streaming where total length is unknown."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(num_channels)
        w.setsampwidth(bits_per_sample // 8)
        w.setframerate(sample_rate)
        w.setnframes(0)
    header = bytearray(buf.getvalue())
    struct.pack_into("<I", header, 4, 0x7FFFFFFF)   # RIFF chunk size
    struct.pack_into("<I", header, 40, 0x7FFFFFFF)  # data sub-chunk size
    return bytes(header)


def _wav_complete(pcm_bytes: bytes, sample_rate: int, num_channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Build a complete, correctly-sized WAV file from raw PCM bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(num_channels)
        w.setsampwidth(bits_per_sample // 8)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def _pcm16(tensor: "torch.Tensor") -> bytes:
    """Convert a float32 waveform tensor (range -1..1) to 16-bit PCM bytes."""
    samples = tensor.squeeze().float().clamp(-1.0, 1.0)
    return (samples * 32767).short().numpy().tobytes()


def _synthesize_to_pcm(text: str, speaker: str) -> bytes:
    """Synthesise a short text fragment to raw PCM bytes (blocking)."""
    model = _load_model()
    parts = []
    for result in model.inference_sft(text, spk_id=speaker, stream=True):
        audio = result.get("tts_speech")
        if audio is not None and audio.numel() > 0:
            parts.append(_pcm16(audio))
    return b"".join(parts)


# ── Public synthesis functions ────────────────────────────────────────────────

def synthesize_stream(text: str) -> Generator[bytes, None, None]:
    """
    Legacy: yield WAV header then PCM chunks for the full text.
    Used by POST /tts — kept for backward compatibility.
    """
    model = _load_model()
    config = load_config()
    speaker = config.get("tts", {}).get("speaker", "English (US) Female")

    yield _wav_header_streaming(_sample_rate)

    for result in model.inference_sft(text, spk_id=speaker, stream=True):
        audio = result.get("tts_speech")
        if audio is not None and audio.numel() > 0:
            yield _pcm16(audio)


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
    First audio arrives in ~300 ms regardless of response length.
    """
    config = load_config()
    speaker = config.get("tts", {}).get("speaker", "English (US) Female")

    sentences = split_sentences(text)
    if not sentences:
        return

    for sentence in sentences:
        pcm = _synthesize_to_pcm(sentence, speaker)
        if not pcm:
            continue
        wav = _wav_complete(pcm, _sample_rate)
        length_prefix = struct.pack("<I", len(wav))
        yield length_prefix + wav
