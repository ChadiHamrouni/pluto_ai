"""
Nightly knowledge base ingestion job.

Scans data/files/ for supported documents (.txt, .md, .pdf) that have
not yet been ingested into ChromaDB, and ingests them in batch.

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
    Scan the files_path directory for new documents and ingest them into ChromaDB.

    Skips files already present in the collection (by filename).
    Logs a summary of what was ingested and any failures.
    """
    cfg = load_config()["knowledge_base"]
    files_path = Path(cfg.get("files_path", "data/files"))

    if not files_path.exists():
        logger.info("Ingestion job: files_path %s does not exist, skipping.", files_path)
        return

    already_ingested = kb.get_ingested_files()
    candidates = [
        f for f in files_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    new_files = [f for f in candidates if f.name not in already_ingested]

    if not new_files:
        logger.info("Ingestion job: no new files to ingest (checked %d files).", len(candidates))
        return

    logger.info(
        "Ingestion job: ingesting %d new file(s) out of %d total.",
        len(new_files), len(candidates),
    )

    total_chunks = 0
    failed = []

    for file in new_files:
        try:
            result = kb.ingest_file(str(file))
            total_chunks += result["chunks_stored"]
            logger.info(
                "  ✓ %s — %d chunks stored (%d chars)",
                result["filename"], result["chunks_stored"], result["total_chars"],
            )
        except Exception as exc:
            logger.warning("  ✗ Failed to ingest %s: %s", file.name, exc)
            failed.append(file.name)

    logger.info(
        "Ingestion job complete: %d file(s) ingested, %d chunk(s) total, %d failure(s).",
        len(new_files) - len(failed), total_chunks, len(failed),
    )
