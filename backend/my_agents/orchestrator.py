from __future__ import annotations

from agents import Agent, handoff

from my_agents.notes_agent import get_notes_agent
from my_agents.slides_agent import get_slides_agent
from helpers.core.config_loader import load_config
from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from tools.memory_tools import forget_memory, prune_memory, store_memory

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
            tools=[store_memory, forget_memory, prune_memory],
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
            ],
        )
    return _orchestrator
