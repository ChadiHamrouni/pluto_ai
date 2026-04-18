from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from agents import Agent, RunConfig, Runner

from helpers.agents.execution.event_parser import (
    compact_tool_output,
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


def _prepare_input(messages: list[dict], memory_context: str) -> list[dict]:
    """
    Build the final input list for Runner.run().

    Injects date/time context and optional calendar/memory as a leading
    system message — NOT by modifying agent.instructions. This keeps the
    static instructions string byte-identical across turns so Ollama's KV
    cache for the instructions prefix survives between requests.

    Structure:
        [system: context + memory]  ← dynamic, changes per turn
        [user/assistant …]          ← conversation history
        [user: current message]     ← last item
    """
    # Build the dynamic context block (date, time, location, optional memory).
    context_parts = [_build_context_block()]
    if memory_context:
        context_parts.append(memory_context)
    context_message = {"role": "system", "content": "\n\n---\n\n".join(context_parts)}

    # Keep only user/assistant turns from the history — strip any existing
    # system messages (compaction summaries are handled separately).
    conversation = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]

    if not conversation:
        conversation = [{"role": "user", "content": ""}]

    return [context_message] + conversation


async def run_agent(
    agent: Agent,
    messages: list[dict],
    memory_context: str = "",
    max_turns: int = 20,
) -> AgentRunResult:
    """Run an agent turn and return the full response with metadata."""
    input_items = _prepare_input(messages, memory_context)

    logger.info("─── Agent '%s' — %d messages ───", agent.name, len(input_items))
    for i, msg in enumerate(input_items):
        content = msg["content"]
        preview = (
            " ".join(p.get("text", "[image]") for p in content if isinstance(p, dict))
            if isinstance(content, list)
            else str(content)
        )
        logger.info("  [%d] %s: %s", i, msg["role"].upper(), preview[:60])
    if memory_context:
        logger.info("  + memory context: %d chars", len(memory_context))

    try:
        result = await Runner.run(
            starting_agent=agent,
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
    max_turns: int = 20,
) -> AsyncIterator[dict[str, Any]]:
    """Run an agent turn in streaming mode, yielding SSE-compatible event dicts.

    Events: token | tool_call | agent_handoff | done | error
    """
    input_items = _prepare_input(messages, memory_context)
    logger.info("─── Agent '%s' STREAMED — %d messages ───", agent.name, len(input_items))

    tools_used: list[str] = []
    agents_seen: list[str] = [agent.name]
    full_response = ""
    t0 = time.perf_counter()
    turn_start = t0
    turn_num = 0

    try:
        result = Runner.run_streamed(
            starting_agent=agent,
            input=input_items,
            run_config=_RUN_CONFIG,
            max_turns=max_turns,
        )

        last_tool_name: str = ""
        async for event in result.stream_events():
            full_response, to_yield = process_stream_event(
                event, full_response, tools_used, agents_seen
            )
            for sse in to_yield:
                if sse["event"] == "tool_call":
                    elapsed = time.perf_counter() - turn_start
                    turn_num += 1
                    last_tool_name = sse["data"].get("tool", "")
                    logger.info(
                        "  ⏱ Turn %d LLM → tool_call '%s' (%.1fs)",
                        turn_num, last_tool_name, elapsed,
                    )
                elif sse["event"] == "tool_output":
                    tool_elapsed = time.perf_counter() - turn_start
                    logger.info("  ⏱ Turn %d tool executed (%.1fs total)", turn_num, tool_elapsed)
                    turn_start = time.perf_counter()
                    # Compact verbose output before it enters the next-turn context.
                    raw_out = sse["data"].get("output", "")
                    compacted = compact_tool_output(last_tool_name, raw_out)
                    if compacted != raw_out:
                        logger.debug("  Compacted tool output: %d → %d chars", len(raw_out), len(compacted))
                        sse = {**sse, "data": {**sse["data"], "output": compacted}}
                yield sse

        # No text streamed — try final_output then last tool output.
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
        "Streamed run complete — agents=%s tools=%s response_len=%d total=%.1fs turns=%d",
        agents_seen, tools_used, len(full_response), time.perf_counter() - t0, turn_num,
    )
    yield {
        "event": "done",
        "data": {
            "response": full_response,
            "tools_used": tools_used,
            "agents_trace": agents_seen,
        },
    }
