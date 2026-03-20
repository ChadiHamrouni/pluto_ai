"""
Tests for helpers/agents/runner.py

Verifies that run_agent():
- Returns the model's text response
- Executes tool calls and sends a follow-up turn
- Raises RuntimeError on timeout
- Raises RuntimeError on LLM error
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from helpers.agents.runner import run_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent(tools: list | None = None) -> MagicMock:
    """Minimal fake Agent object."""
    a = MagicMock()
    a.name = "Orchestrator"
    a.tools = tools or []
    return a


def _make_response(content: str, finish_reason: str = "stop") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_tool_response(tool_name: str, args: str) -> MagicMock:
    tc = MagicMock()
    tc.id = "call_abc"
    tc.function.name = tool_name
    tc.function.arguments = args
    msg = MagicMock()
    msg.content = ""
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"
    resp = MagicMock()
    resp.choices = [choice]
    return resp


MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "hi"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_simple_response(mock_ollama_client):
    """run_agent returns the model's text when no tool calls."""
    mock_ollama_client.chat.completions.create = AsyncMock(
        return_value=_make_response("Hello there!")
    )
    result = await run_agent(_agent(), MESSAGES)
    assert result == "Hello there!"


@pytest.mark.asyncio
async def test_run_agent_empty_response(mock_ollama_client):
    """run_agent returns empty string when model returns None content."""
    mock_ollama_client.chat.completions.create = AsyncMock(
        return_value=_make_response(None)
    )
    result = await run_agent(_agent(), MESSAGES)
    assert result == ""


@pytest.mark.asyncio
async def test_run_agent_tool_call_executed(mock_ollama_client):
    """
    When model returns finish_reason=tool_calls:
    - tool function is called with parsed args
    - follow-up LLM call is made
    - final text is returned
    """
    fake_tool = MagicMock()
    fake_tool.name = "store_memory"
    fake_tool.description = "Store a memory"
    fake_tool.params_json_schema = {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
    }
    fake_tool.return_value = "Memory stored."

    tool_resp = _make_tool_response("store_memory", json.dumps({"content": "I like Python"}))
    final_resp = _make_response("Got it, I'll remember that.")

    mock_ollama_client.chat.completions.create = AsyncMock(
        side_effect=[tool_resp, final_resp]
    )

    result = await run_agent(_agent(tools=[fake_tool]), MESSAGES)

    assert result == "Got it, I'll remember that."
    fake_tool.assert_called_once_with(content="I like Python")
    assert mock_ollama_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_run_agent_async_tool(mock_ollama_client):
    """Async tool functions are awaited correctly."""
    fake_tool = AsyncMock(return_value="async result")
    fake_tool.name = "async_tool"
    fake_tool.description = "An async tool"
    fake_tool.params_json_schema = {"type": "object", "properties": {}, "required": []}

    tool_resp = _make_tool_response("async_tool", "{}")
    final_resp = _make_response("Done async.")

    mock_ollama_client.chat.completions.create = AsyncMock(
        side_effect=[tool_resp, final_resp]
    )

    result = await run_agent(_agent(tools=[fake_tool]), MESSAGES)
    assert result == "Done async."


@pytest.mark.asyncio
async def test_run_agent_unknown_tool_graceful(mock_ollama_client):
    """When model calls a tool not in tool_map, error is sent back gracefully."""
    tool_resp = _make_tool_response("nonexistent_tool", "{}")
    final_resp = _make_response("I tried but that tool doesn't exist.")

    mock_ollama_client.chat.completions.create = AsyncMock(
        side_effect=[tool_resp, final_resp]
    )

    # Agent has no tools registered
    result = await run_agent(_agent(tools=[]), MESSAGES)
    assert result == "I tried but that tool doesn't exist."


@pytest.mark.asyncio
async def test_run_agent_timeout_raises(mock_ollama_client):
    """TimeoutError is wrapped as RuntimeError."""
    import asyncio
    mock_ollama_client.chat.completions.create = AsyncMock(
        side_effect=asyncio.TimeoutError()
    )

    with pytest.raises(RuntimeError, match="timed out"):
        await run_agent(_agent(), MESSAGES)


@pytest.mark.asyncio
async def test_run_agent_llm_error_raises(mock_ollama_client):
    """Generic LLM exception is wrapped as RuntimeError."""
    mock_ollama_client.chat.completions.create = AsyncMock(
        side_effect=Exception("connection refused")
    )

    with pytest.raises(RuntimeError, match="LLM call failed"):
        await run_agent(_agent(), MESSAGES)
