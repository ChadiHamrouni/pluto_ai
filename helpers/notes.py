"""Helper functions for note persistence (DB + filesystem)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime

from helpers.config_loader import load_config
from helpers.logger import get_logger

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


def write_note_file(notes_dir: str, title: str, content: str, category: str, tag_list: list[str]) -> str:
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


def insert_note_db(db_path: str, title: str, content: str, category: str, tags_json: str, file_path: str) -> int:
    """Insert note record into DB. Returns the new row id."""
    conn = sync_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (title, content, category, tags, created_at, file_path) VALUES (?, ?, ?, ?, ?, ?)",
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
            "SELECT id, title, category, tags, created_at, file_path FROM notes WHERE category = ? ORDER BY created_at DESC",
            (category,),
        )
    else:
        cursor = conn.execute(
            "SELECT id, title, category, tags, created_at, file_path FROM notes ORDER BY created_at DESC"
        )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def fetch_note_by_title(db_path: str, title: str) -> dict | None:
    conn = sync_db_connection(db_path)
    row = conn.execute("SELECT * FROM notes WHERE title = ? LIMIT 1", (title,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM notes WHERE title LIKE ? LIMIT 1", (f"%{title}%",)).fetchone()
    conn.close()
    return dict(row) if row else None
