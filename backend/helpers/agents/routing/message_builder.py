"""Shared message-preparation logic for text handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from helpers.agents.execution.ollama_client import get_openai_client
from helpers.agents.routing.command_parser import parse_command
from helpers.agents.routing.prompt_utils import format_chat_history
from helpers.agents.session.compactor import compact_history
from helpers.agents.session.token_counter import needs_compaction
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.calendar import get_db_path as get_cal_db_path
from helpers.tools.calendar import upcoming_events
from helpers.tools.file_parser import ocr_image

logger = get_logger(__name__)


def _calendar_context() -> str:
    """Return a concise upcoming-events blurb for injection into the prompt."""
    try:
        events = upcoming_events(get_cal_db_path(), hours=24)
        if not events:
            return ""
        lines = ["## Upcoming events (next 24h)"]
        for ev in events:
            end = f" → {ev['end_time']}" if ev.get("end_time") else ""
            lines.append(f"- [{ev['id']}] {ev['title']} at {ev['start_time']}{end}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Calendar context skipped: %s", exc)
        return ""


async def build_messages(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> tuple[Any, list[dict[str, Any]], str]:
    """Parse the message, select a tool-scoped agent, build the message list, and compact.

    Slash commands are resolved to both an intent hint and a tool group so the
    agent cloned by get_agent_for_intent() only sees the tools relevant to this
    turn — typically 3–8 instead of all 29. This is the primary accuracy and
    latency lever for a small local model.

    Returns:
        (agent, messages, memory_context)
    """
    from agent.single import get_agent_for_intent

    parsed = parse_command(message)

    # Prepend [intent] hint so the agent knows which domain to focus on.
    if parsed.intent and parsed.content:
        content = f"[{parsed.intent}] {parsed.content}"
    elif parsed.intent and not parsed.content:
        # Bare command with no body (e.g. just "/dashboard") — intent is the message.
        content = parsed.intent
    else:
        content = message

    # Select the scoped agent for this intent (falls back to "core" tool group).
    agent = get_agent_for_intent(intent=parsed.intent, tool_group=parsed.tool_group)
    logger.info(
        "Routing to %s | intent=%s | tool_group=%s | tools=%d",
        agent.name,
        parsed.intent or "none",
        parsed.tool_group or "core",
        len(agent.tools),
    )

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    # Calendar context is injected as memory_context (appended as a system
    # message in runner.py, after the static instructions prefix, so it does
    # not invalidate the KV cache on the stable instructions prefix).
    memory_context = _calendar_context()

    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        extracted = ocr_image(image_path)
        logger.info(
            "Attaching image %s (%d bytes), OCR: %d chars",
            image_path.name,
            image_path.stat().st_size,
            len(extracted),
        )
        user_content = (
            f"{content or message}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{extracted}"
            if extracted
            else content or message
        )
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    if needs_compaction(messages):
        model = config.get("compactor", {}).get("model") or config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    return agent, messages, memory_context
