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
    """Return a concise upcoming-events blurb for injection into the orchestrator prompt."""
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
    """Parse the message, strip any slash-command prefix, build the message list, and compact.

    Returns:
        (agent, messages, memory_context)
    """
    from agent.single import get_single_agent

    # Slash commands: strip the token but prepend the intent as a hint so the
    # agent knows which tool domain to focus on (e.g. "[note] buy groceries").
    parsed = parse_command(message)
    if parsed.intent and parsed.content:
        content = f"[{parsed.intent}] {parsed.content}"
    elif parsed.intent and not parsed.content:
        # bare command with no body (e.g. just "/dashboard") — keep intent as full message
        content = parsed.intent
    else:
        content = message

    agent = get_single_agent()
    logger.info("Routing to %s (single-agent mode)", agent.name)

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    memory_context = ""
    cal_ctx = _calendar_context()
    if cal_ctx:
        memory_context = cal_ctx

    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        extracted = ocr_image(image_path)
        logger.info(
            "Attaching image %s (%d bytes), OCR: %d chars",
            image_path.name,
            image_path.stat().st_size,
            len(extracted),
        )
        if extracted:
            user_content = f"{content or message}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{extracted}"
        else:
            user_content = content or message
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    if needs_compaction(messages):
        model = config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    return agent, messages, memory_context
