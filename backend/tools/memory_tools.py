from __future__ import annotations

import json

from agents import function_tool

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.memory import (
    delete_memory_by_id,
    delete_old_memories,
    get_db_path,
    insert_memory,
    search_memories,
)
from helpers.tools.memory_files import write_memory_md

logger = get_logger(__name__)


@function_tool
def store_memory(content: str, category: str, tags: str) -> str:
    """
    Save a fact about the user to persistent memory.

    Use this tool after any turn where the user shares something worth
    remembering long-term: a personal preference, a recurring context, a goal,
    a role, a constraint, or any detail that would help you serve them better
    in future conversations. Do NOT use this to save task progress or
    temporary state — only durable facts. Call silently without announcing it.

    One call per distinct fact. Keep content concise and self-contained so it
    reads clearly when injected into a future prompt with no extra context.

    Args:
        content:  Short factual statement to remember. Write in third person,
                  present tense (e.g. "User is a teaching assistant for CS101",
                  "User prefers bullet-point summaries over prose").
        category: Classification bucket. Must be one of:
                  teaching, research, career, personal, ideas.
        tags:     Comma-separated keywords for filtering
                  (e.g. "schedule,teaching,fall-semester").

    Returns:
        Confirmation string containing the assigned memory id on success,
        or an error message if the category is invalid or the write fails.
    """
    valid_categories = load_config()["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    try:
        entry_id = insert_memory(get_db_path(), content, category, tags_json)
        logger.info("Stored memory id=%d category=%s", entry_id, category)
        write_memory_md(entry_id, content, category, tag_list)
        return f"Memory stored (id={entry_id})."
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return f"Error storing memory: {exc}"


@function_tool
def forget_memory(memory_id: int) -> str:
    """
    Permanently delete a specific memory entry by its id.

    Use this tool when the user explicitly asks you to forget or remove
    something, or when they correct a previously stored fact and the old
    entry is now wrong. Do NOT call this proactively — only on explicit
    user instruction. Obtain the memory id from a prior store_memory
    confirmation or from context the user provides.

    Args:
        memory_id: The integer id of the memory entry to delete. This is
                   returned by store_memory when the memory was first saved.

    Returns:
        Confirmation that the entry was deleted, a "not found" message if
        no entry with that id exists, or an error message on failure.
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
    Bulk-delete all memory entries older than a given number of days.

    Use this tool only when the user explicitly asks to clean up, clear out,
    or prune their old memories. Do NOT call this automatically. If the user
    says "clean up my old memories" without specifying a threshold, use the
    default (0 triggers the config default, currently 90 days).

    Args:
        days: Age threshold in days. Entries created more than this many days
              ago will be deleted. Pass 0 to use the configured default
              (90 days). Must be a non-negative integer.

    Returns:
        A summary string stating how many entries were deleted, or a message
        saying nothing was old enough to prune, or an error on failure.
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


@function_tool
def search_memory(query: str) -> str:
    """
    Search stored memory facts using full-text search.

    Use this tool when the user asks "do you remember…?", "what do you know
    about…?", or any question whose answer might be stored in memory. Also
    use it before storing a new fact to avoid duplicates.

    The search is powered by SQLite FTS5 (BM25 ranking) and falls back to
    the most-recently stored facts when no FTS match is found.

    Args:
        query: Keywords or a short phrase describing what to look for.
               Examples: "job title", "preferred language", "savings goal".

    Returns:
        A formatted list of matching memory facts (content, category, tags),
        or a message stating no relevant memories were found.
    """
    top_k = load_config()["memory"].get("search_top_k", 10)
    try:
        results = search_memories(get_db_path(), query, top_k=top_k)
    except Exception as exc:
        logger.error("Memory search failed: %s", exc)
        return f"Error searching memory: {exc}"

    if not results:
        return "No memories found matching that query."

    lines = [f"Found {len(results)} memory fact(s) for '{query}':"]
    for mem in results:
        tags = mem.get("tags", "[]")
        lines.append(
            f"- [id={mem['id']}] ({mem['category']}) {mem['content']}"
            + (f"  tags={tags}" if tags and tags != "[]" else "")
        )
    return "\n".join(lines)
