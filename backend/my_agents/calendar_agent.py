from __future__ import annotations

from agents import Agent, ModelSettings

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.calendar_tools import cancel_event, list_events, schedule_event, upcoming_events

_calendar_agent: Agent | None = None


def reset_calendar_agent() -> None:
    global _calendar_agent
    _calendar_agent = None


def get_calendar_agent() -> Agent:
    global _calendar_agent
    if _calendar_agent is not None:
        return _calendar_agent

    config = load_config()
    cfg = config.get("calendar_agent", config["orchestrator"])

    _calendar_agent = Agent(
        name="CalendarAgent",
        model=get_model(cfg["model"]),
        instructions=load_instructions("calendar_agent"),
        tools=[schedule_event, list_events, upcoming_events, cancel_event],
        model_settings=ModelSettings(
            temperature=cfg.get("temperature", 0.0),
            tool_choice=cfg.get("tool_choice", "required"),
        ),
    )

    return _calendar_agent
