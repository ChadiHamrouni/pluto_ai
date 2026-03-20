"""
Tests for helpers/agents/compactor.py + token_counter.py

No Ollama needed — LLM calls are mocked.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Token counter
# ---------------------------------------------------------------------------

def test_estimate_tokens_basic():
    from helpers.agents.token_counter import estimate_tokens
    assert estimate_tokens("hello") > 0
    assert estimate_tokens("") == 0
    # rough check: ~1 token per 4 chars
    assert estimate_tokens("a" * 400) == pytest.approx(100, abs=10)


def test_needs_compaction_false_for_short_history():
    from helpers.agents.token_counter import needs_compaction
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert needs_compaction(messages) is False


def test_needs_compaction_true_for_long_history():
    from helpers.agents.token_counter import needs_compaction, MODEL_CONTEXT_WINDOW
    # Fill past the 75% threshold
    long_content = "x" * int(MODEL_CONTEXT_WINDOW * 4 * 0.8)
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": long_content},
    ]
    assert needs_compaction(messages) is True


# ---------------------------------------------------------------------------
# Compactor
# ---------------------------------------------------------------------------

def _make_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_compact_history_noop_when_short():
    """compact_history returns messages unchanged when under threshold."""
    from helpers.agents.compactor import compact_history

    mock_client = MagicMock()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = await compact_history(messages, mock_client, "qwen3.5:2b")
    assert result == messages
    mock_client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_compact_history_summarises_old_messages(mock_ollama_client):
    """When over threshold, old messages are replaced with a summary."""
    from helpers.agents.compactor import compact_history
    from helpers.agents.token_counter import MODEL_CONTEXT_WINDOW

    mock_ollama_client.chat.completions.create = AsyncMock(
        return_value=_make_response("Summary: user discussed Python and AI.")
    )

    long_content = "x" * int(MODEL_CONTEXT_WINDOW * 4 * 0.8)
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": long_content},
        {"role": "assistant", "content": "I see."},
        {"role": "user", "content": "another message"},
    ]

    result = await compact_history(messages, mock_ollama_client, "qwen3.5:2b")

    # System prompt must be preserved
    assert result[0]["role"] == "system"
    # The compacted result has fewer or equal messages but much shorter total token count
    all_content = " ".join(m.get("content", "") for m in result if isinstance(m.get("content"), str))
    # The huge content should be gone, replaced by the summary
    assert len(all_content) < len(long_content)
    assert "Summary" in all_content
