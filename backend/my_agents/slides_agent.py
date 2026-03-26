from __future__ import annotations

from agents import Agent, ModelSettings

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from backend.tools.slides import draft_slides, render_slides
from tools.web_search import web_search

_slides_agent: Agent | None = None


def reset_slides_agent() -> None:
    global _slides_agent
    _slides_agent = None


def get_slides_agent() -> Agent:
    """
    Return the slides agent singleton, creating it on first call.

    The slides agent researches topics, drafts validated outlines,
    and renders them into Marp PDF presentations.
    """
    global _slides_agent
    if _slides_agent is not None:
        return _slides_agent

    slides_cfg = load_config()["slides_agent"]

    _slides_agent = Agent(
        name="SlidesAgent",
        model=get_model(slides_cfg["model"]),
        instructions=load_instructions("agents/slides_agent"),
        tools=[web_search, draft_slides, render_slides],
        model_settings=ModelSettings(
            temperature=slides_cfg.get("temperature", 0.0),
            tool_choice=slides_cfg.get("tool_choice", "required"),
        ),
    )

    return _slides_agent
