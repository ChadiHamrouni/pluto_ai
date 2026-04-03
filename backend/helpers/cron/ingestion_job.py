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

    if obsidian_path and Path(obsidian_path).exists():
        scan_targets.append((obsidian_path, "obsidian", "obsidian::", True))

    def _is_ignored(file_path: Path, vault_root: str) -> bool:
        """Return True if the file lives inside an Obsidian ignored folder."""
        if not obsidian_ignored or not vault_root:
            return False
        try:
            rel = file_path.relative_to(vault_root)
            return rel.parts[0].lower() in obsidian_ignored if rel.parts else False
        except ValueError:
            return False

    # Build a map of source_key → file path for every file currently on disk
    # Source key uses relative path (not just filename) to avoid collisions across subfolders
    disk_files: dict[str, Path] = {}
    for dir_path, _, prefix, recursive in scan_targets:
        p = Path(dir_path)
        if not p.exists():
            continue
        items = p.rglob("*") if recursive else p.iterdir()
        for f in items:
            if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if _is_ignored(f, obsidian_path):
                continue
            rel = f.relative_to(p).as_posix()  # e.g. "Slides/Streamlit_Workshop.pdf"
            disk_files[f"{prefix}{rel}"] = f

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
