from __future__ import annotations

import time

from agents import Agent, Runner, handoff

from agents.notes_agent import get_notes_agent
from agents.slides_agent import get_slides_agent
from helpers.command_parser import parse_command
from helpers.config_loader import load_config
from helpers.instructions_loader import load_instructions
from helpers.logger import get_logger
from helpers.memory import get_db_path, load_all_memories
from helpers.ollama_client import get_model
from helpers.prompt_utils import build_system_prompt, format_chat_history, format_memory_context
from helpers.tracer import print_trace
from tools.memory_tools import forget_memory, prune_memory, store_memory

logger = get_logger(__name__)

_orchestrator: Agent | None = None


def _build_orchestrator() -> Agent:
    orch_cfg = load_config()["orchestrator"]

    return Agent(
        name="Orchestrator",
        model=get_model(orch_cfg["model"]),
        instructions=load_instructions("orchestrator"),
        tools=[store_memory, forget_memory, prune_memory],
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
    # Parse optional slash command — deterministic routing if present
    parsed = parse_command(message)

    _AGENT_MAP = {
        "note":   get_notes_agent,
        "slides": get_slides_agent,
    }

    if parsed.intent in _AGENT_MAP:
        starting_agent = _AGENT_MAP[parsed.intent]()
        content = parsed.content
        logger.info("Hard-routing to %s via slash command", starting_agent.name)
    else:
        starting_agent = get_orchestrator()
        content = message

    # Load all memory facts and inject into system prompt
    t_mem = time.perf_counter()
    try:
        memory_entries = load_all_memories(get_db_path())
    except Exception as exc:
        logger.warning("Memory load skipped: %s", exc)
        memory_entries = []
    logger.debug("Memory load: %.2fs (%d facts)", time.perf_counter() - t_mem, len(memory_entries))

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
        logger.info("Response from %s (facts=%d)", starting_agent.name, len(memory_entries))
        return response_text
    except Exception as exc:
        logger.error("Orchestrator run failed: %s", exc)
        raise
