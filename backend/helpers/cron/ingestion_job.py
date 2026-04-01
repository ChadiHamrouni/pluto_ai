"""
Nightly knowledge base ingestion job.

Scans multiple content directories for supported documents (.txt, .md, .pdf)
that have not yet been ingested into ChromaDB, and ingests them in batch.

Content sources:
  - data/files/           — user-uploaded files (content_type: "file")
  - data/notes/           — AI-generated markdown notes (content_type: "note")
  - data/memory/          — personal memory markdown files (content_type: "memory")
  - ObsidianVault/        — Obsidian vault (content_type: "obsidian", recursive)

This job is designed to run while the system is idle (e.g. 3:00 AM)
so VRAM is not contested with active LLM inference.
"""

from __future__ import annotations

from pathlib import Path

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools import knowledge_base as kb

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


async def run_ingestion() -> None:
    """
    Scan all content directories for new documents and ingest them into ChromaDB.

    Skips files already present in the collection (by source key).
    Logs a summary of what was ingested and any failures.
    """
    cfg = load_config()
    cfg_kb = cfg["knowledge_base"]
    cfg_storage = cfg["storage"]
    cfg_memory = cfg.get("memory", {})
    obsidian_path = cfg.get("obsidian", {}).get("vault_path", "")

    # Build scan targets: (directory, content_type, source_prefix, recursive)
    scan_targets: list[tuple[str, str, str, bool]] = [
        (cfg_kb.get("files_path", "data/files"),           "file",     "",           False),
        (cfg_storage.get("notes_dir", "data/notes"),       "note",     "",           False),
        (cfg_memory.get("memory_dir", "data/memory"),      "memory",   "",           False),
    ]
    if obsidian_path and Path(obsidian_path).exists():
        scan_targets.append((obsidian_path, "obsidian", "obsidian::", True))

    already_ingested = kb.get_ingested_files()

    total_new = 0
    total_chunks = 0
    failed: list[str] = []

    for dir_path, ctype, prefix, recursive in scan_targets:
        p = Path(dir_path)
        if not p.exists():
            logger.debug("Ingestion job: skipping missing directory %s", p)
            continue

        items = p.rglob("*") if recursive else p.iterdir()
        for f in items:
            if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            source_key = f"{prefix}{f.name}"
            if source_key in already_ingested:
                continue

            total_new += 1
            try:
                result = kb.ingest_file(str(f), content_type=ctype, source_prefix=prefix)
                total_chunks += result["chunks_stored"]
                logger.info(
                    "  ✓ %s [%s] — %d chunks (%d chars)",
                    result["filename"], ctype, result["chunks_stored"], result["total_chars"],
                )
            except Exception as exc:
                logger.warning("  ✗ Failed to ingest %s: %s", source_key, exc)
                failed.append(source_key)

    if total_new == 0:
        logger.info("Ingestion job: no new files to ingest.")
        return

    logger.info(
        "Ingestion job complete: %d file(s) ingested, %d chunk(s) total, %d failure(s).",
        total_new - len(failed), total_chunks, len(failed),
    )
