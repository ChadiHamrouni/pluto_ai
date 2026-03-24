from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from helpers.agents.command_parser import parse_command
from helpers.agents.compactor import compact_history
from helpers.agents.ollama_client import get_openai_client
from helpers.agents.prompt_utils import format_chat_history
from helpers.agents.runner import run_agent, run_agent_streamed
from helpers.agents.token_counter import needs_compaction
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.calendar import get_db_path as get_cal_db_path
from helpers.tools.calendar import upcoming_events
from models.results import HandlerResult
from my_agents.calendar_agent import get_calendar_agent
from my_agents.notes_agent import get_notes_agent
from my_agents.orchestrator import get_orchestrator
from my_agents.research_agent import get_research_agent
from my_agents.slides_agent import get_slides_agent

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
    "note": get_notes_agent,
    "slides": get_slides_agent,
    "research": get_research_agent,
    "calendar": get_calendar_agent,
    # memory/forget: still handled by orchestrator (it calls store_memory /
    # forget_memory tools), but they are recognised intents — the content
    # reaching the orchestrator has the slash token stripped.
    "memory": get_orchestrator,
    "forget": get_orchestrator,
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

    window = load_config().get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2) :]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    memory_context = ""
    if parsed.intent is None:
        # Orchestrator path — inject proactive calendar context
        cal_ctx = _calendar_context()
        if cal_ctx:
            memory_context = cal_ctx
    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        from handlers.file_handler import _ocr_image_glm

        cfg = load_config()
        ollama_base = cfg.get("ollama", {}).get("base_url", "http://localhost:11434")
        ocr_model = cfg.get("pdf", {}).get("ocr_model", "glm-ocr")
        extracted = _ocr_image_glm(image_path, ollama_base, ocr_model)
        logger.info("Attaching image %s (%d bytes), OCR: %d chars",
                     image_path.name, image_path.stat().st_size, len(extracted))
        if extracted:
            user_content = f"{content or message}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{extracted}"
        else:
            user_content = content or message
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    # Compact history if approaching context window limit
    if needs_compaction(messages):
        config = load_config()
        model = config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    result = await run_agent(agent, messages, memory_context=memory_context,
                             max_turns=15 if agent.name == "ResearchAgent" else 10)
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

    window = load_config().get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2) :]

    memory_context = ""
    if parsed.intent is None:
        cal_ctx = _calendar_context()
        if cal_ctx:
            memory_context = cal_ctx
    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        from handlers.file_handler import _ocr_image_glm

        cfg = load_config()
        ollama_base = cfg.get("ollama", {}).get("base_url", "http://localhost:11434")
        ocr_model = cfg.get("pdf", {}).get("ocr_model", "glm-ocr")
        extracted = _ocr_image_glm(image_path, ollama_base, ocr_model)
        logger.info("Attaching image %s (%d bytes), OCR: %d chars",
                     image_path.name, image_path.stat().st_size, len(extracted))
        if extracted:
            user_content = f"{content or message}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{extracted}"
        else:
            user_content = content or message
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    # Compact history if approaching context window limit
    if needs_compaction(messages):
        config = load_config()
        model = config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        messages = await compact_history(messages, get_openai_client(), model)

    max_turns = 15 if agent.name == "ResearchAgent" else 10
    async for event in run_agent_streamed(
        agent, messages, memory_context=memory_context, max_turns=max_turns,
    ):
        yield event
