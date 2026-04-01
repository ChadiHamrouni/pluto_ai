from __future__ import annotations

from agents import Agent

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
from tools.slides import draft_slides, render_slides
from tools.tasks import complete_task, create_task, delete_task, list_tasks, update_task
from tools.web_search import web_search

_executor: Agent | None = None


def get_executor_agent() -> Agent:
    global _executor
    if _executor is None:
        cfg = load_config()
        model_name = cfg.get("autonomous", {}).get("executor_model", cfg["orchestrator"]["model"])
        _executor = Agent(
            name="Executor",
            model=get_model(model_name),
            instructions=load_instructions("autonomous/executor"),
            tools=[
                web_search,
                store_memory,
                forget_memory,
                prune_memory,
                create_note,
                list_notes,
                get_note,
                draft_slides,
                render_slides,
                schedule_event,
                list_events,
                upcoming_events,
                cancel_event,
                create_task,
                list_tasks,
                update_task,
                complete_task,
                delete_task,
                add_transaction,
                list_transactions,
                delete_transaction,
                budget_summary,
                create_savings_goal,
                list_savings_goals,
                delete_savings_goal,
                generate_diagram,
                update_dashboard,
                generate_calendar_view,
                generate_kanban_board,
                generate_budget_report,
                generate_weekly_plan,
                sync_vault,
            ],
        )
    return _executor


def reset_executor_agent() -> None:
    global _executor
    _executor = None
