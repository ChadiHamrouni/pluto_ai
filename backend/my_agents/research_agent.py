from __future__ import annotations

from agents import Agent

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.research_tools import fetch_page, take_research_note
from tools.web_search import web_search

_research_agent: Agent | None = None


def reset_research_agent() -> None:
    global _research_agent
    _research_agent = None


def get_research_agent() -> Agent:
    """
    Return the research agent singleton, creating it on first call.

    The research agent performs multi-step web browsing: search, read
    full pages, take notes, and synthesize findings with citations.
    """
    global _research_agent
    if _research_agent is not None:
        return _research_agent

    config = load_config()
    # Use orchestrator model by default (configurable via "research_agent" key)
    research_cfg = config.get("research_agent", config["orchestrator"])

    _research_agent = Agent(
        name="ResearchAgent",
        model=get_model(research_cfg["model"]),
        instructions=load_instructions("research_agent"),
        tools=[web_search, fetch_page, take_research_note],
    )

    return _research_agent
