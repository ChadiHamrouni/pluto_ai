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


def _get_command_agents() -> dict:
    """Return the slash-command → agent-factory mapping (imported lazily to avoid cycles)."""
    from my_agents.calendar import get_calendar_agent
    from my_agents.dashboard import get_dashboard_agent
    from my_agents.notes import get_notes_agent
    from my_agents.orchestrator import get_orchestrator
    from my_agents.research import get_research_agent
    from my_agents.slides import get_slides_agent

    return {
        "note": get_notes_agent,
        "slides": get_slides_agent,
        "research": get_research_agent,
        "calendar": get_calendar_agent,
        "memory": get_orchestrator,
        "forget": get_orchestrator,
        "task": get_dashboard_agent,
        "budget": get_dashboard_agent,
        "diagram": get_dashboard_agent,
        "dashboard": get_dashboard_agent,
    }


async def build_messages(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> tuple[Any, list[dict[str, Any]], str]:
    """Parse the message, select an agent, build the message list, and compact if needed.

    Returns:
        (agent, messages, memory_context)
    """
    from my_agents.orchestrator import get_orchestrator

    command_agents = _get_command_agents()
    parsed = parse_command(message)

    if parsed.intent in command_agents:
        agent = command_agents[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command", agent.name)
    else:
        agent = get_orchestrator()
        content = message

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    memory_context = ""
    if parsed.intent is None:
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
