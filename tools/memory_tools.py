from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from agents import function_tool

from helpers.config_loader import load_config
from helpers.logger import get_logger
from tools.rag_tools import embed_text, search_embeddings, store_embedding

logger = get_logger(__name__)


def _get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _get_embeddings_path() -> str:
    return load_config()["memory"]["embeddings_path"]


def _sync_db_connection(db_path: str) -> sqlite3.Connection:
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
    config = load_config()
    valid_categories = config["memory"]["categories"]
    if category not in valid_categories:
        return f"Error: invalid category '{category}'. Must be one of: {valid_categories}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    tags_json = json.dumps(tag_list)

    db_path = _get_db_path()
    embeddings_path = _get_embeddings_path()

    try:
        conn = _sync_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO memories (content, category, tags, created_at, relevance_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (content, category, tags_json, datetime.utcnow().isoformat(), 1.0),
        )
        conn.commit()
        entry_id = cursor.lastrowid
        conn.close()

        embedding = embed_text(content)
        store_embedding(entry_id, content, embedding, embeddings_path)

        logger.info("Stored memory entry id=%d category=%s", entry_id, category)
        return f"Memory stored successfully with id={entry_id}."
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return f"Error storing memory: {exc}"


def _search_memory_raw(query: str, category: str = "", top_k: int = 5) -> str:
    """Plain callable version — use this from Python code, not as an agent tool."""
    config = load_config()
    db_path = _get_db_path()
    embeddings_path = _get_embeddings_path()
    similarity_threshold = config["rag"]["similarity_threshold"]

    try:
        matching_ids = search_embeddings(
            query=query,
            top_k=top_k,
            embeddings_path=embeddings_path,
            similarity_threshold=similarity_threshold,
        )
        if not matching_ids:
            return json.dumps([])

        conn = _sync_db_connection(db_path)
        placeholders = ",".join("?" for _ in matching_ids)
        sql = f"SELECT * FROM memories WHERE id IN ({placeholders})"
        params: list = list(matching_ids)
        if category:
            sql += " AND category = ?"
            params.append(category)

        cursor = conn.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        id_order = {eid: idx for idx, eid in enumerate(matching_ids)}
        rows.sort(key=lambda r: id_order.get(r["id"], 999))
        return json.dumps(rows, default=str)
    except Exception as exc:
        logger.error("Failed to search memories: %s", exc)
        return f"Error searching memories: {exc}"


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
    return _search_memory_raw(query=query, category=category, top_k=top_k)


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
    import os

    db_path = _get_db_path()
    embeddings_path = _get_embeddings_path()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    try:
        conn = _sync_db_connection(db_path)

        cursor = conn.execute(
            "SELECT id FROM memories WHERE created_at < ? AND relevance_score < 0.5",
            (cutoff,),
        )
        ids_to_delete = [row["id"] for row in cursor.fetchall()]

        if not ids_to_delete:
            conn.close()
            return "No memories met the pruning criteria."

        placeholders = ",".join("?" for _ in ids_to_delete)
        conn.execute(
            f"DELETE FROM memories WHERE id IN ({placeholders})",
            ids_to_delete,
        )
        conn.commit()
        conn.close()

        removed_files = 0
        for entry_id in ids_to_delete:
            for ext in (".npy", ".json"):
                path = os.path.join(embeddings_path, f"{entry_id}{ext}")
                if os.path.exists(path):
                    os.remove(path)
                    removed_files += 1

        logger.info("Pruned %d memories older than %d days.", len(ids_to_delete), days)
        return (
            f"Pruned {len(ids_to_delete)} memory entries older than {days} days "
            f"(removed {removed_files} embedding files)."
        )
    except Exception as exc:
        logger.error("Failed to prune memories: %s", exc)
        return f"Error pruning memories: {exc}"
