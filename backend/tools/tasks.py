"""Task management @function_tool wrappers for the DashboardAgent."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.tasks import (
    VALID_PRIORITIES,
    VALID_STATUSES,
    get_db_path,
)
from helpers.tools.tasks import (
    create_task as _create_task,
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

logger = get_logger(__name__)


@function_tool
def create_task(
    title: str,
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
    due_date: str = "",
    tags: str = "",
    project: str = "",
) -> str:
    """
    Create a new task and add it to the kanban board.

    Use this when the user wants to add a task, to-do item, action item, or anything
    they need to get done. Tasks have a kanban status (todo/in_progress/done) and a
    priority level. Use project to group related tasks (e.g. "work", "personal").

    Args:
        title:       REQUIRED. Short task title (e.g. "Buy groceries").
        description: Optional longer description or notes about the task.
        status:      One of: todo, in_progress, done. Default: todo.
        priority:    One of: low, medium, high, urgent. Default: medium.
        due_date:    Optional ISO-8601 due date (e.g. "2026-04-01"). Leave empty if none.
        tags:        Comma-separated tags (e.g. "shopping,errands"). Empty string if none.
        project:     Project or area name to group tasks (e.g. "work", "health"). Empty if none.

    Returns:
        Confirmation string with the task id, or an error message.
    """
    if status not in VALID_STATUSES:
        return f"Error: invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
    if priority not in VALID_PRIORITIES:
        return f"Error: invalid priority '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        task = _create_task(
            get_db_path(), title, description, status, priority,
            due_date, tags_json, project,
        )
        due_str = f", due {task['due_date']}" if task.get("due_date") else ""
        return (
            f"Task created (id={task['id']}): \"{title}\" "
            f"[{priority.upper()}]{due_str}"
        )
    except Exception as exc:
        logger.error("create_task failed: %s", exc)
        return f"Failed to create task: {exc}"


@function_tool
def list_tasks(status: str = "", priority: str = "", project: str = "") -> str:
    """
    List tasks, optionally filtered by status, priority, or project.

    Use this to show the user their tasks, kanban board, to-do list, or backlog.
    Returns tasks sorted by priority (urgent first) then due date.

    Args:
        status:   Filter by status. One of: todo, in_progress, done. Empty = all.
        priority: Filter by priority. One of: low, medium, high, urgent. Empty = all.
        project:  Filter by project name. Empty = all projects.

    Returns:
        JSON array of task objects, or a message if no tasks found.
    """
    try:
        tasks = _list_tasks(get_db_path(), status, priority, project)
        if not tasks:
            filters = []
            if status:
                filters.append(f"status={status}")
            if priority:
                filters.append(f"priority={priority}")
            if project:
                filters.append(f"project={project}")
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
    project: str = "",
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
        project:     New project. Leave empty to keep current.

    Returns:
        Updated task as JSON, or an error message.
    """
    if status and status not in VALID_STATUSES:
        return f"Error: invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
    if priority and priority not in VALID_PRIORITIES:
        return f"Error: invalid priority '{priority}'. Must be one of: {sorted(VALID_PRIORITIES)}"

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
    if project:
        fields["project"] = project

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
