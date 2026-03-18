from __future__ import annotations

from agents import Agent

from helpers.core.config_loader import load_config
from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from tools.slides_tools import generate_slides

_slides_agent: Agent | None = None

def get_slides_agent() -> Agent:
    """
    Return the slides agent singleton, creating it on first call.

    The slides agent converts the user's ideas or structured content into
    Marp-compatible markdown and generates a PDF presentation.
    """
    global _slides_agent
    if _slides_agent is not None:
        return _slides_agent

    slides_cfg = load_config()["slides_agent"]

    _slides_agent = Agent(
        name="SlidesAgent",
        model=get_model(slides_cfg["model"]),
        instructions=load_instructions("slides_agent"),
        tools=[generate_slides],
    )

    return _slides_agent
