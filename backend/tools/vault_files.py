"""Vault file management @function_tool wrappers."""

from __future__ import annotations

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.vault_files import (
    append_vault_file as _append,
)
from helpers.tools.vault_files import (
    create_vault_file as _create,
)
from helpers.tools.vault_files import (
    delete_vault_file as _delete,
)
from helpers.tools.vault_files import (
    read_vault_file as _read,
)
from helpers.tools.vault_files import (
    search_vault as _search,
)

logger = get_logger(__name__)


@function_tool
def search_vault(query: str) -> str:
    """
    Search the user's Obsidian vault for files containing a keyword or phrase.

    Use this whenever the user asks a question that might be answered by something
    they've written in their vault — e.g. "what's my masters plan?", "find my notes
    on X", "what did I write about Y?". Searches all .md and .txt files by keyword
    and returns matching snippets with their file paths.

    Args:
        query: The keyword or phrase to search for (e.g. "masters plan", "thesis").

    Returns:
        Matching file paths with relevant snippet lines, or a message if nothing found.
    """
    try:
        hits = _search(query)
        if not hits:
            return f"No vault files found containing '{query}'."
        lines = [f"Found {len(hits)} file(s) matching '{query}':\n"]
        for h in hits:
            lines.append(f"## {h['file']}\n{h['snippet']}\n")
        return "\n".join(lines)
    except ValueError as exc:
        return f"Vault not configured: {exc}"
    except Exception as exc:
        logger.error("search_vault failed: %s", exc)
        return f"Failed to search vault: {exc}"


@function_tool
def read_vault_file(relative_path: str) -> str:
    """
    Read the full content of a specific file in the Obsidian vault.

    Use this when you know the file path (e.g. from search_vault results) and
    need the complete content to answer the user's question in detail.

    Args:
        relative_path: Path relative to the vault root (e.g. "Masters Plan.md",
                       "Projects/Thesis.md").

    Returns:
        The full file content as a string, or an error message.
    """
    try:
        content = _read(relative_path)
        return f"# {relative_path}\n\n{content}"
    except FileNotFoundError as exc:
        return str(exc)
    except ValueError as exc:
        return f"Vault not configured: {exc}"
    except Exception as exc:
        logger.error("read_vault_file failed: %s", exc)
        return f"Failed to read vault file: {exc}"


@function_tool
def create_vault_file(relative_path: str, content: str) -> str:
    """
    Create a new markdown file in the Obsidian vault (or overwrite an existing one).

    Use this when the user wants to save a new note, plan, or document directly
    to their vault. If the file already exists it will be fully replaced.

    Args:
        relative_path: Path relative to vault root (e.g. "Masters Plan.md",
                       "Projects/Research.md"). Parent folders are created automatically.
        content:       Full markdown content to write.

    Returns:
        The full path of the written file, or an error message.
    """
    try:
        path = _create(relative_path, content)
        return f"Vault file created: {path}"
    except ValueError as exc:
        return f"Vault not configured: {exc}"
    except Exception as exc:
        logger.error("create_vault_file failed: %s", exc)
        return f"Failed to create vault file: {exc}"


@function_tool
def append_vault_file(relative_path: str, content: str) -> str:
    """
    Append content to an existing vault file without overwriting it.

    Use this when the user wants to add to an existing note — e.g. "add this to
    my masters plan", "append a new section to Projects/Thesis.md". Creates the
    file if it doesn't exist yet.

    Args:
        relative_path: Path relative to vault root (e.g. "Masters Plan.md").
        content:       Markdown content to append (include a leading newline if needed).

    Returns:
        The full path of the file, or an error message.
    """
    try:
        path = _append(relative_path, content)
        return f"Appended to vault file: {path}"
    except ValueError as exc:
        return f"Vault not configured: {exc}"
    except Exception as exc:
        logger.error("append_vault_file failed: %s", exc)
        return f"Failed to append to vault file: {exc}"


@function_tool
def delete_vault_file(relative_path: str) -> str:
    """
    Permanently delete a file from the Obsidian vault.

    Use this only when the user explicitly asks to delete or remove a vault file.

    Args:
        relative_path: Path relative to vault root (e.g. "old-notes.md").

    Returns:
        Confirmation or error message.
    """
    try:
        deleted = _delete(relative_path)
        if deleted:
            return f"Deleted vault file: {relative_path}"
        return f"File not found in vault: {relative_path}"
    except ValueError as exc:
        return f"Vault not configured: {exc}"
    except Exception as exc:
        logger.error("delete_vault_file failed: %s", exc)
        return f"Failed to delete vault file: {exc}"
