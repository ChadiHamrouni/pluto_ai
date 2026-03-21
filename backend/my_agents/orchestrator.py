from __future__ import annotations

from agents import Agent, handoff

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from my_agents.calendar_agent import get_calendar_agent
from my_agents.notes_agent import get_notes_agent
from my_agents.research_agent import get_research_agent
from my_agents.slides_agent import get_slides_agent
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.web_search import web_search

_orchestrator: Agent | None = None


def reset_orchestrator() -> None:
    global _orchestrator
    _orchestrator = None


def get_orchestrator() -> Agent:
    global _orchestrator
    if _orchestrator is None:
        cfg = load_config()["orchestrator"]
        _orchestrator = Agent(
            name="Orchestrator",
            model=get_model(cfg["model"]),
            instructions=load_instructions("orchestrator"),
            tools=[store_memory, forget_memory, prune_memory, web_search],
            handoffs=[
                handoff(
                    get_notes_agent(),
                    tool_description_override=(
                        "Transfer to NotesAgent when the user wants to create, save, "
                        "write, list, or read a note. Examples: 'take a note about ...', "
                        "'save this as a note', 'show my notes', 'list my research notes'."
                    ),
                ),
                handoff(
                    get_slides_agent(),
                    tool_description_override=(
                        "Transfer to SlidesAgent when the user wants a presentation, "
                        "slide deck, or slides generated as a PDF. Examples: 'make me a "
                        "presentation about ...', 'create slides on ...', 'generate a "
                        "2-page slide deck about ...'."
                    ),
                ),
                handoff(
                    get_research_agent(),
                    tool_description_override=(
                        "Transfer to ResearchAgent when the user wants in-depth research "
                        "on a topic. The research agent searches multiple sources, reads "
                        "full pages, and synthesises findings with citations. Examples: "
                        "'research ...', 'find out about ...', 'what's the latest on ...', "
                        "'investigate ...', 'compare X vs Y'."
                    ),
                ),
                handoff(
                    get_calendar_agent(),
                    tool_description_override=(
                        "Transfer to CalendarAgent when the user wants to schedule, create, "
                        "list, view, or cancel calendar events or appointments. Examples: "
                        "'schedule a meeting tomorrow at 3pm', 'what do I have this week', "
                        "'add an event for Friday', 'cancel my dentist appointment', "
                        "'remind me about the call on Monday'."
                    ),
                ),
            ],
        )
    return _orchestrator
