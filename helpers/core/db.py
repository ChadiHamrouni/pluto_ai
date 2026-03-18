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

CREATE_MEMORIES_IDX = """
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
"""

CREATE_NOTES_IDX = """
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
"""

CREATE_NOTES_TITLE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
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
        await db.execute(CREATE_MEMORIES_IDX)
        await db.execute(CREATE_NOTES_IDX)
        await db.execute(CREATE_NOTES_TITLE_IDX)

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
