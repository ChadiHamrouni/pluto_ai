from __future__ import annotations

from agents import Agent, handoff

from my_agents.notes_agent import get_notes_agent
from my_agents.slides_agent import get_slides_agent
from helpers.core.config_loader import load_config
from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from tools.memory_tools import forget_memory, prune_memory, store_memory

_orchestrator: Agent | None = None


def get_orchestrator() -> Agent:
    global _orchestrator
    if _orchestrator is None:
        cfg = load_config()["orchestrator"]
        _orchestrator = Agent(
            name="Orchestrator",
            model=get_model(cfg["model"]),
            instructions=load_instructions("orchestrator"),
            tools=[store_memory, forget_memory, prune_memory],
            handoffs=[
                handoff(get_notes_agent()),
                handoff(get_slides_agent()),
            ],
        )
    return _orchestrator
