from __future__ import annotations

import json

from agents import function_tool

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.memory import delete_memory_by_id, delete_old_memories, get_db_path, insert_memory

logger = get_logger(__name__)


@function_tool
def store_memory(content: str, category: str, tags: str) -> str:
    """
    Save a fact about the user to persistent memory.

    Call this silently after any turn where the user shares something worth
    remembering: a preference, goal, personal detail, or recurring context.
    Keep content concise and factual — one idea per entry.

    Args:
        content:  Short factual statement to remember (e.g. "User is a TA").
        category: One of teaching, research, career, personal, ideas.
        tags:     Comma-separated tags (e.g. "schedule,teaching").

    Returns:
        Confirmation with the new memory id.
    """
    valid_categories = load_config()["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        entry_id = insert_memory(get_db_path(), content, category, tags_json)
        logger.info("Stored memory id=%d category=%s", entry_id, category)
        return f"Memory stored (id={entry_id})."
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return f"Error storing memory: {exc}"


@function_tool
def forget_memory(memory_id: int) -> str:
    """
    Delete a specific memory entry by its id.

    Use this when the user explicitly asks to forget something or when a
    stored fact is no longer accurate (e.g. user corrects a previous statement).

    Args:
        memory_id: The integer id of the memory to delete.

    Returns:
        Confirmation or error message.
    """
    try:
        deleted = delete_memory_by_id(get_db_path(), memory_id)
        if deleted:
            logger.info("Deleted memory id=%d", memory_id)
            return f"Memory {memory_id} forgotten."
        return f"No memory found with id={memory_id}."
    except Exception as exc:
        logger.error("Failed to forget memory: %s", exc)
        return f"Error deleting memory: {exc}"


@function_tool
def prune_memory(days: int = 0) -> str:
    """
    Delete all memory entries older than *days* days.

    Call this only when the user explicitly asks to clean up old memories.

    Args:
        days: Age threshold in days (default 90).

    Returns:
        A summary of how many entries were deleted.
    """
    if days == 0:
        days = load_config()["memory"].get("default_prune_threshold_days", 90)
    try:
        deleted = delete_old_memories(get_db_path(), days)
        if deleted == 0:
            return "No memories older than the threshold found."
        logger.info("Pruned %d memories older than %d days.", deleted, days)
        return f"Pruned {deleted} memory entries older than {days} days."
    except Exception as exc:
        logger.error("Failed to prune memories: %s", exc)
        return f"Error pruning memories: {exc}"
