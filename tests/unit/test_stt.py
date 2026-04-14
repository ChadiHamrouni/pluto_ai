"""
Tests for helpers/tools/stt.py

Uses a mock WhisperModel — no Ollama, no GPU, no model download required.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_segment(text: str):
    return SimpleNamespace(text=text)


# ---------------------------------------------------------------------------
# _transcribe_sync
# ---------------------------------------------------------------------------

def test_transcribe_sync_joins_segments(tmp_path):
    """_transcribe_sync concatenates segment texts and strips whitespace."""
    from helpers.tools import stt as stt_module

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (
        [_make_segment(" Hello"), _make_segment(" world ")],
        None,
    )

    with patch.object(stt_module, "_model", mock_model):
        result = stt_module._transcribe_sync(b"fake-audio-bytes", "audio.webm")

    assert result == "Hello world"
    mock_model.transcribe.assert_called_once()
    call_kwargs = mock_model.transcribe.call_args
    assert call_kwargs.kwargs.get("beam_size") == 5
    assert call_kwargs.kwargs.get("language") is None


def test_transcribe_sync_empty_segments(tmp_path):
    """Returns empty string when model returns no segments."""
    from helpers.tools import stt as stt_module

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], None)

    with patch.object(stt_module, "_model", mock_model):
        result = stt_module._transcribe_sync(b"fake-audio-bytes", "audio.webm")

    assert result == ""


def test_transcribe_sync_cleans_up_temp_file():
    """Temp file must be deleted even on successful transcription."""
    import tempfile
    from pathlib import Path
    from helpers.tools import stt as stt_module

    created_paths: list[Path] = []
    original_ntf = tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        ctx = original_ntf(*args, **kwargs)
        created_paths.append(Path(ctx.name))
        return ctx

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([_make_segment("hi")], None)

    with patch.object(stt_module, "_model", mock_model), \
         patch("helpers.tools.stt.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
        stt_module._transcribe_sync(b"x", "audio.webm")

    for p in created_paths:
        assert not p.exists(), f"Temp file not cleaned up: {p}"


def test_transcribe_sync_cleans_up_on_error():
    """Temp file must be deleted even when model.transcribe raises."""
    import tempfile
    from pathlib import Path
    from helpers.tools import stt as stt_module

    created_paths: list[Path] = []
    original_ntf = tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        ctx = original_ntf(*args, **kwargs)
        created_paths.append(Path(ctx.name))
        return ctx

    mock_model = MagicMock()
    mock_model.transcribe.side_effect = RuntimeError("model exploded")

    with patch.object(stt_module, "_model", mock_model), \
         patch("helpers.tools.stt.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
        try:
            stt_module._transcribe_sync(b"x", "audio.webm")
        except RuntimeError:
            pass

    for p in created_paths:
        assert not p.exists(), f"Temp file not cleaned up after error: {p}"


# ---------------------------------------------------------------------------
# transcribe_audio (async)
# ---------------------------------------------------------------------------

def test_transcribe_audio_async():
    """transcribe_audio delegates to _transcribe_sync via run_in_executor."""
    from helpers.tools import stt as stt_module

    with patch.object(stt_module, "_transcribe_sync", return_value="async result") as mock_sync:
        result = asyncio.run(stt_module.transcribe_audio(b"bytes", "audio.webm"))

    assert result == "async result"
    mock_sync.assert_called_once_with(b"bytes", "audio.webm")


# ---------------------------------------------------------------------------
# _get_model singleton
# ---------------------------------------------------------------------------

def test_get_model_loads_once():
    """WhisperModel is instantiated only once regardless of concurrent calls."""
    from helpers.tools import stt as stt_module

    mock_model_instance = MagicMock()
    mock_whisper_cls = MagicMock(return_value=mock_model_instance)

    original_model = stt_module._model
    try:
        stt_module._model = None
        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_cls)}):
            m1 = stt_module._get_model()
            m2 = stt_module._get_model()
    finally:
        stt_module._model = original_model

    assert m1 is m2
    assert mock_whisper_cls.call_count == 1
