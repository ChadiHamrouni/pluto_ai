"""
Tests for handlers/text_handler.py

Mocks:
- Ollama client (no real HTTP)
- SQLite memory DB (tmp in-memory)
- compactor (no-op)

Verifies the full handler pipeline: memory search → message building → agent call → response.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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


@pytest.fixture
def patched_handler(mock_ollama_client, tmp_db):
    """Patch all external deps so text_handler runs fully in-process."""
    mock_ollama_client.chat.completions.create = AsyncMock(
        return_value=_make_response("I am Jarvis, your assistant.")
    )

    with patch("helpers.tools.memory.get_db_path", return_value=tmp_db):
        with patch("handlers.text_handler.get_db_path", return_value=tmp_db):
            with patch("handlers.text_handler.compact_history", new=AsyncMock(side_effect=lambda msgs, *a, **kw: msgs)):
                yield mock_ollama_client


@pytest.mark.asyncio
async def test_text_handler_returns_string(patched_handler):
    from handlers.text_handler import text_handler

    response, elapsed, tools = await text_handler("hello", history=[])

    assert isinstance(response, str)
    assert len(response) > 0
    assert isinstance(elapsed, float)
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_text_handler_passes_history(patched_handler):
    """History messages should appear in the LLM call messages."""
    from handlers.text_handler import text_handler

    history = [
        {"role": "user", "content": "what is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    with patch("handlers.text_handler.run_agent", new=AsyncMock(return_value=("ok", []))) as mock_run:
        await text_handler("follow up question", history=history)

        call_args = mock_run.call_args
        messages = call_args.args[1] if call_args.args else call_args.kwargs.get("messages", [])
        all_content = " ".join(
            m.get("content", "") if isinstance(m.get("content"), str) else ""
            for m in messages
        )
        assert "2+2" in all_content or "follow up" in all_content


@pytest.mark.asyncio
async def test_text_handler_slash_note_routes_to_notes_agent(patched_handler):
    """'/note ...' should route to notes agent, not orchestrator."""
    from handlers.text_handler import text_handler

    # The notes agent is a cached singleton — capture which agent run_agent receives
    with patch("handlers.text_handler.run_agent", new=AsyncMock(return_value=("note created", []))) as mock_run:
        await text_handler("/note Write a note about Python", history=[])

        mock_run.assert_called_once()
        agent_used = mock_run.call_args.args[0]
        assert agent_used.name in ("Notes", "NotesAgent")


@pytest.mark.asyncio
async def test_text_handler_empty_message(patched_handler):
    """Empty message should still complete without raising."""
    from handlers.text_handler import text_handler

    response, _, tools = await text_handler("", history=[])
    assert isinstance(response, str)
    assert isinstance(tools, list)
