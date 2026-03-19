from __future__ import annotations

from agents import Agent

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config

_planner: Agent | None = None


def get_planner_agent() -> Agent:
    global _planner
    if _planner is None:
        cfg = load_config()
        model_name = cfg.get("autonomous", {}).get("model", cfg["orchestrator"]["model"])
        _planner = Agent(
            name="Planner",
            model=get_model(model_name),
            instructions=load_instructions("planner"),
            tools=[],  # Pure reasoning — no tools
        )
    return _planner
