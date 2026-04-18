"""Helper functions for note persistence (DB + filesystem)."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def get_notes_dir() -> str:
    return load_config()["storage"]["notes_dir"]


def sync_db_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80]


def write_note_file(
    notes_dir: str, title: str, content: str, category: str, tag_list: list[str]
) -> str:
    """Write the markdown file with YAML front matter. Returns the file path."""
    os.makedirs(notes_dir, exist_ok=True)
    slug = slugify(title)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    file_path = os.path.join(notes_dir, f"{timestamp}-{slug}.md")

    front_matter = (
        f"---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"tags: [{', '.join(tag_list)}]\n"
        f"created_at: {datetime.utcnow().isoformat()}\n"
        f"---\n\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(front_matter + content)

    return file_path


def insert_note_db(
    db_path: str, title: str, content: str, category: str, tags_json: str, file_path: str
) -> int:
    """Insert note record into DB. Returns the new row id."""
    conn = sync_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (title, content, category, tags, created_at, file_path)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (title, content, category, tags_json, datetime.utcnow().isoformat(), file_path),
    )
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id


def query_notes(db_path: str, category: str = "") -> list[dict]:
    conn = sync_db_connection(db_path)
    if category:
        cursor = conn.execute(
            "SELECT id, title, category, tags, created_at, file_path FROM notes"
            " WHERE category = ? ORDER BY created_at DESC",
            (category,),
        )
    else:
        cursor = conn.execute(
            "SELECT id, title, category, tags, created_at, file_path FROM notes"
            " ORDER BY created_at DESC"
        )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def create_notes_batch(
    db_path: str,
    notes_dir: str,
    notes: list[dict],
) -> list[dict]:
    """Write multiple notes atomically (file + DB).
    Each dict must have 'title', 'content', 'category'. Optional: tags (list[str]), idempotency_key.
    Returns list of result dicts with status='created'|'skipped'.
    """
    import hashlib, json as _json

    results: list[dict] = []
    conn = sync_db_connection(db_path)
    try:
        for item in notes:
            idem_key = item.get("idempotency_key", "")
            if idem_key:
                existing = conn.execute(
                    "SELECT id FROM notes WHERE idempotency_key = ? LIMIT 1",
                    (idem_key,),
                ).fetchone()
                if existing:
                    results.append({"status": "skipped", "id": existing["id"], "idempotency_key": idem_key})
                    continue

            tag_list = item.get("tags", [])
            if isinstance(tag_list, str):
                tag_list = [t.strip() for t in tag_list.split(",") if t.strip()]
            tags_json = _json.dumps(tag_list)

            file_path = write_note_file(notes_dir, item["title"], item["content"], item["category"], tag_list)
            cursor = conn.execute(
                "INSERT INTO notes (title, content, category, tags, created_at, file_path, idempotency_key)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item["title"], item["content"], item["category"], tags_json,
                 datetime.utcnow().isoformat(), file_path, idem_key),
            )
            results.append({
                "status": "created",
                "id": cursor.lastrowid,
                "title": item["title"],
                "file_path": file_path,
                "idempotency_key": idem_key,
            })
            logger.info("Batch created note id=%d title='%s'", cursor.lastrowid, item["title"])
        conn.commit()
    finally:
        conn.close()
    return results


def fetch_note_by_title(db_path: str, title: str) -> dict | None:
    conn = sync_db_connection(db_path)
    row = conn.execute("SELECT * FROM notes WHERE title = ? LIMIT 1", (title,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM notes WHERE title LIKE ? LIMIT 1", (f"%{title}%",)
        ).fetchone()
    conn.close()
    return dict(row) if row else None
