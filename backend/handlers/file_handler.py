from __future__ import annotations

import base64
import time
from pathlib import Path

import fitz  # pymupdf

from my_agents.orchestrator import get_orchestrator
from helpers.agents.runner import run_agent
from helpers.core.logger import get_logger
from models.chat import ChatMessage

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_PDF_EXTS   = {".pdf"}


def _extract_pdf_text(path: Path) -> str:
    doc = fitz.open(str(path))
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            pages.append(f"[Page {i}]\n{text}")
    doc.close()

    if not pages:
        raise ValueError("PDF contains no extractable text (may be scanned/image-only).")

    return "\n\n".join(pages)


def _mime(ext: str) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
        ".gif": "image/gif",  ".bmp": "image/bmp",
    }.get(ext, "image/png")


async def file_handler(
    message: str,
    history: list[ChatMessage],
    file_path: Path,
) -> tuple[str, float]:
    t0 = time.perf_counter()

    ext = file_path.suffix.lower()
    if ext not in _IMAGE_EXTS | _PDF_EXTS:
        raise ValueError(f"Unsupported file type: {ext}")

    logger.info("File handler: %s (%d bytes)", file_path.name, file_path.stat().st_size)

    if ext in _PDF_EXTS:
        pdf_text = _extract_pdf_text(file_path)
        logger.info("Extracted %d chars from PDF (%d pages)", len(pdf_text), pdf_text.count("[Page "))
        user_content = (
            f"{message}\n\n---\n\n{pdf_text}"
            if message
            else f"Summarise this document:\n\n---\n\n{pdf_text}"
        )
        messages: list[dict] = [{"role": "user", "content": user_content}]

    else:
        mime = _mime(ext)
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": message or "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}]

    response = await run_agent(get_orchestrator(), messages)
    return response, time.perf_counter() - t0
