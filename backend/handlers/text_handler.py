from __future__ import annotations

import base64
import time
from pathlib import Path

from my_agents.orchestrator import get_orchestrator
from my_agents.notes_agent import get_notes_agent
from my_agents.slides_agent import get_slides_agent
from helpers.agents.command_parser import parse_command
from helpers.agents.compactor import compact_history
from helpers.agents.ollama_client import get_openai_client
from helpers.agents.runner import run_agent
from helpers.agents.prompt_utils import build_system_prompt, format_chat_history, format_memory_context
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.memory import get_db_path, search_memories

logger = get_logger(__name__)

_COMMAND_AGENTS = {
    "note":   get_notes_agent,
    "slides": get_slides_agent,
}


async def text_handler(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> tuple[str, float]:
    t0 = time.perf_counter()

    parsed = parse_command(message)

    if parsed.intent in _COMMAND_AGENTS:
        agent = _COMMAND_AGENTS[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command", agent.name)
    else:
        agent = get_orchestrator()
        content = message

    # Load relevant memory facts via hybrid search (FTS5 + keyword scoring)
    top_k = load_config().get("memory", {}).get("search_top_k", 10)
    try:
        memory_entries = search_memories(get_db_path(), query=content or message, top_k=top_k)
    except Exception as exc:
        logger.warning("Memory search skipped: %s", exc)
        memory_entries = []

    # Rolling window — keep last N turns (pairs), configurable
    window = load_config().get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]  # 2 messages per turn (user + assistant)
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    memory_context = format_memory_context(memory_entries)
    messages: list[dict] = []

    # System prompt — always includes memories regardless of window size
    messages.append({
        "role": "system",
        "content": build_system_prompt("You are a helpful personal AI assistant.", memory_context),
    })

    messages.extend(format_chat_history(windowed_history))

    # Progressive compaction — summarise old messages if approaching context limit
    try:
        cfg = load_config()
        compact_model = cfg.get("orchestrator", {}).get("model", "qwen3.5:2b")
        messages = await compact_history(messages, get_openai_client(), compact_model)
    except Exception as exc:
        logger.warning("Compaction skipped: %s", exc)

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

    response = await run_agent(agent, messages)
    return response, time.perf_counter() - t0
