from __future__ import annotations

from agents import Agent, ModelSettings
from tools.calendar import cancel_event, list_events, schedule_event, upcoming_events
from tools.notes import create_note, get_note, list_notes
from tools.slides import draft_slides, render_slides

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.web_search import web_search

_single_agent: Agent | None = None


def reset_single_agent() -> None:
    global _single_agent
    _single_agent = None


def get_single_agent(model: str | None = None) -> Agent:
    """
    Return the single-agent singleton, creating it on first call.

    This is the control condition for the multi-agent ablation (Ablation G).
    It has the same persona and domain knowledge as the full multi-agent system
    but all tools are handled by one agent with no handoffs whatsoever.
    The model defaults to the orchestrator model from config, but can be
    overridden to sweep across models in Ablation C.
    """
    global _single_agent
    if _single_agent is not None and model is None:
        return _single_agent

    cfg = load_config()["orchestrator"]
    model_name = model or cfg["model"]

    agent = Agent(
        name="SingleAgent",
        model=get_model(model_name),
        instructions=load_instructions("agents/single_agent"),
        tools=[
            store_memory, forget_memory, prune_memory,
            web_search,
            create_note, list_notes, get_note,
            draft_slides, render_slides,
            schedule_event, list_events, cancel_event, upcoming_events,
        ],
        model_settings=ModelSettings(
            temperature=cfg.get("temperature", 0.0),
            tool_choice="required",
        ),
    )

    if model is None:
        _single_agent = agent
    return agent
