"""Helper functions for memory persistence (DB + embeddings)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta

from helpers.config_loader import load_config
from helpers.logger import get_logger
from tools.rag_tools import embed_text, search_embeddings, store_embedding

logger = get_logger(__name__)


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def get_embeddings_path() -> str:
    return load_config()["memory"]["embeddings_path"]


def sync_db_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def insert_memory(db_path: str, embeddings_path: str, content: str, category: str, tags_json: str) -> int:
    """Insert memory into DB, embed it, and persist the embedding. Returns entry id."""
    conn = sync_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO memories (content, category, tags, created_at, relevance_score) VALUES (?, ?, ?, ?, ?)",
        (content, category, tags_json, datetime.utcnow().isoformat(), 1.0),
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()

    embedding = embed_text(content)
    store_embedding(entry_id, content, embedding, embeddings_path)
    return entry_id


def search_memories(query: str, category: str = "", top_k: int = 5) -> str:
    """Semantic search over stored memories. Returns JSON string."""
    config = load_config()
    db_path = get_db_path()
    embeddings_path = get_embeddings_path()
    similarity_threshold = config["rag"]["similarity_threshold"]

    matching_ids = search_embeddings(
        query=query,
        top_k=top_k,
        embeddings_path=embeddings_path,
        similarity_threshold=similarity_threshold,
    )
    if not matching_ids:
        return json.dumps([])

    conn = sync_db_connection(db_path)
    placeholders = ",".join("?" for _ in matching_ids)
    sql = f"SELECT * FROM memories WHERE id IN ({placeholders})"
    params: list = list(matching_ids)
    if category:
        sql += " AND category = ?"
        params.append(category)

    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    conn.close()

    id_order = {eid: idx for idx, eid in enumerate(matching_ids)}
    rows.sort(key=lambda r: id_order.get(r["id"], 999))
    return json.dumps(rows, default=str)


def delete_old_memories(db_path: str, embeddings_path: str, days: int) -> tuple[int, int]:
    """Delete low-relevance memories older than *days*. Returns (entries_deleted, files_removed)."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = sync_db_connection(db_path)

    ids_to_delete = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM memories WHERE created_at < ? AND relevance_score < 0.5",
            (cutoff,),
        ).fetchall()
    ]

    if not ids_to_delete:
        conn.close()
        return 0, 0

    placeholders = ",".join("?" for _ in ids_to_delete)
    conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids_to_delete)
    conn.commit()
    conn.close()

    removed_files = 0
    for entry_id in ids_to_delete:
        for ext in (".npy", ".json"):
            path = os.path.join(embeddings_path, f"{entry_id}{ext}")
            if os.path.exists(path):
                os.remove(path)
                removed_files += 1

    return len(ids_to_delete), removed_files
