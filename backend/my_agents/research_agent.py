from __future__ import annotations

from agents import Agent, ModelSettings

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.web_search import fetch_page, web_search

_research_agent: Agent | None = None


def reset_research_agent() -> None:
    global _research_agent
    _research_agent = None


def get_research_agent() -> Agent:
    global _research_agent
    if _research_agent is not None:
        return _research_agent

    config = load_config()
    cfg = config.get("research_agent", config["orchestrator"])

    _research_agent = Agent(
        name="ResearchAgent",
        model=get_model(cfg["model"]),
        instructions=load_instructions("agents/research_agent"),
        tools=[web_search, fetch_page],
        model_settings=ModelSettings(
            temperature=cfg.get("temperature", 0.3),
            tool_choice=cfg.get("tool_choice", "required"),
        ),
    )

    return _research_agent
