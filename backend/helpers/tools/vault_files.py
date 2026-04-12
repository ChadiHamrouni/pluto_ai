"""Helper functions for reading, searching, and deleting arbitrary vault files."""

from __future__ import annotations

import os
from pathlib import Path

from helpers.core.logger import get_logger
from helpers.tools.obsidian import get_vault_path, write_vault_file

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt"}


def _resolve_safe(vault_path: str, relative_path: str) -> Path:
    """Resolve relative_path inside vault_path and guard against traversal."""
    base = Path(vault_path).resolve()
    full = (base / relative_path).resolve()
    if not str(full).startswith(str(base)):
        raise ValueError("Path escapes the vault directory.")
    return full


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_vault(query: str, max_results: int = 10) -> list[dict]:
    """
    Keyword search across all .md and .txt files in the vault.

    Returns a list of dicts:
        {"file": relative_path, "snippet": matched_lines}
    sorted by number of matches descending.
    """
    vault_path = get_vault_path()
    base = Path(vault_path).resolve()
    query_lower = query.lower()
    hits: list[tuple[int, str, str]] = []  # (match_count, rel_path, snippet)

    for filepath in base.rglob("*"):
        if not filepath.is_file() or filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        # Skip hidden dirs / common noise
        if any(p.startswith(".") for p in filepath.parts):
            continue
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        matching_lines = [
            line.strip()
            for line in text.splitlines()
            if query_lower in line.lower()
        ]
        if not matching_lines:
            continue

        snippet = "\n".join(matching_lines[:5])
        rel = str(filepath.relative_to(base))
        hits.append((len(matching_lines), rel, snippet))

    hits.sort(key=lambda x: x[0], reverse=True)
    return [{"file": h[1], "snippet": h[2]} for h in hits[:max_results]]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_vault_file(relative_path: str) -> str:
    """Read and return the full content of a vault file."""
    vault_path = get_vault_path()
    full = _resolve_safe(vault_path, relative_path)
    if not full.exists():
        raise FileNotFoundError(f"File not found in vault: {relative_path}")
    return full.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Create / overwrite
# ---------------------------------------------------------------------------

def create_vault_file(relative_path: str, content: str) -> str:
    """Write content to a vault file, creating it (or overwriting it). Returns full path."""
    vault_path = get_vault_path()
    return write_vault_file(vault_path, relative_path, content)


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------

def append_vault_file(relative_path: str, content: str) -> str:
    """Append content to an existing vault file. Creates the file if it doesn't exist."""
    vault_path = get_vault_path()
    full = _resolve_safe(vault_path, relative_path)
    os.makedirs(full.parent, exist_ok=True)
    with open(full, "a", encoding="utf-8") as f:
        f.write(content)
    logger.info("Vault file appended: %s", full)
    return str(full)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_vault_file(relative_path: str) -> bool:
    """Delete a vault file. Returns True if deleted, False if it didn't exist."""
    vault_path = get_vault_path()
    full = _resolve_safe(vault_path, relative_path)
    if not full.exists():
        return False
    full.unlink()
    logger.info("Vault file deleted: %s", full)
    return True
