from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import Agent, Runner, RunConfig
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)

from helpers.agents.guardrails import get_output_guardrails
from helpers.core.logger import get_logger
from models.results import AgentRunResult

logger = get_logger(__name__)

_AGENT_TIMEOUT = 120  # seconds


async def run_agent(
    agent: Agent,
    messages: list[dict],
    memory_context: str = "",
) -> AgentRunResult:
    """
    Run an agent turn using the OpenAI Agents SDK Runner.

    Handoffs, tool calls, and multi-agent routing are all handled by the SDK.

    Args:
        agent:          The starting agent (Orchestrator or a sub-agent).
        messages:       Conversation history as role/content dicts. The last
                        entry must be the user turn. System messages are
                        ignored — agent.instructions is used instead.
        memory_context: Optional memory block to append to the orchestrator's
                        instructions for this turn only.

    Returns:
        response_text — final text reply to show the user
        tools_used    — names of every tool called across all agents
        agents_trace  — ordered list of agent names that ran
    """
    run_config = RunConfig(
        tracing_disabled=True,
        output_guardrails=get_output_guardrails(),
    )

    # Build conversation input (user + assistant turns only — SDK handles system via instructions)
    input_items: list = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]
    if not input_items:
        input_items = [{"role": "user", "content": ""}]

    # Log full conversation context being passed to the agent
    logger.info("─── Agent '%s' — %d messages ───", agent.name, len(input_items))
    for i, msg in enumerate(input_items):
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            # Multimodal content (images etc.)
            text_parts = [p.get("text", "[image]") for p in content if isinstance(p, dict)]
            preview = " ".join(text_parts)[:200]
        else:
            preview = str(content)[:200]
        logger.info("  [%d] %s: %s", i, role.upper(), preview)
    if memory_context:
        logger.info("  + memory context: %d chars", len(memory_context))
    logger.info("─── end context ───")

    # Inject memory context into orchestrator instructions for this turn only
    # by cloning the agent with updated instructions (does not mutate the singleton)
    run_agent_instance = agent
    if memory_context and agent.name == "Orchestrator":
        run_agent_instance = agent.clone(
            instructions=agent.instructions + "\n\n" + memory_context
        )

    try:
        result = await Runner.run(
            starting_agent=run_agent_instance,
            input=input_items,
            run_config=run_config,
        )
    except Exception as exc:
        logger.exception("Runner.run failed for agent '%s': %s", agent.name, exc)
        raise RuntimeError(f"Agent run failed: {exc}") from exc

    # Extract tools used and agents trace from RunResult.new_items
    tools_used: list[str] = []
    agents_seen: list[str] = []

    for item in (result.new_items or []):
        agent_name = getattr(getattr(item, "agent", None), "name", None)
        if agent_name and agent_name not in agents_seen:
            agents_seen.append(agent_name)
        if isinstance(item, ToolCallItem):
            # raw_item is the underlying API response object
            raw = getattr(item, "raw_item", None)
            name = (
                getattr(getattr(raw, "function", None), "name", None)
                or getattr(raw, "name", None)
                or getattr(item, "name", None)
            )
            if name and name not in tools_used:
                tools_used.append(name)

    logger.debug("new_items types: %s", [type(i).__name__ for i in (result.new_items or [])])

    if not agents_seen:
        agents_seen = [agent.name]

    response = result.final_output or ""

    # If the final agent called a tool and returned no text, fall back to the
    # last tool output as the response (e.g. generate_slides returns a file path).
    if not response:
        for item in reversed(result.new_items or []):
            if isinstance(item, ToolCallOutputItem):
                raw_output = getattr(item, "output", None) or getattr(getattr(item, "raw_item", None), "output", None)
                if raw_output:
                    response = str(raw_output)
                    break

    logger.info(
        "Run complete — agents=%s tools=%s response_len=%d",
        agents_seen, tools_used, len(response),
    )
    return AgentRunResult(response=response, tools_used=tools_used, agents_trace=agents_seen)


async def run_agent_streamed(
    agent: Agent,
    messages: list[dict],
    memory_context: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """
    Run an agent turn in streaming mode, yielding SSE-compatible event dicts.

    Events yielded:
        {"event": "token",          "data": {"delta": "..."}}
        {"event": "tool_call",      "data": {"tool": "...", "arguments": "..."}}
        {"event": "agent_handoff",  "data": {"agent": "..."}}
        {"event": "done",           "data": {"tools_used": [...], "agents_trace": [...], "response": "..."}}
        {"event": "error",          "data": {"message": "..."}}
    """
    run_config = RunConfig(
        tracing_disabled=True,
        output_guardrails=get_output_guardrails(),
    )

    input_items: list = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]
    if not input_items:
        input_items = [{"role": "user", "content": ""}]

    logger.info("─── Agent '%s' STREAMED — %d messages ───", agent.name, len(input_items))

    run_agent_instance = agent
    if memory_context and agent.name == "Orchestrator":
        run_agent_instance = agent.clone(
            instructions=agent.instructions + "\n\n" + memory_context
        )

    tools_used: list[str] = []
    agents_seen: list[str] = [agent.name]
    full_response = ""

    try:
        result = Runner.run_streamed(
            starting_agent=run_agent_instance,
            input=input_items,
            run_config=run_config,
        )

        async for event in result.stream_events():
            # Text delta — the main content tokens
            if isinstance(event, RawResponsesStreamEvent):
                raw_type = getattr(event.data, "type", "")
                if raw_type == "response.output_text.delta":
                    delta = getattr(event.data, "delta", "")
                    if delta:
                        full_response += delta
                        yield {"event": "token", "data": {"delta": delta}}

            # Agent handoffs and tool calls
            elif isinstance(event, RunItemStreamEvent):
                if event.name == "tool_called":
                    raw = getattr(event.item, "raw_item", None)
                    name = (
                        getattr(getattr(raw, "function", None), "name", None)
                        or getattr(raw, "name", None)
                        or getattr(event.item, "name", None)
                    )
                    arguments = getattr(getattr(raw, "function", None), "arguments", None) or ""
                    if name and name not in tools_used:
                        tools_used.append(name)
                    yield {"event": "tool_call", "data": {"tool": name or "unknown", "arguments": arguments}}

                elif event.name in ("handoff_requested", "handoff_occured"):
                    new_agent_name = getattr(
                        getattr(event.item, "target_agent", None), "name",
                        getattr(getattr(event.item, "agent", None), "name", "unknown"),
                    )
                    if new_agent_name and new_agent_name not in agents_seen:
                        agents_seen.append(new_agent_name)
                    yield {"event": "agent_handoff", "data": {"agent": new_agent_name}}

            elif isinstance(event, AgentUpdatedStreamEvent):
                new_name = event.new_agent.name
                if new_name and new_name not in agents_seen:
                    agents_seen.append(new_name)

        # If no text was streamed, check final output
        if not full_response:
            final = getattr(result, "final_output", None)
            if final:
                full_response = str(final)
                yield {"event": "token", "data": {"delta": full_response}}

            # Fallback: last tool output
            if not full_response:
                for item in reversed(getattr(result, "new_items", []) or []):
                    if isinstance(item, ToolCallOutputItem):
                        raw_output = getattr(item, "output", None) or getattr(
                            getattr(item, "raw_item", None), "output", None
                        )
                        if raw_output:
                            full_response = str(raw_output)
                            yield {"event": "token", "data": {"delta": full_response}}
                            break

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
