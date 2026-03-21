from __future__ import annotations

import base64
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from my_agents.orchestrator import get_orchestrator
from my_agents.calendar_agent import get_calendar_agent
from my_agents.notes_agent import get_notes_agent
from my_agents.research_agent import get_research_agent
from my_agents.slides_agent import get_slides_agent
from helpers.agents.command_parser import parse_command
from helpers.agents.compactor import compact_history
from helpers.agents.ollama_client import get_openai_client
from helpers.agents.runner import run_agent, run_agent_streamed
from helpers.agents.prompt_utils import format_chat_history, format_memory_context
from helpers.agents.token_counter import needs_compaction
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.calendar import get_db_path as get_cal_db_path, upcoming_events
from helpers.tools.memory import get_db_path, search_memories
from models.results import HandlerResult

logger = get_logger(__name__)


def _calendar_context() -> str:
    """Return a concise upcoming-events blurb for the orchestrator system prompt."""
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


_COMMAND_AGENTS = {
    "note":     get_notes_agent,
    "slides":   get_slides_agent,
    "research": get_research_agent,
    "calendar": get_calendar_agent,
}


async def text_handler(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> HandlerResult:
    t0 = time.perf_counter()

    parsed = parse_command(message)

    if parsed.intent in _COMMAND_AGENTS:
        agent = _COMMAND_AGENTS[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command", agent.name)
    else:
        agent = get_orchestrator()
        content = message

    top_k = load_config().get("memory", {}).get("search_top_k", 10)
    try:
        memory_entries = search_memories(get_db_path(), query=content or message, top_k=top_k)
    except Exception as exc:
        logger.warning("Memory search skipped: %s", exc)
        memory_entries = []

    window = load_config().get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    memory_context = format_memory_context(memory_entries)
    if parsed.intent is None:
        # Orchestrator path — inject proactive calendar context
        cal_ctx = _calendar_context()
        if cal_ctx:
            memory_context = f"{memory_context}\n\n{cal_ctx}".strip()
    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        user_content = [
            {"type": "text", "text": content or message},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
        logger.info("Attaching image %s (%d bytes)", image_path.name, image_path.stat().st_size)
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    # Compact history if approaching context window limit
    if needs_compaction(messages):
        config = load_config()
        model = config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    result = await run_agent(agent, messages, memory_context=memory_context)
    return HandlerResult(
        response=result.response,
        elapsed=time.perf_counter() - t0,
        tools_used=result.tools_used,
        agents_trace=result.agents_trace,
    )


async def text_handler_streamed(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Streaming variant of text_handler — yields SSE event dicts."""
    parsed = parse_command(message)

    if parsed.intent in _COMMAND_AGENTS:
        agent = _COMMAND_AGENTS[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command (streamed)", agent.name)
    else:
        agent = get_orchestrator()
        content = message

    top_k = load_config().get("memory", {}).get("search_top_k", 10)
    try:
        memory_entries = search_memories(get_db_path(), query=content or message, top_k=top_k)
    except Exception as exc:
        logger.warning("Memory search skipped: %s", exc)
        memory_entries = []

    window = load_config().get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]

    memory_context = format_memory_context(memory_entries)
    if parsed.intent is None:
        cal_ctx = _calendar_context()
        if cal_ctx:
            memory_context = f"{memory_context}\n\n{cal_ctx}".strip()
    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        user_content = [
            {"type": "text", "text": content or message},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    # Compact history if approaching context window limit
    if needs_compaction(messages):
        config = load_config()
        model = config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    async for event in run_agent_streamed(agent, messages, memory_context=memory_context):
        yield event
