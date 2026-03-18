from __future__ import annotations

from agents import Agent, Runner

from helpers.agents.tracer import print_trace
from helpers.core.logger import get_logger

logger = get_logger(__name__)


async def run_agent(agent: Agent, messages: list[dict]) -> str:
    result = await Runner.run(starting_agent=agent, input=messages)
    print_trace(result, source=agent.name)
    return result.final_output or ""
