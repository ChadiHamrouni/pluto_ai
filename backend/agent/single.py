from __future__ import annotations

from agents import Agent, ModelSettings

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config

from tools.budget import (
    add_transaction,
    budget_summary,
    create_savings_goal,
    delete_savings_goal,
    delete_transaction,
    list_savings_goals,
    list_transactions,
)

from tools.calculator import calculate
from tools.calendar import cancel_event, list_events, schedule_event, upcoming_events
from tools.diagrams import generate_diagram
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.notes import create_note, get_note, list_notes
from tools.obsidian import (
    generate_budget_report,
    generate_calendar_view,
    generate_kanban_board,
    generate_weekly_plan,
    sync_vault,
    update_dashboard,
)

from tools.vault_files import (
    append_vault_file,
    create_vault_file,
    delete_vault_file,
    read_vault_file,
    search_vault,
)

from tools.slides import draft_slides, render_slides
from tools.tasks import complete_task, create_task, delete_task, list_tasks, update_task
from tools.web_search import web_search

_single_agent: Agent | None = None


def reset_single_agent() -> None:
    global _single_agent
    _single_agent = None


def get_single_agent(model: str | None = None) -> Agent:
    """
    Pluto — the primary single agent with all tools and no handoffs.

    One agent handles everything: notes, calendar, memory, slides, research,
    tasks, budget, diagrams, and Obsidian vault sync. Planning and execution
    are handled by the autonomous loop (Planner + Executor agents), not here.

    The model argument allows the eval sweep (Ablation C/G) to override the
    default model without affecting the cached singleton.
    """
    global _single_agent
    if _single_agent is not None and model is None:
        return _single_agent

    cfg = load_config()["orchestrator"]
    model_name = model or cfg["model"]

    agent = Agent(
        name="Pluto",
        model=get_model(model_name),
        instructions=load_instructions("agents/single_agent"),
        tools=[
            # Memory
            store_memory, forget_memory, prune_memory,
            # Web
            web_search,
            # Notes
            create_note, list_notes, get_note,
            # Slides
            draft_slides, render_slides,
            # Calendar
            schedule_event, list_events, upcoming_events, cancel_event,
            # Tasks / Kanban
            create_task, list_tasks, update_task, complete_task, delete_task,
            # Budget
            add_transaction, list_transactions, delete_transaction,
            budget_summary, create_savings_goal, list_savings_goals, delete_savings_goal,
            # Calculator
            calculate,
            # Diagrams
            generate_diagram,
            # Obsidian vault — structured pages
            update_dashboard, generate_calendar_view, generate_kanban_board,
            generate_budget_report, generate_weekly_plan, sync_vault,
            # Obsidian vault — file operations
            search_vault, read_vault_file, create_vault_file,
            append_vault_file, delete_vault_file,
        ],
        model_settings=ModelSettings(
            temperature=cfg.get("temperature", 0.0),
            tool_choice=cfg.get("tool_choice", "auto"),
        ),
    )

    if model is None:
        _single_agent = agent
    return agent
