"""Obsidian vault sync @function_tool wrappers for the DashboardAgent."""

from __future__ import annotations

from datetime import date, timedelta

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.budget import get_db_path as get_budget_db
from helpers.tools.budget import get_summary, list_goals, list_transactions
from helpers.tools.calendar import get_db_path as get_cal_db
from helpers.tools.calendar import list_events
from helpers.tools.obsidian import (
    _week_label,
    generate_budget_md,
    generate_calendar_md,
    generate_dashboard_md,
    generate_kanban_md,
    generate_weekly_plan_md,
    get_vault_path,
    write_vault_file,
)
from helpers.tools.tasks import get_db_path as get_tasks_db
from helpers.tools.tasks import list_tasks

logger = get_logger(__name__)


def _fetch_all_data() -> tuple:
    """Fetch tasks, events (next 60 days), budget summary, and goals."""
    tasks = list_tasks(get_tasks_db())
    now = date.today()
    events = list_events(
        get_cal_db(),
        now.isoformat(),
        (now + timedelta(days=60)).isoformat(),
    )
    budget = get_summary(get_budget_db())
    goals = list_goals(get_budget_db())
    return tasks, events, budget, goals


@function_tool
def update_dashboard() -> str:
    """
    Regenerate the main Obsidian dashboard page with current tasks, events, budget, and goals.

    Call this after any significant change to tasks, budget, or calendar to keep the
    dashboard fresh. Also useful when the user asks to "update my dashboard" or "sync vault".

    Returns:
        Path to the written dashboard.md file, or an error message.
    """
    try:
        vault_path = get_vault_path()
        tasks, events, budget, goals = _fetch_all_data()
        content = generate_dashboard_md(tasks, events, budget, goals)
        path = write_vault_file(vault_path, "Dashboard.md", content)
        return f"Dashboard updated: {path}"
    except ValueError as exc:
        return f"Configuration error: {exc}"
    except Exception as exc:
        logger.error("update_dashboard failed: %s", exc)
        return f"Failed to update dashboard: {exc}"


@function_tool
def generate_calendar_view(month: str = "") -> str:
    """
    Generate a calendar page for a given month in the Obsidian vault.

    Creates a markdown calendar grid showing all events for the month,
    saved to Calendar/YYYY-MM.md in the vault.

    Args:
        month: Month in "YYYY-MM" format (e.g. "2026-03"). Defaults to current month.

    Returns:
        Path to the written calendar file, or an error message.
    """
    try:
        vault_path = get_vault_path()
        if not month:
            today = date.today()
            year, mon = today.year, today.month
            month = f"{year}-{mon:02d}"
        else:
            year, mon = int(month[:4]), int(month[5:7])

        from calendar import monthrange
        _, last_day = monthrange(year, mon)
        from_date = f"{month}-01"
        to_date = f"{month}-{last_day:02d}"
        events = list_events(get_cal_db(), from_date, to_date + "T23:59:59")

        content = generate_calendar_md(events, year, mon)
        path = write_vault_file(vault_path, f"Calendar/{month}.md", content)
        return f"Calendar view generated: {path}"
    except ValueError as exc:
        return f"Configuration error: {exc}"
    except Exception as exc:
        logger.error("generate_calendar_view failed: %s", exc)
        return f"Failed to generate calendar view: {exc}"


@function_tool
def show_kanban(project: str = "") -> str:
    """
    Show the Kanban board inline as a markdown response.

    Displays all tasks grouped into Todo / In Progress / Done columns.
    Use this when the user asks to see their kanban board, task board, or
    wants a visual overview of their tasks by status.

    Args:
        project: Optional category to filter tasks (e.g. "work"). Empty = all tasks.

    Returns:
        Markdown kanban board to display directly to the user.
    """
    try:
        tasks = list_tasks(get_tasks_db(), project=project)
    except Exception as exc:
        logger.error("show_kanban failed: %s", exc)
        return f"Failed to load tasks: {exc}"

    PRIORITY_EMOJI = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

    todo = [t for t in tasks if t.get("status") == "todo"]
    wip  = [t for t in tasks if t.get("status") == "in_progress"]
    done = [t for t in tasks if t.get("status") == "done"]

    def _item(t: dict) -> str:
        emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
        due   = f" _(due {t['due_date']})_" if t.get("due_date") else ""
        desc  = f"\n  _{t['description']}_" if t.get("description") else ""
        check = "x" if t.get("status") == "done" else " "
        return f"- [{check}] {emoji} **{t['title']}**{due}{desc}"

    title = f"Kanban — {project}" if project else "Kanban Board"
    lines = [f"## 📋 {title}", ""]

    lines += [f"### ⬜ Todo ({len(todo)})", ""]
    lines += [_item(t) for t in todo] or ["_Nothing here._"]

    lines += ["", f"### 🔵 In Progress ({len(wip)})", ""]
    lines += [_item(t) for t in wip] or ["_Nothing here._"]

    lines += ["", f"### ✅ Done ({len(done)})", ""]
    lines += [_item(t) for t in done] or ["_Nothing completed yet._"]

    return "\n".join(lines)


@function_tool
def generate_budget_report(month: str = "") -> str:
    """
    Generate a budget report page in the Obsidian vault.

    Creates a markdown report with income/expense summary, category breakdown,
    savings goal progress bars, and recent transactions.

    Args:
        month: Month in "YYYY-MM" format. Empty = current month.

    Returns:
        Path to the written budget file, or an error message.
    """
    try:
        vault_path = get_vault_path()
        if not month:
            month = date.today().strftime("%Y-%m")
        summary = get_summary(get_budget_db(), month)
        goals = list_goals(get_budget_db())
        transactions = list_transactions(get_budget_db())
        content = generate_budget_md(summary, goals, transactions)
        path = write_vault_file(vault_path, f"Budget/{month}.md", content)
        return f"Budget report generated: {path}"
    except ValueError as exc:
        return f"Configuration error: {exc}"
    except Exception as exc:
        logger.error("generate_budget_report failed: %s", exc)
        return f"Failed to generate budget report: {exc}"


@function_tool
def generate_weekly_plan(week_start_date: str = "") -> str:
    """
    Generate a weekly plan page in the Obsidian vault.

    Creates a day-by-day view for the week with scheduled events, tasks due that
    week, overdue tasks, and an inbox of unscheduled tasks.

    Args:
        week_start_date: ISO-8601 date of the Monday to start from (e.g. "2026-03-31").
                         Defaults to the current week's Monday.

    Returns:
        Path to the written weekly plan file, or an error message.
    """
    try:
        vault_path = get_vault_path()
        today = date.today()

        if week_start_date:
            week_start = date.fromisoformat(week_start_date[:10])
            # Snap to Monday
            week_start -= timedelta(days=week_start.weekday())
        else:
            week_start = today - timedelta(days=today.weekday())

        week_end = week_start + timedelta(days=6)
        week_end_str = week_end.isoformat() + "T23:59:59"
        events = list_events(get_cal_db(), week_start.isoformat(), week_end_str)
        tasks = list_tasks(get_tasks_db())

        content = generate_weekly_plan_md(events, tasks, week_start)
        label = _week_label(week_start)
        path = write_vault_file(vault_path, f"Weekly/{label}.md", content)
        return f"Weekly plan generated: {path}"
    except ValueError as exc:
        return f"Configuration error: {exc}"
    except Exception as exc:
        logger.error("generate_weekly_plan failed: %s", exc)
        return f"Failed to generate weekly plan: {exc}"


@function_tool
def sync_vault() -> str:
    """
    Regenerate all Obsidian vault pages: dashboard, calendar, kanban, budget, and weekly plan.

    Use this when the user asks to "sync everything", "update my vault", "refresh Obsidian",
    or after a series of changes across tasks/budget/calendar.

    Returns:
        Summary of all files written, or an error message.
    """
    results = []
    errors = []

    try:
        vault_path = get_vault_path()
    except ValueError as exc:
        return f"Configuration error: {exc}"

    today = date.today()
    month_str = today.strftime("%Y-%m")
    week_start = today - timedelta(days=today.weekday())

    # Dashboard
    try:
        tasks, events, budget, goals = _fetch_all_data()
        content = generate_dashboard_md(tasks, events, budget, goals)
        path = write_vault_file(vault_path, "Dashboard.md", content)
        results.append(f"✅ Dashboard: {path}")
    except Exception as exc:
        errors.append(f"❌ Dashboard: {exc}")

    # Calendar (current month)
    try:
        from calendar import monthrange
        _, last_day = monthrange(today.year, today.month)
        cal_to = f"{month_str}-{last_day:02d}T23:59:59"
        events_cal = list_events(get_cal_db(), f"{month_str}-01", cal_to)
        content = generate_calendar_md(events_cal, today.year, today.month)
        path = write_vault_file(vault_path, f"Calendar/{month_str}.md", content)
        results.append(f"✅ Calendar: {path}")
    except Exception as exc:
        errors.append(f"❌ Calendar: {exc}")

    # Kanban
    try:
        all_tasks = list_tasks(get_tasks_db())
        content = generate_kanban_md(all_tasks)
        path = write_vault_file(vault_path, "Kanban/tasks.md", content)
        results.append(f"✅ Kanban: {path}")
    except Exception as exc:
        errors.append(f"❌ Kanban: {exc}")

    # Budget
    try:
        summary = get_summary(get_budget_db(), month_str)
        all_goals = list_goals(get_budget_db())
        txs = list_transactions(get_budget_db())
        content = generate_budget_md(summary, all_goals, txs)
        path = write_vault_file(vault_path, f"Budget/{month_str}.md", content)
        results.append(f"✅ Budget: {path}")
    except Exception as exc:
        errors.append(f"❌ Budget: {exc}")

    # Weekly plan
    try:
        week_end = week_start + timedelta(days=6)
        week_end_str = week_end.isoformat() + "T23:59:59"
        week_events = list_events(get_cal_db(), week_start.isoformat(), week_end_str)
        all_tasks = list_tasks(get_tasks_db())
        content = generate_weekly_plan_md(week_events, all_tasks, week_start)
        label = _week_label(week_start)
        path = write_vault_file(vault_path, f"Weekly/{label}.md", content)
        results.append(f"✅ Weekly plan: {path}")
    except Exception as exc:
        errors.append(f"❌ Weekly plan: {exc}")

    summary_lines = ["Vault sync complete:", ""] + results
    if errors:
        summary_lines += ["", "Errors:"] + errors
    return "\n".join(summary_lines)
