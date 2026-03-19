"""File-first Markdown memory — writes each memory fact as a .md file.

Every memory also lives in SQLite (source of truth for queries).
The .md files provide transparency, git-trackability, and a human-readable audit trail.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def _memory_dir() -> str:
    return load_config()["memory"].get("memory_dir", "data/memory")


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:max_len]


def write_memory_md(memory_id: int, content: str, category: str, tags: list[str]) -> str:
    """Write a memory fact to data/memory/{category}/YYYYMMDD-slug.md.

    Returns the file path written, or empty string on failure.
    """
    base = _memory_dir()
    cat_dir = os.path.join(base, category)
    os.makedirs(cat_dir, exist_ok=True)

    date_str = datetime.utcnow().strftime("%Y%m%d")
    slug = _slugify(content)
    filename = f"{date_str}-{slug}.md"
    path = os.path.join(cat_dir, filename)

    tags_yaml = ", ".join(tags) if tags else ""
    frontmatter = (
        f"---\n"
        f"id: {memory_id}\n"
        f"category: {category}\n"
        f"tags: [{tags_yaml}]\n"
        f"created_at: {datetime.utcnow().isoformat()}\n"
        f"---\n\n"
        f"{content}\n"
    )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
        logger.debug("Wrote memory md: %s", path)
        return path
    except Exception as exc:
        logger.warning("Failed to write memory md: %s", exc)
        return ""


def write_daily_note(entries: list[str]) -> str:
    """Append session learnings to data/memory/daily/YYYY-MM-DD.md.

    Returns the file path, or empty string on failure.
    """
    if not entries:
        return ""

    base = _memory_dir()
    daily_dir = os.path.join(base, "daily")
    os.makedirs(daily_dir, exist_ok=True)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(daily_dir, f"{date_str}.md")

    now = datetime.utcnow().strftime("%H:%M:%S")
    lines = [f"\n## Session entry — {now}\n"]
    for entry in entries:
        lines.append(f"- {entry}")
    lines.append("")

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
    except Exception as exc:
        logger.warning("Failed to write daily note: %s", exc)
        return ""


def build_memory_index() -> str:
    """Regenerate data/memory/MEMORY.md as a curated index of all memory files.

    Returns the path to the index file.
    """
    base = _memory_dir()
    index_path = os.path.join(base, "MEMORY.md")

    lines = ["# Memory Index\n", f"*Updated: {datetime.utcnow().isoformat()}*\n"]

    for category in sorted(os.listdir(base)):
        cat_dir = os.path.join(base, category)
        if not os.path.isdir(cat_dir) or category == "daily":
            continue

        md_files = sorted(
            [f for f in os.listdir(cat_dir) if f.endswith(".md")],
            reverse=True,
        )
        if not md_files:
            continue

        lines.append(f"\n## {category.capitalize()}\n")
        for fname in md_files:
            fpath = os.path.join(cat_dir, fname)
            # Extract first non-frontmatter line as preview
            preview = _extract_preview(fpath)
            lines.append(f"- [{fname}]({category}/{fname}) — {preview}")

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return index_path
    except Exception as exc:
        logger.warning("Failed to write memory index: %s", exc)
        return ""


def _extract_preview(path: str) -> str:
    """Return first content line after frontmatter."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Strip YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else content
        else:
            body = content.strip()
        first_line = body.split("\n")[0].strip()
        return first_line[:80] if first_line else "(empty)"
    except Exception:
        return "(unreadable)"
