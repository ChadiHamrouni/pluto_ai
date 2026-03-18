from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime

from agents import function_tool

from helpers.config_loader import load_config
from helpers.logger import get_logger

logger = get_logger(__name__)


def _get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _get_notes_dir() -> str:
    return load_config()["storage"]["notes_dir"]


def _sync_db_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80]


@function_tool
def create_note(title: str, content: str, category: str, tags: str) -> str:
    """
    Create a new markdown note, save it to disk, and record it in the database.

    Args:
        title:    Human-readable note title (must be unique).
        content:  Markdown body of the note.
        category: One of teaching, research, career, personal, ideas.
        tags:     Comma-separated list of tags.

    Returns:
        Confirmation string with the note ID and file path.
    """
    config = load_config()
    valid_categories = config["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)
    notes_dir = _get_notes_dir()
    db_path = _get_db_path()

    os.makedirs(notes_dir, exist_ok=True)

    slug = _slugify(title)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"{timestamp}-{slug}.md"
    file_path = os.path.join(notes_dir, filename)

    front_matter = (
        f"---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"tags: [{', '.join(tag_list)}]\n"
        f"created_at: {datetime.utcnow().isoformat()}\n"
        f"---\n\n"
    )
    full_content = front_matter + content

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        conn = _sync_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO notes (title, content, category, tags, created_at, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, content, category, tags_json, datetime.utcnow().isoformat(), file_path),
        )
        conn.commit()
        note_id = cursor.lastrowid
        conn.close()

        logger.info("Created note id=%d title='%s' path=%s", note_id, title, file_path)
        return f"Note created successfully. id={note_id}, file={file_path}"
    except sqlite3.IntegrityError:
        if os.path.exists(file_path):
            os.remove(file_path)
        return f"Error: a note with title '{title}' already exists."
    except Exception as exc:
        logger.error("Failed to create note: %s", exc)
        return f"Error creating note: {exc}"


@function_tool
def list_notes(category: str = "") -> str:
    """
    List all notes, optionally filtered by category.

    Args:
        category: Optional category filter (leave empty for all notes).

    Returns:
        JSON-encoded list of note summaries (id, title, category, tags, created_at).
    """
    db_path = _get_db_path()

    try:
        conn = _sync_db_connection(db_path)

        if category:
            cursor = conn.execute(
                "SELECT id, title, category, tags, created_at, file_path FROM notes WHERE category = ? ORDER BY created_at DESC",
                (category,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, title, category, tags, created_at, file_path FROM notes ORDER BY created_at DESC"
            )

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return json.dumps(rows if rows else [], default=str)
    except Exception as exc:
        logger.error("Failed to list notes: %s", exc)
        return f"Error listing notes: {exc}"


@function_tool
def get_note(title: str) -> str:
    """
    Retrieve the full content of a note by its title.

    Args:
        title: Exact (or partial) title of the note to retrieve.

    Returns:
        JSON-encoded note data, or an error message if not found.
    """
    db_path = _get_db_path()

    try:
        conn = _sync_db_connection(db_path)
        cursor = conn.execute(
            "SELECT * FROM notes WHERE title = ? LIMIT 1",
            (title,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            conn = _sync_db_connection(db_path)
            cursor = conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? LIMIT 1",
                (f"%{title}%",),
            )
            row = cursor.fetchone()
            conn.close()

        if row is None:
            return f"Note with title '{title}' not found."

        return json.dumps(dict(row), default=str)
    except Exception as exc:
        logger.error("Failed to get note: %s", exc)
        return f"Error retrieving note: {exc}"
