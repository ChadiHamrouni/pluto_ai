"""
Knowledge base ingestion job.

Scans all content directories and keeps ChromaDB perfectly in sync:
  - NEW files       → embedded and added
  - MODIFIED files  → re-embedded (old chunks replaced)
  - DELETED files   → chunks removed from ChromaDB

Content sources:
  - data/files/     — user-uploaded files      (content_type: "file")
  - data/notes/     — AI-generated notes       (content_type: "note")
  - data/memory/    — memory markdown files    (content_type: "memory")
  - ObsidianVault/  — Obsidian vault           (content_type: "obsidian", recursive)
"""

from __future__ import annotations

from pathlib import Path

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.core import knowledge_base as kb

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


async def run_ingestion() -> None:
    """
    Sync ChromaDB with the current state of all content directories.

    - Adds chunks for new files.
    - Re-embeds files whose mtime is newer than their stored ingestion timestamp.
    - Deletes chunks for files that no longer exist on disk.
    """
    cfg = load_config()
    obsidian_path = cfg.get("obsidian", {}).get("vault_path", "")

    # Only embed the Obsidian vault — other dirs (files, notes, memory) are excluded
    scan_targets: list[tuple[str, str, str, bool]] = []
    obsidian_ignored: set[str] = {
        name.lower()
        for name in cfg.get("obsidian", {}).get("ignored_folders", [])
    }

    # Directory names that should NEVER be embedded regardless of where they appear
    # in the vault tree (venvs, package caches, build artefacts, VCS internals, etc.)
    _ALWAYS_SKIP_DIRS: frozenset[str] = frozenset({
        "site-packages", "dist-packages",
        "node_modules",
        "__pycache__",
        ".git", ".svn", ".hg",
        ".venv", "venv", ".env", "env",
        "dist", "build", ".tox",
        ".mypy_cache", ".pytest_cache", ".ruff_cache",
        ".idea", ".vscode",
        "eggs", ".eggs",
    })

    if obsidian_path and Path(obsidian_path).exists():
        scan_targets.append((obsidian_path, "obsidian", "obsidian::", True))
        logger.info("Ingestion: scanning obsidian vault at %s", obsidian_path)
    elif obsidian_path:
        logger.warning("Ingestion: obsidian vault path not found: %s", obsidian_path)
    else:
        logger.info("Ingestion: no obsidian vault configured.")

    def _is_ignored(file_path: Path, vault_root: str) -> bool:
        """Return True if the file should be skipped.

        Skips files when:
        - They live inside a user-configured ignored top-level folder, OR
        - Any path segment matches a known dependency/build directory name.
        """
        try:
            rel = file_path.relative_to(vault_root)
        except ValueError:
            return False

        parts_lower = [p.lower() for p in rel.parts]

        # User-configured top-level folder exclusions
        if obsidian_ignored and parts_lower and parts_lower[0] in obsidian_ignored:
            return True

        # Always-skip directory names anywhere in the path
        return bool(_ALWAYS_SKIP_DIRS.intersection(parts_lower))

    # Build a map of source_key → file path for every file currently on disk
    # Source key uses relative path (not just filename) to avoid collisions across subfolders
    disk_files: dict[str, Path] = {}
    for dir_path, ctype_label, prefix, recursive in scan_targets:
        p = Path(dir_path)
        if not p.exists():
            logger.info("Ingestion: skipping missing dir [%s] %s", ctype_label, p)
            continue
        items = p.rglob("*") if recursive else p.iterdir()
        for f in items:
            if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if _is_ignored(f, obsidian_path):
                continue
            rel = f.relative_to(p).as_posix()  # e.g. "Slides/Streamlit_Workshop.pdf"
            disk_files[f"{prefix}{rel}"] = f

    logger.info("Ingestion: found %d files on disk to consider.", len(disk_files))
    for key in sorted(disk_files.keys()):
        logger.debug("  disk: %s", key)

    # Fetch what ChromaDB currently knows about — source_key → ingested_at timestamp
    ingested = kb.get_ingested_files_with_timestamps()

    total_added = total_updated = total_deleted = 0
    failed: list[str] = []

    # ── 1. Delete chunks for files no longer on disk ───────────────────────
    for source_key in list(ingested.keys()):
        if source_key not in disk_files:
            deleted = kb.delete_source(source_key)
            logger.info("  🗑  Removed %d stale chunks for deleted file: %s", deleted, source_key)
            total_deleted += 1

    # ── 2. Add new files / re-embed modified files ─────────────────────────
    for dir_path, ctype, prefix, recursive in scan_targets:
        p = Path(dir_path)
        if not p.exists():
            logger.debug("Ingestion job: skipping missing directory %s", p)
            continue

        items = p.rglob("*") if recursive else p.iterdir()
        for f in items:
            if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if _is_ignored(f, obsidian_path):
                continue

            rel = f.relative_to(p).as_posix()
            source_key = f"{prefix}{rel}"
            ingested_at = ingested.get(source_key)

            # New file
            if ingested_at is None:
                is_new = True
            else:
                # Modified: file mtime is newer than when it was last ingested
                is_new = f.stat().st_mtime > ingested_at

            if not is_new:
                continue

            try:
                logger.info("  → Embedding [%s]: %s", ctype, source_key)
                result = kb.ingest_file(str(f), content_type=ctype, source_key=source_key)
                logger.info(
                    "  ✓ %s [%s] — %d chunks (%d chars)",
                    result["filename"], ctype, result["chunks_stored"], result["total_chars"],
                )
                if ingested_at is None:
                    total_added += 1
                else:
                    total_updated += 1
            except Exception as exc:
                logger.warning("  ✗ Failed to ingest %s: %s", source_key, exc)
                failed.append(source_key)

    if total_added == 0 and total_updated == 0 and total_deleted == 0:
        logger.info("Ingestion job: everything is up to date.")
        return

    logger.info(
        "Ingestion complete — added: %d, updated: %d, deleted: %d, failed: %d",
        total_added, total_updated, total_deleted, len(failed),
    )
