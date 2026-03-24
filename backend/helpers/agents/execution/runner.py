from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents import Agent, RunConfig, Runner

from helpers.agents.execution.event_parser import (
    extract_last_tool_output,
    extract_run_metadata,
    process_stream_event,
    unwrap_handle_turn,
)
from helpers.agents.routing.prompt_utils import _build_context_block
from helpers.core.logger import get_logger
from models.results import AgentRunResult

logger = get_logger(__name__)

_RUN_CONFIG = RunConfig(tracing_disabled=True)


def _prepare_input(messages: list[dict]) -> list[dict]:
    """Filter to user/assistant turns and ensure at least one item."""
    items = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]
    return items or [{"role": "user", "content": ""}]


def _inject_context(agent: Agent, memory_context: str) -> Agent:
    """Clone the agent with date/time context and optional memory injected."""
    extra = _build_context_block()
    if memory_context:
        extra += "\n\n---\n\n" + memory_context
    return agent.clone(instructions=agent.instructions + "\n\n---\n\n" + extra)


async def run_agent(
    agent: Agent,
    messages: list[dict],
    memory_context: str = "",
    max_turns: int = 10,
) -> AgentRunResult:
    """Run an agent turn and return the full response with metadata."""
    input_items = _prepare_input(messages)

    logger.info("─── Agent '%s' — %d messages ───", agent.name, len(input_items))
    for i, msg in enumerate(input_items):
        content = msg["content"]
        preview = (
            " ".join(p.get("text", "[image]") for p in content if isinstance(p, dict))
            if isinstance(content, list)
            else str(content)
        )
        logger.info("  [%d] %s: %s", i, msg["role"].upper(), preview[:40])
    if memory_context:
        logger.info("  + memory context: %d chars", len(memory_context))

    try:
        result = await Runner.run(
            starting_agent=_inject_context(agent, memory_context),
            input=input_items,
            run_config=_RUN_CONFIG,
            max_turns=max_turns,
        )
    except Exception as exc:
        logger.exception("Runner.run failed for agent '%s': %s", agent.name, exc)
        raise RuntimeError(f"Agent run failed: {exc}") from exc

    tools_used, agents_seen = extract_run_metadata(result.new_items, agent.name)

    response = unwrap_handle_turn(result.final_output or "")
    if not response:
        response = extract_last_tool_output(result.new_items)

    logger.info(
        "Run complete — agents=%s tools=%s response_len=%d",
        agents_seen, tools_used, len(response),
    )
    return AgentRunResult(response=response, tools_used=tools_used, agents_trace=agents_seen)


async def run_agent_streamed(
    agent: Agent,
    messages: list[dict],
    memory_context: str = "",
    max_turns: int = 10,
) -> AsyncIterator[dict[str, Any]]:
    """Run an agent turn in streaming mode, yielding SSE-compatible event dicts.

    Events: token | tool_call | agent_handoff | done | error
    """
    input_items = _prepare_input(messages)
    logger.info("─── Agent '%s' STREAMED — %d messages ───", agent.name, len(input_items))

    tools_used: list[str] = []
    agents_seen: list[str] = [agent.name]
    full_response = ""

    try:
        result = Runner.run_streamed(
            starting_agent=_inject_context(agent, memory_context),
            input=input_items,
            run_config=_RUN_CONFIG,
            max_turns=max_turns,
        )

        async for event in result.stream_events():
            full_response, to_yield = process_stream_event(
                event, full_response, tools_used, agents_seen
            )
            for sse in to_yield:
                yield sse

        # No text streamed — try final_output then last tool output
        if not full_response:
            final = getattr(result, "final_output", None)
            if final:
                full_response = unwrap_handle_turn(str(final))
                yield {"event": "token", "data": {"delta": full_response}}
            if not full_response:
                fallback = extract_last_tool_output(getattr(result, "new_items", []))
                if fallback:
                    full_response = fallback
                    yield {"event": "token", "data": {"delta": full_response}}

    except Exception as exc:
        logger.exception("Streamed run failed for agent '%s': %s", agent.name, exc)
        yield {"event": "error", "data": {"message": str(exc)}}
        return

    logger.info(
        "Streamed run complete — agents=%s tools=%s response_len=%d",
        agents_seen, tools_used, len(full_response),
    )
    yield {
        "event": "done",
        "data": {
            "response": full_response,
            "tools_used": tools_used,
            "agents_trace": agents_seen,
        },
    }
