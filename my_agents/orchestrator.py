from __future__ import annotations

import json
import time

from agents import Agent, OpenAIChatCompletionsModel, Runner, handoff
from openai import AsyncOpenAI

from my_agents.notes_agent import get_notes_agent
from my_agents.slides_agent import get_slides_agent
from helpers.command_parser import parse_command
from helpers.config_loader import load_config
from helpers.logger import get_logger
from helpers.prompt_utils import build_system_prompt, format_chat_history, format_memory_context
from helpers.tracer import print_trace
from tools.memory_tools import _search_memory_raw, prune_memory, search_memory, store_memory

logger = get_logger(__name__)

_orchestrator: Agent | None = None


def _build_orchestrator() -> Agent:
    config = load_config()
    orch_cfg = config["orchestrator"]

    client = AsyncOpenAI(
        base_url=orch_cfg["base_url"],
        api_key=orch_cfg["api_key"],
    )

    model = OpenAIChatCompletionsModel(
        model=orch_cfg["model"],
        openai_client=client,
    )

    instructions = (
        "You are a personal AI assistant. You help the user with a variety of tasks "
        "by either handling them directly or routing to a specialist agent.\n\n"
        "Specialist agents:\n"
        "- **NotesAgent**: Create, list, and retrieve markdown notes. Hand off when "
        "  the user wants to save, organise, or recall notes.\n"
        "- **SlidesAgent**: Generate PDF slide presentations from markdown or outlines. "
        "  Hand off when the user wants to create a presentation.\n\n"
        "Memory tools (call these yourself — do not hand off for memory):\n"
        "- **store_memory**: After any turn where the user shares something worth "
        "  remembering (a fact, preference, goal, or context), call this silently. "
        "  Choose the most appropriate category: teaching, research, career, personal, ideas.\n"
        "- **search_memory**: Call this when you need to recall something specific "
        "  that is not already in the provided memory context.\n"
        "- **prune_memory**: Call this only when the user explicitly asks to clean up "
        "  or forget old memories.\n\n"
        "Guidelines:\n"
        "- For general conversation and Q&A, answer directly without a handoff.\n"
        "- For ambiguous requests, ask a clarifying question.\n"
        "- Use the memory context in the system prompt to give personalised responses.\n"
        "- Be conservative about what you store — only save genuinely useful facts, "
        "  not every message.\n"
        "- Never mention to the user that you are storing a memory unless they ask."
    )

    return Agent(
        name="Orchestrator",
        model=model,
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
        memory_json = _search_memory_raw(query=content or message, top_k=config["rag"]["top_k"])
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
