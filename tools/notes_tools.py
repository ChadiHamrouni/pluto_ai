from __future__ import annotations

import json

from agents import function_tool

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.notes import (
    fetch_note_by_title,
    get_db_path,
    get_notes_dir,
    insert_note_db,
    query_notes,
    write_note_file,
)

logger = get_logger(__name__)


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
    valid_categories = load_config()["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        file_path = write_note_file(get_notes_dir(), title, content, category, tag_list)
        note_id = insert_note_db(get_db_path(), title, content, category, tags_json, file_path)
        logger.info("Created note id=%d title='%s' path=%s", note_id, title, file_path)
        return f"Note created successfully. id={note_id}, file={file_path}"
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
    try:
        rows = query_notes(get_db_path(), category)
        return json.dumps(rows, default=str)
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
    try:
        row = fetch_note_by_title(get_db_path(), title)
        if row is None:
            return f"Note with title '{title}' not found."
        return json.dumps(row, default=str)
    except Exception as exc:
        logger.error("Failed to get note: %s", exc)
        return f"Error retrieving note: {exc}"
