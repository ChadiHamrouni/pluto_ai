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
    Create a new persistent markdown note, write it to disk, and index it in
    the database.

    Use this tool when the user asks to save, write down, take, or create a
    note — whether it's a reminder, a summary, research notes, a to-do list,
    or any free-form content they want to keep. Notes are richer and longer
    than memories; use store_memory for short facts, create_note for
    structured or multi-line content.

    The title is used to generate the filename slug, so it should be
    descriptive and unique. Duplicate titles will cause an error.

    Args:
        title:    REQUIRED. Human-readable title for the note. Used as the filename base.
                  Must be unique across all notes (e.g. "Meeting notes 2026-03-20").
                  Always provide this — the call will fail without it.
        content:  REQUIRED. Full markdown body of the note. May include headings,
                  bullet points, code blocks, etc.
        category: REQUIRED. Must be one of: teaching, research, career, personal, ideas.
        tags:     REQUIRED. Comma-separated keywords (e.g. "meeting,project-x,action-items").
                  Use empty string "" if no tags apply.

    Returns:
        Confirmation string with the assigned note id and the file path on
        disk, or an error message if the category is invalid or the write fails.
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
    List all saved notes, optionally filtered by category.

    Use this tool when the user asks to see, show, or list their notes —
    e.g. "what notes do I have?", "show my research notes". Returns summaries
    only (no full content). Use get_note to fetch the body of a specific note.

    Args:
        category: Optional category to filter by. Must be one of:
                  teaching, research, career, personal, ideas.
                  Leave empty (or pass "") to list all notes across all categories.

    Returns:
        JSON-encoded array of note summary objects, each containing:
        id, title, category, tags, created_at. Returns an empty array if no
        notes exist. Returns an error string on failure.
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

    Use this tool when the user asks to read, open, or see the contents of a
    specific note — e.g. "show me my meeting notes", "open the AI guardrails
    note". Call list_notes first if you need to discover available titles.
    Matching is partial, so a substring of the title is sufficient.

    Args:
        title: Full or partial title of the note to retrieve. Case-insensitive
               substring match is used (e.g. "guardrails" will match
               "AI Guardrails Research").

    Returns:
        JSON-encoded note object containing: id, title, content, category,
        tags, file_path, created_at. Returns a "not found" message if no
        match exists, or an error string on failure.
    """
    try:
        row = fetch_note_by_title(get_db_path(), title)
        if row is None:
            return f"Note with title '{title}' not found."
        return json.dumps(row, default=str)
    except Exception as exc:
        logger.error("Failed to get note: %s", exc)
        return f"Error retrieving note: {exc}"
