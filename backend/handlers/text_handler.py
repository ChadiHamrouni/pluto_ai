from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from helpers.agents.execution.runner import run_agent, run_agent_streamed
from helpers.agents.routing.message_builder import build_messages
from helpers.core.logger import get_logger
from models.results import HandlerResult

logger = get_logger(__name__)


async def text_handler(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
) -> HandlerResult:
    t0 = time.perf_counter()
    agent, messages, memory_context = await build_messages(message, history, image_path)
    max_turns = 15 if agent.name == "ResearchAgent" else 10
    result = await run_agent(agent, messages, memory_context=memory_context, max_turns=max_turns)
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
    """Streaming variant — yields SSE event dicts."""
    agent, messages, memory_context = await build_messages(message, history, image_path)
    max_turns = 15 if agent.name == "ResearchAgent" else 10
    async for event in run_agent_streamed(
        agent, messages, memory_context=memory_context, max_turns=max_turns
    ):
        yield event
