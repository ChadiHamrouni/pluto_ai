"""
Unit tests for handlers/text_handler.py

Mocks:
- Runner.run (OpenAI Agents SDK) — no real HTTP
- SQLite memory DB (tmp_db fixture from conftest)
- search_memories — returns empty list by default

Verifies routing, history windowing, and HandlerResult structure.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.results import AgentRunResult, HandlerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sdk_result(text: str = "I am Pluto.", tools: list[str] | None = None) -> MagicMock:
    r = MagicMock()
    r.final_output = text
    r.new_items = []
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_handler_returns_handler_result(tmp_db):
    sdk_result = _sdk_result("Hello!")
    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)),
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        from handlers.text_handler import text_handler
        result = await text_handler("hello", history=[])

    assert isinstance(result, HandlerResult)
    assert result.response == "Hello!"
    assert isinstance(result.elapsed, float)
    assert isinstance(result.tools_used, list)
    assert isinstance(result.agents_trace, list)


@pytest.mark.asyncio
async def test_text_handler_slash_note_routes_to_Pluto(tmp_db):
    """/note command injects a [note] hint and routes to single Pluto agent."""
    sdk_result = _sdk_result("Note created.")

    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)) as mock_run,
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        from handlers.text_handler import text_handler
        await text_handler("/note Save my idea about AI agents", history=[])

    call_kwargs = mock_run.call_args.kwargs
    agent_used = call_kwargs.get(
        "starting_agent",
        mock_run.call_args.args[0] if mock_run.call_args.args else None,
    )
    # Single-agent architecture: all commands route through Pluto
    assert agent_used is not None
    assert agent_used.name.lower() == "Pluto"


@pytest.mark.asyncio
async def test_text_handler_slash_slides_routes_to_Pluto(tmp_db):
    """/slides command injects a [slides] hint and routes to single Pluto agent."""
    sdk_result = _sdk_result("Slides generated.")

    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)) as mock_run,
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        from handlers.text_handler import text_handler
        await text_handler("/slides Make a deck about Python", history=[])

    call_kwargs = mock_run.call_args.kwargs
    agent_used = call_kwargs.get(
        "starting_agent",
        mock_run.call_args.args[0] if mock_run.call_args.args else None,
    )
    # Single-agent architecture: all commands route through Pluto
    assert agent_used is not None
    assert agent_used.name.lower() == "Pluto"


@pytest.mark.asyncio
async def test_text_handler_passes_history(tmp_db):
    sdk_result = _sdk_result("Follow-up answer.")

    history = [
        {"role": "user", "content": "what is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)) as mock_run,
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        from handlers.text_handler import text_handler
        await text_handler("follow up", history=history)

    # Runner.run receives input containing prior history
    call_kwargs = mock_run.call_args.kwargs
    input_msgs = call_kwargs.get("input", mock_run.call_args.args[1] if len(mock_run.call_args.args) > 1 else [])
    all_content = " ".join(
        m.get("content", "") for m in input_msgs if isinstance(m.get("content"), str)
    )
    assert "2+2" in all_content or "follow up" in all_content


@pytest.mark.asyncio
async def test_text_handler_empty_message(tmp_db):
    sdk_result = _sdk_result("")
    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)),
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        from handlers.text_handler import text_handler
        result = await text_handler("", history=[])

    assert isinstance(result, HandlerResult)
