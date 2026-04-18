"""Utilities for extracting structured data from OpenAI Agents SDK stream events."""

from __future__ import annotations

import json
from typing import Any

from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)

from helpers.core.logger import get_logger

logger = get_logger(__name__)


def unwrap_handle_turn(text: str) -> str:
    """Some open-source models emit handle_turn as text JSON instead of a native
    function call. Extract the inner text so the user never sees raw JSON."""
    t = text.strip()
    if not t.startswith("{"):
        return text
    try:
        obj = json.loads(t)
        if obj.get("name") == "handle_turn":
            return obj.get("parameters", {}).get("text", text)
    except (json.JSONDecodeError, AttributeError):
        pass
    return text


def extract_tool_name(item: ToolCallItem) -> str | None:
    """Return the tool name from a ToolCallItem, or None."""
    raw = getattr(item, "raw_item", None)
    return (
        getattr(getattr(raw, "function", None), "name", None)
        or getattr(raw, "name", None)
        or getattr(item, "name", None)
    )


def extract_tool_arguments(item: ToolCallItem) -> str:
    """Return the raw arguments string from a ToolCallItem."""
    raw = getattr(item, "raw_item", None)
    return (
        getattr(getattr(raw, "function", None), "arguments", None)
        or getattr(raw, "arguments", None)
        or getattr(item, "arguments", None)
        or ""
    )


def extract_last_tool_output(new_items: list) -> str:
    """Return the output of the last ToolCallOutputItem, or empty string."""
    for item in reversed(new_items or []):
        if isinstance(item, ToolCallOutputItem):
            raw_output = getattr(item, "output", None) or getattr(
                getattr(item, "raw_item", None), "output", None
            )
            if raw_output:
                return str(raw_output)
    return ""


def extract_run_metadata(new_items: list, fallback_agent: str) -> tuple[list[str], list[str]]:
    """Return (tools_used, agents_trace) from a completed run's new_items."""
    tools_used: list[str] = []
    agents_seen: list[str] = []
    for item in new_items or []:
        agent_name = getattr(getattr(item, "agent", None), "name", None)
        if agent_name and agent_name not in agents_seen:
            agents_seen.append(agent_name)
        if isinstance(item, ToolCallItem):
            name = extract_tool_name(item)
            if name and name not in tools_used:
                tools_used.append(name)
    if not agents_seen:
        agents_seen = [fallback_agent]
    return tools_used, agents_seen


def compact_tool_output(tool_name: str, output: str) -> str:
    """Return a one-line summary of a tool output for use in compacted history.

    Recognises known batch/CRUD result shapes and templating them into a short
    summary. Full output is still yielded as SSE for the frontend; only the
    version stored in intermediate conversation context is compacted.
    """
    if not output or len(output) < 120:
        return output

    name = (tool_name or "").lower()

    # Batch creation tools — extract Created/skipped count from first line
    if name in ("schedule_events", "create_reminders", "create_tasks", "create_notes"):
        first_line = output.splitlines()[0]
        return first_line  # already a one-liner like "Created 5 event(s), skipped 0 duplicate(s)."

    # Single-create tools — already short confirmations, but strip trailing JSON
    if name in ("schedule_event", "set_reminder", "create_task", "create_note"):
        return output.splitlines()[0]

    # List tools — summarise count
    if name in ("list_events", "list_tasks", "list_reminders", "list_notes"):
        try:
            items = json.loads(output)
            if isinstance(items, list):
                return f"[{name}] returned {len(items)} item(s)."
        except (json.JSONDecodeError, ValueError):
            pass

    # Budget summary — keep first 2 lines
    if "budget" in name or "transaction" in name:
        lines = output.splitlines()
        return " | ".join(lines[:2])

    # Generic fallback — first 100 chars
    return output[:100] + ("…" if len(output) > 100 else "")


def process_stream_event(
    event: Any,
    full_response: str,
    tools_used: list[str],
    agents_seen: list[str],
) -> tuple[str, list[dict]]:
    """Process one stream event, updating state in-place and returning events to yield.

    Returns the updated full_response and a list of SSE event dicts to yield.
    """
    to_yield: list[dict] = []

    if isinstance(event, RawResponsesStreamEvent):
        raw_type = getattr(event.data, "type", "")

        if raw_type == "response.output_text.delta":
            delta = getattr(event.data, "delta", "")
            if delta:
                full_response += delta
                if not full_response.lstrip().startswith("{"):
                    to_yield.append({"event": "token", "data": {"delta": delta}})

        elif raw_type == "response.output_text.done":
            unwrapped = unwrap_handle_turn(full_response)
            if unwrapped != full_response:
                full_response = unwrapped
                to_yield.append({"event": "token", "data": {"delta": full_response}})

    elif isinstance(event, RunItemStreamEvent):
        if event.name == "tool_called":
            item = event.item
            name = extract_tool_name(item)
            arguments = extract_tool_arguments(item)
            if name and name not in tools_used:
                tools_used.append(name)
            to_yield.append({
                "event": "tool_call",
                "data": {"tool": name or "unknown", "arguments": arguments},
            })

        elif event.name == "tool_output":
            item = event.item
            output = ""
            if isinstance(item, ToolCallOutputItem):
                output = str(getattr(item, "output", None) or "")
            to_yield.append({
                "event": "tool_output",
                "data": {"output": output},
            })

        elif event.name in ("handoff_requested", "handoff_occured"):
            new_name = getattr(
                getattr(event.item, "target_agent", None),
                "name",
                getattr(getattr(event.item, "agent", None), "name", "unknown"),
            )
            if new_name and new_name not in agents_seen:
                agents_seen.append(new_name)
            to_yield.append({"event": "agent_handoff", "data": {"agent": new_name}})

    elif isinstance(event, AgentUpdatedStreamEvent):
        new_name = event.new_agent.name
        if new_name and new_name not in agents_seen:
            agents_seen.append(new_name)

    return full_response, to_yield
