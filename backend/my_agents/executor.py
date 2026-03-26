from __future__ import annotations

from agents import Agent
from tools.calendar import cancel_event, list_events, schedule_event, upcoming_events
from tools.notes import create_note, get_note, list_notes
from tools.slides import draft_slides, render_slides

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.web_search import web_search

_executor: Agent | None = None


def get_executor_agent() -> Agent:
    global _executor
    if _executor is None:
        cfg = load_config()
        model_name = cfg.get("autonomous", {}).get("executor_model", cfg["orchestrator"]["model"])
        _executor = Agent(
            name="Executor",
            model=get_model(model_name),
            instructions=load_instructions("autonomous/executor"),
            tools=[
                web_search,
                store_memory,
                forget_memory,
                prune_memory,
                create_note,
                list_notes,
                get_note,
                draft_slides,
                render_slides,
                schedule_event,
                list_events,
                upcoming_events,
                cancel_event,
            ],
        )
    return _executor


def reset_executor_agent() -> None:
    global _executor
    _executor = None
