"""DashboardAgent — tasks, budget, diagrams, and Obsidian vault management."""

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
from tools.diagrams import generate_diagram
from tools.obsidian import (
    generate_budget_report,
    generate_calendar_view,
    generate_kanban_board,
    generate_weekly_plan,
    sync_vault,
    update_dashboard,
)
from tools.tasks import (
    complete_task,
    create_task,
    delete_task,
    list_tasks,
    update_task,
)

_dashboard: Agent | None = None


def reset_dashboard_agent() -> None:
    global _dashboard
    _dashboard = None


def get_dashboard_agent() -> Agent:
    global _dashboard
    if _dashboard is None:
        cfg = load_config().get("dashboard_agent", {})
        _dashboard = Agent(
            name="DashboardAgent",
            model=get_model(cfg.get("model", "qwen3.5:9b")),
            instructions=load_instructions("agents/dashboard_agent"),
            tools=[
                # Tasks
                create_task,
                list_tasks,
                update_task,
                complete_task,
                delete_task,
                # Budget
                add_transaction,
                list_transactions,
                delete_transaction,
                budget_summary,
                create_savings_goal,
                list_savings_goals,
                delete_savings_goal,
                # Diagrams
                generate_diagram,
                # Obsidian vault
                update_dashboard,
                generate_calendar_view,
                generate_kanban_board,
                generate_budget_report,
                generate_weekly_plan,
                sync_vault,
            ],
            model_settings=ModelSettings(
                temperature=cfg.get("temperature", 0.0),
                tool_choice=cfg.get("tool_choice", "auto"),
            ),
        )
    return _dashboard
