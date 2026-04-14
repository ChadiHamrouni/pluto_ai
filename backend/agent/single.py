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
from tools.calendar import cancel_event, list_events, schedule_event, upcoming_events, update_event
from tools.diagrams import generate_diagram
from tools.memory_tools import forget_memory, prune_memory, search_memory, store_memory
from tools.notes import create_note, get_note, list_notes
from tools.obsidian import (
    generate_budget_report,
    generate_calendar_view,
    generate_weekly_plan,
    show_kanban,
    sync_vault,
    update_dashboard,
)
from tools.slides import draft_slides, render_slides
from tools.tasks import complete_task, create_task, delete_task, list_tasks, update_task
from tools.vault_files import (
    append_vault_file,
    create_vault_file,
    delete_vault_file,
    read_vault_file,
    search_vault,
)
from tools.reminders import delete_reminder, list_reminders, set_reminder
from tools.web_search import web_search

# ---------------------------------------------------------------------------
# Tool groups — each intent sees only the tools it needs.
#
# Keeping the visible tool menu small is the single biggest accuracy lever
# for a 4B model: fewer choices → fewer wrong-tool picks, and ~2–3k fewer
# schema tokens per turn.
#
# _ALWAYS_AVAILABLE tools are injected into every group automatically.
# Add a tool here when the core instructions unconditionally mandate its use
# (e.g. "ALWAYS use calculate for ANY arithmetic") — otherwise the model will
# try to call it and crash with "Tool not found in agent".
#
# "core" is the fallback for unrecognised / free-form messages. It exposes
# a small read-oriented set so the agent can answer most questions and
# naturally ask for clarification rather than guessing a write tool.
# ---------------------------------------------------------------------------

_ALWAYS_AVAILABLE = [
    calculate,    # core instructions mandate this for ALL arithmetic
    store_memory, # agent should silently save facts it learns in any domain
    web_search,   # always available regardless of domain
]

def _group(*tools) -> list:
    """Return the tool list for a group, prepending _ALWAYS_AVAILABLE and deduplicating."""
    seen: set[int] = set()
    result = []
    for t in [*_ALWAYS_AVAILABLE, *tools]:
        if id(t) not in seen:
            seen.add(id(t))
            result.append(t)
    return result


TOOL_GROUPS: dict[str, list] = {
    "core": _group(
        # Cheap read-only tools so the agent can fetch context and answer
        # most questions without guessing a write tool.
        web_search,
        search_memory,
        list_notes,
        get_note,
        list_tasks,
        list_events,
        list_reminders,
        budget_summary,
        search_vault,
        show_kanban,
    ),
    "notes":    _group(create_note, list_notes, get_note),
    "slides":   _group(draft_slides, render_slides, web_search),
    "calendar": _group(schedule_event, list_events, upcoming_events, cancel_event, update_event),
    "reminders": _group(set_reminder, list_reminders, delete_reminder),
    "memory":   _group(store_memory, forget_memory, prune_memory, search_memory),
    "tasks":    _group(
        create_task, list_tasks, update_task, complete_task, delete_task, show_kanban
    ),
    "budget":   _group(
        add_transaction, list_transactions, delete_transaction,
        budget_summary, create_savings_goal, list_savings_goals, delete_savings_goal,
    ),
    "diagrams": _group(generate_diagram),
    "vault":    _group(
        update_dashboard, generate_calendar_view, show_kanban,
        generate_budget_report, generate_weekly_plan, sync_vault,
        search_vault, read_vault_file, create_vault_file,
        append_vault_file, delete_vault_file,
    ),
    # Full set — used only for eval sweeps or unknown intents that opt in explicitly.
    "all": _group(
        store_memory, forget_memory, prune_memory, search_memory,
        web_search,
        create_note, list_notes, get_note,
        draft_slides, render_slides,
        schedule_event, list_events, upcoming_events, cancel_event, update_event,
        create_task, list_tasks, update_task, complete_task, delete_task,
        add_transaction, list_transactions, delete_transaction,
        budget_summary, create_savings_goal, list_savings_goals, delete_savings_goal,
        generate_diagram,
        set_reminder, list_reminders, delete_reminder,
        update_dashboard, generate_calendar_view, show_kanban,
        generate_budget_report, generate_weekly_plan, sync_vault,
        search_vault, read_vault_file, create_vault_file,
        append_vault_file, delete_vault_file,
    ),
}

_single_agent: Agent | None = None


def reset_single_agent() -> None:
    global _single_agent
    _single_agent = None


def get_single_agent(model: str | None = None) -> Agent:
    """
    Return the cached Pluto singleton with the full tool set.

    Use get_agent_for_intent() in normal request handling — this function
    exists for backward compatibility and eval sweeps that need the full set.
    The model argument lets eval sweeps override the default without polluting
    the singleton cache.
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
        tools=TOOL_GROUPS["all"],
        model_settings=ModelSettings(
            temperature=cfg.get("temperature", 0.0),
            tool_choice=cfg.get("tool_choice", "auto"),
            parallel_tool_calls=True,
            extra_body={"think": False},
        ),
    )

    if model is None:
        _single_agent = agent
    return agent


def get_agent_for_intent(
    intent: str | None,
    tool_group: str | None = None,
    model: str | None = None,
) -> Agent:
    """
    Return an agent scoped to the given intent's tool group.

    The base agent (instructions, model, settings) is always the Pluto
    singleton. Only the tool list is narrowed. This means:
    - No extra LLM calls — single turn, same model, same latency profile.
    - The 4B model picks from 3–8 tools instead of 29 → higher accuracy.
    - Tool schema tokens drop from ~3k to ~300–800 per scoped turn.

    Args:
        intent:     Routing tag from ParsedCommand (e.g. "note", "budget").
                    Pass None for free-form messages → falls back to "core".
        tool_group: Override the group name if it differs from the intent.
                    Usually you can pass ParsedCommand.tool_group directly.
        model:      Optional model override (for eval sweeps).

    Returns:
        A cloned Agent with the scoped tool list and a matching domain
        instructions appendix loaded from instructions/agents/domain/<group>.md
        (if the file exists; silently falls back to the base instructions).
    """
    base = get_single_agent(model=model)

    group = tool_group or intent or "core"
    tools = TOOL_GROUPS.get(group, TOOL_GROUPS["core"])

    # Append the domain-specific instructions section if one exists.
    domain_instructions = _load_domain_instructions(group)
    if domain_instructions:
        instructions = base.instructions + "\n\n---\n\n" + domain_instructions
    else:
        instructions = base.instructions

    return base.clone(tools=tools, instructions=instructions)


def _load_domain_instructions(group: str) -> str:
    """Load optional per-domain instruction appendix. Returns empty string if absent."""
    try:
        return load_instructions(f"agents/domain/{group}")
    except (FileNotFoundError, OSError):
        return ""
