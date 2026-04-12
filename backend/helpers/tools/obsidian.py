"""Helper functions for generating Obsidian-compatible markdown files."""

from __future__ import annotations

import calendar
import os
import threading
from datetime import date, datetime, timedelta

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def sync_vault_background() -> None:
    """
    Fire-and-forget vault sync. Regenerates all structured pages in a background
    thread so callers are never blocked. Silently skips if vault is not configured.
    """
    def _run() -> None:
        try:
            vault_path = get_vault_path()
        except ValueError:
            return  # vault not configured — nothing to do

        from helpers.tools.budget import get_db_path as get_budget_db
        from helpers.tools.budget import get_summary, list_goals, list_transactions
        from helpers.tools.calendar import get_db_path as get_cal_db
        from helpers.tools.calendar import list_events
        from helpers.tools.tasks import get_db_path as get_tasks_db
        from helpers.tools.tasks import list_tasks

        today = date.today()
        month_str = today.strftime("%Y-%m")
        week_start = today - timedelta(days=today.weekday())

        # Dashboard
        try:
            tasks = list_tasks(get_tasks_db())
            _, last_day = calendar.monthrange(today.year, today.month)
            events = list_events(
                get_cal_db(),
                today.isoformat(),
                (today.replace(day=last_day) + timedelta(days=60)).isoformat(),
            )
            budget = get_summary(get_budget_db())
            goals = list_goals(get_budget_db())
            write_vault_file(
                vault_path, "Dashboard.md",
                generate_dashboard_md(tasks, events, budget, goals),
            )
        except Exception as exc:
            logger.warning("sync_vault_background: dashboard failed: %s", exc)

        # Kanban
        try:
            all_tasks = list_tasks(get_tasks_db())
            write_vault_file(vault_path, "Kanban/tasks.md", generate_kanban_md(all_tasks))
        except Exception as exc:
            logger.warning("sync_vault_background: kanban failed: %s", exc)

        # Budget
        try:
            summary = get_summary(get_budget_db(), month_str)
            all_goals = list_goals(get_budget_db())
            txs = list_transactions(get_budget_db())
            write_vault_file(
                vault_path, f"Budget/{month_str}.md",
                generate_budget_md(summary, all_goals, txs),
            )
        except Exception as exc:
            logger.warning("sync_vault_background: budget failed: %s", exc)

        # Calendar (current month)
        try:
            _, last_day = calendar.monthrange(today.year, today.month)
            cal_events = list_events(
                get_cal_db(), f"{month_str}-01", f"{month_str}-{last_day:02d}T23:59:59"
            )
            write_vault_file(
                vault_path, f"Calendar/{month_str}.md",
                generate_calendar_md(cal_events, today.year, today.month),
            )
        except Exception as exc:
            logger.warning("sync_vault_background: calendar failed: %s", exc)

        # Weekly plan
        try:
            week_end = week_start + timedelta(days=6)
            week_events = list_events(
                get_cal_db(), week_start.isoformat(), week_end.isoformat() + "T23:59:59"
            )
            all_tasks = list_tasks(get_tasks_db())
            label = _week_label(week_start)
            write_vault_file(
                vault_path, f"Weekly/{label}.md",
                generate_weekly_plan_md(week_events, all_tasks, week_start),
            )
        except Exception as exc:
            logger.warning("sync_vault_background: weekly plan failed: %s", exc)

        logger.info("sync_vault_background: done")

    threading.Thread(target=_run, daemon=True).start()

PRIORITY_EMOJI = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
STATUS_EMOJI = {"todo": "⬜", "in_progress": "🔵", "done": "✅"}


def get_vault_path() -> str:
    path = load_config().get("obsidian", {}).get("vault_path", "")
    if not path:
        raise ValueError(
            "Obsidian vault path is not configured. "
            "Set 'obsidian.vault_path' in config.json."
        )
    return path


def write_vault_file(vault_path: str, relative_path: str, content: str) -> str:
    """Write content to a file in the vault. Creates parent dirs. Returns full path."""
    base = os.path.realpath(vault_path)
    full_path = os.path.realpath(os.path.join(vault_path, relative_path))
    if not full_path.startswith(base):
        raise ValueError("Target path escapes the vault directory.")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Vault file written: %s", full_path)
    return full_path


def _progress_bar(pct: float, width: int = 20) -> str:
    filled = int(width * min(pct, 100) / 100)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:.1f}%"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def generate_dashboard_md(
    tasks: list[dict],
    events: list[dict],
    budget_summary: dict,
    goals: list[dict],
) -> str:
    today = date.today().isoformat()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Task stats
    todo_count = sum(1 for t in tasks if t.get("status") == "todo")
    wip_count = sum(1 for t in tasks if t.get("status") == "in_progress")
    done_count = sum(1 for t in tasks if t.get("status") == "done")
    urgent = [
        t for t in tasks
        if t.get("priority") in ("urgent", "high") and t.get("status") != "done"
    ]

    # Upcoming events (next 7 days)
    upcoming = sorted(events, key=lambda e: e.get("start_time", ""))[:5]

    lines = [
        "---",
        "tags: [dashboard, home]",
        f"updated: {now}",
        "---",
        "",
        "# 🏠 Dashboard",
        "",
        f"> Last synced: {now}",
        "",
        "---",
        "",
        "## 📋 Tasks Overview",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| ⬜ Todo | {todo_count} |",
        f"| 🔵 In Progress | {wip_count} |",
        f"| ✅ Done | {done_count} |",
        f"| **Total** | **{len(tasks)}** |",
        "",
    ]

    if urgent:
        lines += ["### 🔥 Urgent / High Priority", ""]
        for t in urgent[:5]:
            emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
            due = f" _(due {t['due_date']})_" if t.get("due_date") else ""
            lines.append(f"- {emoji} **{t['title']}**{due}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 📅 Upcoming Events",
        "",
    ]
    if upcoming:
        lines += ["| Event | Time |", "|-------|------|"]
        for ev in upcoming:
            start = ev.get("start_time", "")[:16].replace("T", " ")
            lines.append(f"| {ev['title']} | {start} |")
    else:
        lines.append("_No upcoming events._")
    lines.append("")

    lines += [
        "---",
        "",
        "## 💰 Budget Snapshot",
        "",
        "| | Amount |",
        "|---|--------|",
        f"| 💚 Income | {budget_summary.get('total_income', 0):.2f} |",
        f"| 🔴 Expenses | {budget_summary.get('total_expenses', 0):.2f} |",
        f"| 💙 Net | {budget_summary.get('net', 0):.2f} |",
        "",
    ]

    if goals:
        lines += ["### 🎯 Savings Goals", ""]
        for g in goals:
            pct = g.get("percent_complete", 0)
            proj = g.get("projected_completion_date", "Unknown")
            bar = _progress_bar(pct)
            cur = g.get("current_amount", 0)
            tgt = g["target_amount"]
            lines.append(f"**{g['name']}** — {cur:.2f} / {tgt:.2f}")
            lines.append(f"`{bar}` → {proj}")
            lines.append("")

    lines += [
        "---",
        "",
        "## 🔗 Quick Links",
        "",
        "- [[Kanban/tasks|📋 Kanban Board]]",
        f"- [[Calendar/{today[:7]}|📅 This Month's Calendar]]",
        f"- [[Budget/{today[:7]}|💰 Budget Report]]",
        f"- [[Weekly/{_week_label(date.today())}|📆 This Week's Plan]]",
        "",
    ]

    return "\n".join(lines)


def _week_label(d: date) -> str:
    """Return ISO week label like 2026-W14."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


# ---------------------------------------------------------------------------
# Calendar view
# ---------------------------------------------------------------------------

def generate_calendar_md(events: list[dict], year: int, month: int) -> str:
    month_name = calendar.month_name[month]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Build day → events map
    day_events: dict[int, list[str]] = {}
    for ev in events:
        start = ev.get("start_time", "")
        try:
            ev_date = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if ev_date.year == year and ev_date.month == month:
                d = ev_date.day
                day_events.setdefault(d, []).append(
                    f"{ev_date.strftime('%H:%M')} {ev['title']}"
                )
        except Exception:
            pass

    # Calendar grid
    cal = calendar.monthcalendar(year, month)
    header = "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |"
    sep = "|-----|-----|-----|-----|-----|-----|-----|"

    rows = [header, sep]
    for week in cal:
        cells = []
        for d in week:
            if d == 0:
                cells.append("     ")
            else:
                evs = day_events.get(d, [])
                ev_str = "<br>".join(f"• {e}" for e in evs[:2])
                overflow = f"<br>+{len(evs)-2} more" if len(evs) > 2 else ""
                cells.append(f"**{d}**{('<br>' + ev_str + overflow) if ev_str else ''}")
        rows.append("| " + " | ".join(cells) + " |")

    lines = [
        "---",
        f"tags: [calendar, {year}-{month:02d}]",
        f"updated: {now}",
        "---",
        "",
        f"# 📅 {month_name} {year}",
        "",
        "[[Dashboard|🏠 Home]] | "
        f"[[Calendar/{year}-{(month-1) if month > 1 else 12:02d}|← Prev]] | "
        f"[[Calendar/{year}-{(month+1) if month < 12 else 1:02d}|Next →]]",
        "",
    ] + rows + [""]

    # Event list below calendar
    if day_events:
        lines += ["## Events This Month", ""]
        for day in sorted(day_events):
            lines.append(f"### {month_name} {day}")
            for ev_str in day_events[day]:
                lines.append(f"- {ev_str}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kanban board
# ---------------------------------------------------------------------------

def generate_kanban_md(tasks: list[dict], project: str = "") -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = f"Kanban — {project}" if project else "Kanban Board"

    todo = [t for t in tasks if t.get("status") == "todo"]
    wip = [t for t in tasks if t.get("status") == "in_progress"]
    done = [t for t in tasks if t.get("status") == "done"]

    def _task_item(t: dict) -> str:
        emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
        due = f" _(due {t['due_date']})_" if t.get("due_date") else ""
        desc = f"\n  _{t['description']}_" if t.get("description") else ""
        checked = "x" if t.get("status") == "done" else " "
        return f"- [{checked}] {emoji} **{t['title']}**{due}{desc}"

    lines = [
        "---",
        f"tags: [kanban, tasks{', ' + project if project else ''}]",
        f"updated: {now}",
        "---",
        "",
        f"# 📋 {title}",
        "",
        "[[Dashboard|🏠 Home]]",
        "",
        "---",
        "",
        f"## ⬜ Todo ({len(todo)})",
        "",
    ]
    lines += [_task_item(t) for t in todo] or ["_Nothing here._"]
    lines += [
        "",
        "---",
        "",
        f"## 🔵 In Progress ({len(wip)})",
        "",
    ]
    lines += [_task_item(t) for t in wip] or ["_Nothing here._"]
    lines += [
        "",
        "---",
        "",
        f"## ✅ Done ({len(done)})",
        "",
    ]
    lines += [_task_item(t) for t in done] or ["_Nothing completed yet._"]
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Budget report
# ---------------------------------------------------------------------------

def generate_budget_md(
    summary: dict,
    goals: list[dict],
    transactions: list[dict],
) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    period = summary.get("period", "all_time")
    title = f"Budget — {period}" if period != "all_time" else "Budget Overview"

    lines = [
        "---",
        f"tags: [budget, finance, {period}]",
        f"updated: {now}",
        "---",
        "",
        f"# 💰 {title}",
        "",
        "[[Dashboard|🏠 Home]]",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| | Amount |",
        "|---|--------|",
        f"| 💚 Total Income | **{summary.get('total_income', 0):.2f}** |",
        f"| 🔴 Total Expenses | **{summary.get('total_expenses', 0):.2f}** |",
        f"| 💙 Net Savings | **{summary.get('net', 0):.2f}** |",
        "",
    ]

    # By category
    by_cat = summary.get("by_category", [])
    if by_cat:
        lines += [
            "## Breakdown by Category", "",
            "| Type | Category | Amount |",
            "|------|----------|--------|",
        ]
        for item in by_cat:
            icon = "💚" if item["type"] == "income" else "🔴"
            lines.append(f"| {icon} {item['type']} | {item['category']} | {item['total']:.2f} |")
        lines.append("")

    # Savings goals
    if goals:
        lines += ["## 🎯 Savings Goals", ""]
        for g in goals:
            pct = g.get("percent_complete", 0)
            proj = g.get("projected_completion_date", "Unknown")
            rate = g.get("avg_monthly_savings", 0)
            bar = _progress_bar(pct)
            remaining = max(0, g["target_amount"] - g.get("current_amount", 0))
            lines += [
                f"### {g['name']}",
                "",
                "| | |",
                "|---|---|",
                f"| Target | {g['target_amount']:.2f} |",
                f"| Saved | {g.get('current_amount', 0):.2f} |",
                f"| Remaining | {remaining:.2f} |",
                f"| Monthly rate | {rate:.2f}/mo |",
                f"| Projected | {proj} |",
                "",
                f"`{bar}`",
                "",
            ]

    # Recent transactions
    recent = sorted(transactions, key=lambda t: t.get("date", ""), reverse=True)[:20]
    if recent:
        lines += [
            "## Recent Transactions",
            "",
            "| Date | Type | Category | Amount | Description |",
            "|------|------|----------|--------|-------------|",
        ]
        for tx in recent:
            icon = "💚" if tx["type"] == "income" else "🔴"
            lines.append(
                f"| {tx.get('date', '')[:10]} | {icon} {tx['type']} | "
                f"{tx.get('category', '')} | {tx.get('amount', 0):.2f} | "
                f"{tx.get('description', '')} |"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Weekly plan
# ---------------------------------------------------------------------------

def generate_weekly_plan_md(
    events: list[dict],
    tasks: list[dict],
    week_start: date,
) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    week_end = week_start + timedelta(days=6)
    week_label = _week_label(week_start)

    # Map events by day
    day_events: dict[date, list[dict]] = {}
    for ev in events:
        start = ev.get("start_time", "")
        try:
            ev_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
            if week_start <= ev_date <= week_end:
                day_events.setdefault(ev_date, []).append(ev)
        except Exception:
            pass

    # Map tasks by due date
    day_tasks: dict[date, list[dict]] = {}
    unscheduled = []
    for t in tasks:
        if t.get("status") == "done":
            continue
        due = t.get("due_date")
        if due:
            try:
                d = date.fromisoformat(due[:10])
                if week_start <= d <= week_end:
                    day_tasks.setdefault(d, []).append(t)
                elif d < week_start:
                    unscheduled.append(t)  # overdue
            except Exception:
                unscheduled.append(t)
        else:
            unscheduled.append(t)

    lines = [
        "---",
        f"tags: [weekly, plan, {week_label}]",
        f"updated: {now}",
        "---",
        "",
        f"# 📆 Week {week_label}",
        f"_{week_start.strftime('%B %d')} — {week_end.strftime('%B %d, %Y')}_",
        "",
        "[[Dashboard|🏠 Home]] | "
        f"[[Weekly/{_week_label(week_start - timedelta(days=7))}|← Prev Week]] | "
        f"[[Weekly/{_week_label(week_start + timedelta(days=7))}|Next Week →]]",
        "",
        "---",
        "",
    ]

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for i in range(7):
        d = week_start + timedelta(days=i)
        day_name = day_names[i]
        evs = day_events.get(d, [])
        ts = day_tasks.get(d, [])
        today_marker = " _(today)_" if d == date.today() else ""

        lines += [f"## {day_name} {d.strftime('%b %d')}{today_marker}", ""]

        if evs:
            lines.append("**Events:**")
            for ev in sorted(evs, key=lambda e: e.get("start_time", "")):
                start = ev.get("start_time", "")[:16].replace("T", " ").split(" ")[-1]
                end = ev.get("end_time", "")
                end_str = f" → {end[:16].split('T')[-1]}" if end else ""
                lines.append(f"- 📅 {start}{end_str} — {ev['title']}")
            lines.append("")

        if ts:
            lines.append("**Tasks due:**")
            for t in ts:
                emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
                lines.append(f"- [ ] {emoji} {t['title']}")
            lines.append("")

        if not evs and not ts:
            lines.append("_Free day_")
            lines.append("")

    if unscheduled:
        week_iso = week_start.isoformat()
        overdue = [
            t for t in unscheduled
            if t.get("due_date") and t["due_date"][:10] < week_iso
        ]
        inbox = [t for t in unscheduled if not t.get("due_date")]
        if overdue:
            lines += ["---", "", "## ⚠️ Overdue", ""]
            for t in overdue:
                emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
                lines.append(f"- [ ] {emoji} {t['title']} _(was due {t['due_date'][:10]})_")
            lines.append("")
        if inbox:
            lines += ["---", "", "## 📥 Inbox (no due date)", ""]
            for t in inbox[:10]:
                emoji = PRIORITY_EMOJI.get(t.get("priority", "medium"), "🟡")
                lines.append(f"- [ ] {emoji} {t['title']}")
            if len(inbox) > 10:
                lines.append(f"_...and {len(inbox)-10} more_")
            lines.append("")

    return "\n".join(lines)
