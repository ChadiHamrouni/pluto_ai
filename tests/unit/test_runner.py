"""
Unit tests for helpers/agents/runner.py

Mocks Runner.run (OpenAI Agents SDK) — no real Ollama or network calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.results import AgentRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_result(
    final_output: str = "Hello!",
    tool_names: list[str] | None = None,
    agent_name: str = "Orchestrator",
) -> MagicMock:
    """Build a minimal fake RunResult as returned by Runner.run."""
    from agents.items import ToolCallItem, ToolCallOutputItem

    new_items: list = []

    for tool in (tool_names or []):
        item = MagicMock(spec=ToolCallItem)
        item.agent = MagicMock()
        item.agent.name = agent_name
        raw = MagicMock()
        raw.function = MagicMock()
        raw.function.name = tool
        item.raw_item = raw
        new_items.append(item)

    result = MagicMock()
    result.final_output = final_output
    result.new_items = new_items
    return result


def _agent(name: str = "Orchestrator") -> MagicMock:
    a = MagicMock()
    a.name = name
    a.instructions = "You are helpful."
    a.clone = MagicMock(return_value=a)
    return a


MESSAGES = [
    {"role": "user", "content": "hello"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_returns_response():
    with patch("helpers.agents.runner.Runner.run", new=AsyncMock(return_value=_make_run_result("Hi there!"))):
        from helpers.agents.runner import run_agent
        result = await run_agent(_agent(), MESSAGES)

    assert isinstance(result, AgentRunResult)
    assert result.response == "Hi there!"
    assert result.tools_used == []
    assert "Orchestrator" in result.agents_trace


@pytest.mark.asyncio
async def test_run_agent_records_tools_used():
    run_result = _make_run_result("Done.", tool_names=["store_memory"])
    with patch("helpers.agents.runner.Runner.run", new=AsyncMock(return_value=run_result)):
        from helpers.agents.runner import run_agent
        result = await run_agent(_agent(), MESSAGES)

    assert "store_memory" in result.tools_used


@pytest.mark.asyncio
async def test_run_agent_empty_final_output_falls_back_to_tool_output():
    """When final_output is empty, runner should fall back to last tool output."""
    from agents.items import ToolCallOutputItem

    tool_out_item = MagicMock(spec=ToolCallOutputItem)
    tool_out_item.agent = MagicMock()
    tool_out_item.agent.name = "SlidesAgent"
    tool_out_item.output = "/data/slides/deck.pdf"
    tool_out_item.raw_item = None

    run_result = MagicMock()
    run_result.final_output = ""
    run_result.new_items = [tool_out_item]

    with patch("helpers.agents.runner.Runner.run", new=AsyncMock(return_value=run_result)):
        from helpers.agents.runner import run_agent
        result = await run_agent(_agent(), MESSAGES)

    assert "/data/slides/deck.pdf" in result.response


@pytest.mark.asyncio
async def test_run_agent_raises_on_sdk_error():
    with patch("helpers.agents.runner.Runner.run", new=AsyncMock(side_effect=Exception("connection refused"))):
        from helpers.agents.runner import run_agent
        with pytest.raises(RuntimeError, match="Agent run failed"):
            await run_agent(_agent(), MESSAGES)


@pytest.mark.asyncio
async def test_run_agent_injects_memory_context_via_clone():
    """When memory_context is given, the orchestrator is cloned with updated instructions."""
    agent = _agent("Orchestrator")
    cloned = MagicMock()
    cloned.name = "Orchestrator"
    cloned.instructions = "You are helpful.\n\nUser remembers: X"
    agent.clone = MagicMock(return_value=cloned)

    run_result = _make_run_result("Got it.")
    with patch("helpers.agents.runner.Runner.run", new=AsyncMock(return_value=run_result)) as mock_run:
        from helpers.agents.runner import run_agent
        await run_agent(agent, MESSAGES, memory_context="User remembers: X")

    agent.clone.assert_called_once()
    # The cloned agent (not original) is what gets passed to Runner.run
    call_kwargs = mock_run.call_args.kwargs
    used_agent = call_kwargs.get("starting_agent", mock_run.call_args.args[0] if mock_run.call_args.args else None)
    assert used_agent is cloned
