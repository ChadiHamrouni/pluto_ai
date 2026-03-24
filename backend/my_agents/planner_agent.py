from __future__ import annotations

from agents import Agent

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from models.plan import PlanOutput, StepItem  # noqa: F401 — re-exported for SDK output_type

_planner: Agent | None = None


def get_planner_agent() -> Agent[PlanOutput]:
    global _planner
    if _planner is None:
        cfg = load_config()
        model_name = cfg.get("autonomous", {}).get("planner_model", cfg["orchestrator"]["model"])
        _planner = Agent(
            name="Planner",
            model=get_model(model_name),
            instructions=load_instructions("autonomous/planner"),
            output_type=PlanOutput,
            tools=[],
        )
    return _planner


def reset_planner_agent() -> None:
    global _planner
    _planner = None
