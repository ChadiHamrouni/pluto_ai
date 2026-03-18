from __future__ import annotations

from agents import function_tool

from helpers.config_loader import load_config
from helpers.logger import get_logger
from helpers.memory import (
    delete_old_memories,
    get_db_path,
    get_embeddings_path,
    insert_memory,
    search_memories,
)

logger = get_logger(__name__)


@function_tool
def store_memory(content: str, category: str, tags: str) -> str:
    """
    Store a new memory entry in the SQLite database and persist its embedding.

    Args:
        content:  The text content to remember.
        category: One of teaching, research, career, personal, ideas.
        tags:     Comma-separated list of tags (e.g. "python,async,tips").

    Returns:
        A confirmation string with the new entry ID.
    """
    import json

    valid_categories = load_config()["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        entry_id = insert_memory(get_db_path(), get_embeddings_path(), content, category, tags_json)
        logger.info("Stored memory entry id=%d category=%s", entry_id, category)
        return f"Memory stored successfully with id={entry_id}."
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return f"Error storing memory: {exc}"


@function_tool
def search_memory(query: str, category: str = "", top_k: int = 5) -> str:
    """
    Search stored memories for entries semantically similar to the query.

    Args:
        query:    Natural-language search query.
        category: Optional category filter.
        top_k:    Maximum number of results to return (default 5).

    Returns:
        JSON-encoded list of matching memory entries.
    """
    try:
        return search_memories(query=query, category=category, top_k=top_k)
    except Exception as exc:
        logger.error("Failed to search memories: %s", exc)
        return f"Error searching memories: {exc}"


@function_tool
def prune_memory(days: int = 90) -> str:
    """
    Remove memory entries older than *days* days that have low relevance.

    Entries with relevance_score < 0.5 created more than *days* days ago
    are deleted from both the database and the embeddings directory.

    Args:
        days: Age threshold in days (default 90).

    Returns:
        A summary of how many entries were pruned.
    """
    try:
        deleted, files_removed = delete_old_memories(get_db_path(), get_embeddings_path(), days)
        if deleted == 0:
            return "No memories met the pruning criteria."
        logger.info("Pruned %d memories older than %d days.", deleted, days)
        return f"Pruned {deleted} memory entries older than {days} days (removed {files_removed} embedding files)."
    except Exception as exc:
        logger.error("Failed to prune memories: %s", exc)
        return f"Error pruning memories: {exc}"
