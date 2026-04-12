from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from helpers.core.logger import get_logger

logger = get_logger(__name__)

CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_NOTES_TABLE = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    category   TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '[]',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    file_path  TEXT
);
"""

CREATE_MEMORIES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    memory_id UNINDEXED
);
"""

CREATE_MEMORIES_IDX = """
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
"""

CREATE_NOTES_IDX = """
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
"""


CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT    PRIMARY KEY,
    title      TEXT    NOT NULL DEFAULT 'New Chat',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role           TEXT    NOT NULL,
    content        TEXT    NOT NULL,
    metadata       TEXT    NOT NULL DEFAULT '{}',
    user_metadata  TEXT    NOT NULL DEFAULT '{}',
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# Migration: add metadata column to existing databases that predate it
MIGRATE_CONVERSATIONS_METADATA = """
ALTER TABLE conversations ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}';
"""

MIGRATE_CONVERSATIONS_USER_METADATA = """
ALTER TABLE conversations ADD COLUMN user_metadata TEXT NOT NULL DEFAULT '{}';
"""

CREATE_CONVERSATIONS_IDX = """
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id, id);
"""

CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    start_time  TEXT    NOT NULL,
    end_time    TEXT,
    description TEXT    NOT NULL DEFAULT '',
    location    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_EVENTS_IDX = """
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_time);
"""

CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'todo',
    priority     TEXT    NOT NULL DEFAULT 'medium',
    due_date     TEXT,
    tags         TEXT    NOT NULL DEFAULT '[]',
    category     TEXT    NOT NULL DEFAULT 'personal',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
"""

CREATE_TASKS_IDX = """
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""

CREATE_TASKS_CATEGORY_IDX = """
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);
"""

CREATE_BUDGET_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS budget_transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    type          TEXT    NOT NULL,
    amount        REAL    NOT NULL,
    category      TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    date          TEXT    NOT NULL,
    recurring     TEXT    NOT NULL DEFAULT '',
    recurring_day INTEGER,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_BUDGET_IDX = """
CREATE INDEX IF NOT EXISTS idx_budget_date ON budget_transactions(date);
"""

CREATE_SAVINGS_GOALS_TABLE = """
CREATE TABLE IF NOT EXISTS savings_goals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    target_amount  REAL    NOT NULL,
    current_amount REAL    NOT NULL DEFAULT 0,
    deadline       TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


async def init_db(db_path: str) -> None:
    """
    Initialise the SQLite database.
    Creates the parent directory if it does not exist, then creates the
    memories and notes tables (along with indexes) if they are absent.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    logger.info("Initialising database at %s", db_path)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        await db.execute(CREATE_MEMORIES_TABLE)
        await db.execute(CREATE_NOTES_TABLE)
        await db.execute(CREATE_MEMORIES_FTS)
        await db.execute(CREATE_MEMORIES_IDX)
        await db.execute(CREATE_NOTES_IDX)
        await db.execute(CREATE_SESSIONS_TABLE)
        await db.execute(CREATE_CONVERSATIONS_TABLE)
        await db.execute(CREATE_CONVERSATIONS_IDX)
        await db.execute(CREATE_EVENTS_TABLE)
        await db.execute(CREATE_EVENTS_IDX)
        await db.execute(CREATE_TASKS_TABLE)
        await db.execute(CREATE_TASKS_IDX)

        # Migrate: add category column before creating its index
        try:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN category TEXT NOT NULL DEFAULT 'personal';"
            )
            await db.execute(
                """UPDATE tasks SET category = project
                   WHERE project IN ('groceries','work','career','finance','health','personal','home')
                   AND category = 'personal';"""
            )
        except Exception:
            pass  # column already exists — safe to ignore

        try:
            await db.execute(CREATE_TASKS_CATEGORY_IDX)
        except Exception:
            pass  # index already exists — safe to ignore

        await db.execute(CREATE_BUDGET_TRANSACTIONS_TABLE)
        await db.execute(CREATE_BUDGET_IDX)
        await db.execute(CREATE_SAVINGS_GOALS_TABLE)

        # Migrate: add metadata column if it doesn't exist yet
        try:
            await db.execute(MIGRATE_CONVERSATIONS_METADATA)
        except Exception:
            pass  # column already exists — safe to ignore

        # Migrate: add user_metadata column if it doesn't exist yet
        try:
            await db.execute(MIGRATE_CONVERSATIONS_USER_METADATA)
        except Exception:
            pass  # column already exists — safe to ignore

        # Migrate: drop the unique title index — id is the PK, titles can repeat
        try:
            await db.execute("DROP INDEX IF EXISTS idx_notes_title;")
        except Exception:
            pass

        # Migrate: add currency column to budget_transactions if it doesn't exist
        try:
            await db.execute(
                "ALTER TABLE budget_transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'TND';"
            )
        except Exception:
            pass  # column already exists — safe to ignore

        await db.commit()

    logger.info("Database initialised successfully.")


@asynccontextmanager
async def get_db_connection(db_path: str) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields an aiosqlite connection.

    Usage:
        async with get_db_connection(db_path) as db:
            rows = await db.execute("SELECT * FROM notes")
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        yield db
