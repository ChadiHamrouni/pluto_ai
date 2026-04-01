from __future__ import annotations

from agents import Agent, ModelSettings, handoff

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from my_agents.calendar import get_calendar_agent
from my_agents.dashboard import get_dashboard_agent
from my_agents.notes import get_notes_agent
from my_agents.research import get_research_agent
from my_agents.slides import get_slides_agent
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.rag import search_knowledge
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
            instructions=load_instructions("agents/orchestrator"),
            tools=[store_memory, forget_memory, prune_memory, web_search, search_knowledge],
            model_settings=ModelSettings(
                temperature=cfg.get("temperature", 0.0),
                tool_choice=cfg.get("tool_choice", "auto"),
            ),
            handoffs=[
                handoff(
                    get_notes_agent(),
                    tool_description_override=(
                        "Transfer to NotesAgent when the user wants to create, save, "
                        "write, list, or read a note. Do NOT transfer for remembering facts "
                        "— use store_memory for those. "
                        "Examples: 'take a note about ...', "
                        "'save this as a note', 'show my notes'."
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
                        "Transfer to ResearchAgent ONLY when the user "
                        "explicitly asks to 'research', 'investigate', "
                        "'compare', 'analyze', or wants a multi-source "
                        "report with citations. "
                        "Do NOT transfer for simple questions — use "
                        "web_search yourself for those. "
                        "Examples that SHOULD transfer: 'research X', "
                        "'compare X vs Y', 'investigate X'. "
                        "Examples that should NOT transfer: "
                        "'what is X?', 'how does X work?'."
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
                handoff(
                    get_dashboard_agent(),
                    tool_description_override=(
                        "Transfer to DashboardAgent when the user wants to: "
                        "manage tasks or a to-do list ('add a task', 'mark done', 'show kanban'), "
                        "track budget or finances ('I spent X', 'record income', 'show my goals'), "
                        "generate a diagram or chart ('make a flowchart', 'create a mindmap'), "
                        "or sync/update their Obsidian vault ('update dashboard', 'sync vault', "
                        "'generate weekly plan', 'show budget report')."
                    ),
                ),
            ],
        )
    return _orchestrator
