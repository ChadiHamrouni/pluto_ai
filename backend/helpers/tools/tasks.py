"""Helper functions for task/kanban persistence (DB)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

VALID_STATUSES = {"todo", "in_progress", "done"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def create_task(
    db_path: str,
    title: str,
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
    due_date: str = "",
    tags_json: str = "[]",
    project: str = "",
) -> dict:
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO tasks (title, description, status, priority, due_date, tags, project)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, description, status, priority, due_date or None, tags_json, project),
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created task id=%d title='%s'", task_id, title)
    return get_task(db_path, task_id)


def list_tasks(
    db_path: str,
    status: str = "",
    priority: str = "",
    project: str = "",
) -> list[dict]:
    conn = _connect(db_path)
    clauses = []
    params = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if project:
        clauses.append("project = ?")
        params.append(project)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM tasks {where} ORDER BY "
        "CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,"
        " due_date ASC NULLS LAST, created_at ASC",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(db_path: str, task_id: int) -> dict | None:
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_task(db_path: str, task_id: int, **fields) -> dict | None:
    allowed = {"title", "description", "status", "priority", "due_date", "tags", "project", "completed_at"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_task(db_path, task_id)

    # Auto-set completed_at when marking done
    if updates.get("status") == "done" and "completed_at" not in updates:
        updates["completed_at"] = datetime.now(timezone.utc).isoformat()
    elif updates.get("status") in ("todo", "in_progress"):
        updates["completed_at"] = None

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [task_id]
    conn = _connect(db_path)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_task(db_path, task_id)


def delete_task(db_path: str, task_id: int) -> bool:
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
