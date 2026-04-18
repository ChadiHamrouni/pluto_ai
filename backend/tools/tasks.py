"""Task management @function_tool wrappers for the DashboardAgent."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.idempotency import make_key as _make_key
from models.batch import TaskSpec
from helpers.tools.tasks import (
    VALID_PRIORITIES,
    VALID_STATUSES,
    get_db_path,
)
from helpers.tools.tasks import (
    create_task as _create_task,
)
from helpers.tools.tasks import (
    create_tasks_batch as _create_tasks_batch,
)
from helpers.tools.tasks import (
    delete_task as _delete_task,
)
from helpers.tools.tasks import (
    list_tasks as _list_tasks,
)
from helpers.tools.tasks import (
    update_task as _update_task,
)
from models.tasks import VALID_CATEGORIES

logger = get_logger(__name__)


@function_tool
def create_task(
    title: str,
    category: str = "personal",
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
    due_date: str = "",
    tags: str = "",
) -> str:
    """
    Create a new task and add it to the kanban board.

    Use this when the user wants to add a task, to-do item, action item, or anything
    they need to get done. Tasks have a kanban status (todo/in_progress/done), a
    priority level, and a category that groups tasks by life area.

    Args:
        title:       REQUIRED. Short task title (e.g. "Buy clipper").
        category:    REQUIRED. One of: groceries, work, career, finance, health, personal, home.
                     Infer from context — shopping/food → groceries, job/school → work or career,
                     money/bills → finance, doctor/gym → health, repairs/cleaning → home.
        description: Optional longer description or notes about the task.
        status:      One of: todo, in_progress, done. Default: todo.
        priority:    One of: low, medium, high, urgent. Default: medium.
        due_date:    Optional ISO-8601 due date (e.g. "2026-04-01"). Leave empty if none.
        tags:        Comma-separated tags (e.g. "shopping,errands"). Empty string if none.

    Returns:
        Confirmation string with the task id, or an error message.
    """
    if status not in VALID_STATUSES:
        return f"Error: invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
    if priority not in VALID_PRIORITIES:
        return f"Error: invalid priority '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}"
    if category not in VALID_CATEGORIES:
        return f"Error: invalid category '{category}'. Must be one of: {sorted(VALID_CATEGORIES)}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        task = _create_task(
            get_db_path(), title, description, status, priority,
            due_date, tags_json, category,
        )
        due_str = f", due {task['due_date']}" if task.get("due_date") else ""
        return (
            f"Task created (id={task['id']}): \"{title}\" "
            f"[{priority.upper()}] [{category}]{due_str}"
        )
    except Exception as exc:
        logger.error("create_task failed: %s", exc)
        return f"Failed to create task: {exc}"


@function_tool
def create_tasks(tasks: list[TaskSpec]) -> str:
    """
    Create one or more tasks. Use for any request to add tasks —
    single or multiple. Pass a list with one item for a single task.

    Each item is a TaskSpec with:
        title       (required) — task title
        category    (required) — groceries | work | career | finance | health | personal | home
        description (optional)
        status      (optional) — todo | in_progress | done  (default: todo)
        priority    (optional) — low | medium | high | urgent  (default: medium)
        due_date    (optional) — ISO-8601 date e.g. "2026-04-30"
        tags        (optional) — comma-separated tags

    Idempotency: re-submitting the same (title, category) pair is safe — duplicates
    are skipped and reported as status='skipped'.

    Returns:
        Summary string: how many created / skipped, with ids and titles.
    """
    prepped: list[dict] = []
    for t in tasks:
        title = t.title
        category = t.category if t.category in VALID_CATEGORIES else "personal"
        status = t.status if t.status in VALID_STATUSES else "todo"
        priority = t.priority if t.priority in VALID_PRIORITIES else "medium"
        tag_list = [x.strip() for x in t.tags.split(",") if x.strip()] if t.tags else []
        prepped.append({
            "title": title,
            "category": category,
            "description": t.description,
            "status": status,
            "priority": priority,
            "due_date": t.due_date,
            "tags_json": json.dumps(tag_list),
            "idempotency_key": _make_key(title, category),
        })

    if not prepped:
        return "No valid tasks to create."

    try:
        results = _create_tasks_batch(get_db_path(), prepped)
    except Exception as exc:
        logger.error("create_tasks failed: %s", exc)
        return f"Failed to create tasks: {exc}"

    created = [r for r in results if r["status"] == "created"]
    skipped = [r for r in results if r["status"] == "skipped"]
    lines = [f"Created {len(created)} task(s), skipped {len(skipped)} duplicate(s)."]
    for r in created:
        lines.append(f"  ✓ [{r['id']}] {r['title']}")
    for r in skipped:
        lines.append(f"  ~ [{r['id']}] skipped (duplicate)")
    return "\n".join(lines)


@function_tool
def list_tasks(status: str = "", priority: str = "", category: str = "") -> str:
    """
    List tasks, optionally filtered by status, priority, or category.

    Use this to show the user their tasks, kanban board, to-do list, or backlog.
    Returns tasks sorted by priority (urgent first) then due date.

    To show ALL tasks organized by category, call with no filters — then group the
    results by the "category" field in your response.

    Args:
        status:   Filter by status. One of: todo, in_progress, done. Empty = all.
        priority: Filter by priority. One of: low, medium, high, urgent. Empty = all.
        category: Filter by category. One of: groceries, work, career, finance, health,
                  personal, home. Empty = all categories.

    Returns:
        JSON array of task objects, or a message if no tasks found.
    """
    try:
        tasks = _list_tasks(get_db_path(), status, priority, category)
        if not tasks:
            filters = []
            if status:
                filters.append(f"status={status}")
            if priority:
                filters.append(f"priority={priority}")
            if category:
                filters.append(f"category={category}")
            filter_str = f" matching {', '.join(filters)}" if filters else ""
            return f"No tasks found{filter_str}."
        return json.dumps(tasks, indent=2)
    except Exception as exc:
        logger.error("list_tasks failed: %s", exc)
        return f"Failed to list tasks: {exc}"


@function_tool
def update_task(
    task_id: int,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    due_date: str = "",
    tags: str = "",
    category: str = "",
) -> str:
    """
    Update an existing task. Only provided (non-empty) fields are changed.

    Use this when the user wants to edit, modify, reschedule, reprioritize, or
    move a task between kanban columns. To mark a task complete, use complete_task instead.

    Args:
        task_id:     REQUIRED. The numeric id of the task to update.
        title:       New title. Leave empty to keep current.
        description: New description. Leave empty to keep current.
        status:      New status: todo, in_progress, or done. Leave empty to keep current.
        priority:    New priority: low, medium, high, urgent. Leave empty to keep current.
        due_date:    New due date (ISO-8601) or "none" to clear. Leave empty to keep current.
        tags:        New comma-separated tags. Leave empty to keep current.
        category:    New category. One of: groceries, work, career, finance, health, personal, home.

    Returns:
        Updated task as JSON, or an error message.
    """
    if status and status not in VALID_STATUSES:
        return f"Error: invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
    if priority and priority not in VALID_PRIORITIES:
        return f"Error: invalid priority '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}"
    if category and category not in VALID_CATEGORIES:
        return f"Error: invalid category '{category}'. Must be one of: {sorted(VALID_CATEGORIES)}"

    fields: dict = {}
    if title:
        fields["title"] = title
    if description:
        fields["description"] = description
    if status:
        fields["status"] = status
    if priority:
        fields["priority"] = priority
    if due_date == "none":
        fields["due_date"] = None
    elif due_date:
        fields["due_date"] = due_date
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        fields["tags"] = json.dumps(tag_list)
    if category:
        fields["category"] = category

    try:
        task = _update_task(get_db_path(), task_id, **fields)
        if task is None:
            return f"No task found with id={task_id}."
        return json.dumps(task, indent=2)
    except Exception as exc:
        logger.error("update_task failed: %s", exc)
        return f"Failed to update task: {exc}"


@function_tool
def complete_task(task_id: int) -> str:
    """
    Mark a task as done.

    Use this when the user says a task is finished, completed, done, or checked off.
    This is a shortcut for update_task with status=done — it also records the
    completion timestamp automatically.

    Args:
        task_id: The numeric id of the task to mark as done.

    Returns:
        Confirmation string or error.
    """
    try:
        task = _update_task(
            get_db_path(),
            task_id,
            status="done",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        if task is None:
            return f"No task found with id={task_id}."
        return f"Task {task_id} marked as done: \"{task['title']}\""
    except Exception as exc:
        logger.error("complete_task failed: %s", exc)
        return f"Failed to complete task: {exc}"


@function_tool
def delete_task(task_id: int) -> str:
    """
    Permanently delete a task.

    Use this only when the user explicitly wants to remove a task entirely.
    If the task is just finished, use complete_task instead.

    Args:
        task_id: The numeric id of the task to delete.

    Returns:
        Confirmation or error string.
    """
    try:
        deleted = _delete_task(get_db_path(), task_id)
        if deleted:
            return f"Task {task_id} deleted."
        return f"No task found with id={task_id}."
    except Exception as exc:
        logger.error("delete_task failed: %s", exc)
        return f"Failed to delete task: {exc}"
