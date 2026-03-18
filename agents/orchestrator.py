from __future__ import annotations

import json
import time

from agents import Agent, Runner, handoff

from agents.notes_agent import get_notes_agent
from agents.slides_agent import get_slides_agent
from helpers.command_parser import parse_command
from helpers.config_loader import load_config
from helpers.instructions_loader import load_instructions
from helpers.ollama_client import get_model
from helpers.logger import get_logger
from helpers.prompt_utils import build_system_prompt, format_chat_history, format_memory_context
from helpers.tracer import print_trace
from helpers.memory import search_memories
from tools.memory_tools import prune_memory, search_memory, store_memory

logger = get_logger(__name__)

_orchestrator: Agent | None = None


def _build_orchestrator() -> Agent:
    orch_cfg = load_config()["orchestrator"]

    instructions = load_instructions("orchestrator")

    return Agent(
        name="Orchestrator",
        model=get_model(orch_cfg["model"]),
        instructions=instructions,
        tools=[store_memory, search_memory, prune_memory],
        handoffs=[
            handoff(get_notes_agent()),
            handoff(get_slides_agent()),
        ],
    )


def get_orchestrator() -> Agent:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = _build_orchestrator()
    return _orchestrator


async def run_orchestrator(message: str, history: list) -> str:
    config = load_config()

    # Parse optional slash command — deterministic routing if present
    parsed = parse_command(message)

    _AGENT_MAP = {
        "note":   get_notes_agent,
        "slides": get_slides_agent,
    }

    if parsed.intent in _AGENT_MAP:
        # Hard-route: skip orchestrator LLM routing entirely
        starting_agent = _AGENT_MAP[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command", starting_agent.name)
    else:
        # Normal path: orchestrator decides
        starting_agent = get_orchestrator()
        content = message  # keep original (may include unknown /cmd or no cmd)

    # Pre-fetch relevant memories and inject as system context
    t_mem = time.perf_counter()
    try:
        memory_json = search_memories(query=content or message, top_k=config["rag"]["top_k"])
        memory_entries = json.loads(memory_json) if memory_json else []
    except Exception as exc:
        logger.warning("Memory pre-fetch skipped: %s", exc)
        memory_entries = []
    logger.debug("Memory fetch: %.2fs", time.perf_counter() - t_mem)

    memory_context = format_memory_context(memory_entries)
    formatted_history = format_chat_history(history)

    messages: list[dict[str, str]] = []
    if memory_context:
        messages.append({
            "role": "system",
            "content": build_system_prompt(
                "You are a helpful personal AI assistant.", memory_context
            ),
        })

    messages.extend(formatted_history)
    messages.append({"role": "user", "content": content or message})

    try:
        t_run = time.perf_counter()
        result = await Runner.run(starting_agent=starting_agent, input=messages)
        logger.debug("Agent run:    %.2fs", time.perf_counter() - t_run)
        print_trace(result, source=starting_agent.name)
        response_text = result.final_output or ""
        logger.info("Response from %s (memory_entries=%d)", starting_agent.name, len(memory_entries))
        return response_text
    except Exception as exc:
        logger.error("Orchestrator run failed: %s", exc)
        raise
