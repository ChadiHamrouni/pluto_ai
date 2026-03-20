from __future__ import annotations

import base64
import time
from pathlib import Path

from my_agents.orchestrator import get_orchestrator
from helpers.agents.runner import run_agent
from helpers.core.logger import get_logger

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_PDF_EXTS   = {".pdf"}
_TEXT_EXTS  = {".txt"}

# Docling converter is expensive to initialise — create it once and reuse.
_docling_converter = None


def _get_docling_converter():
    global _docling_converter
    if _docling_converter is None:
        from docling.document_converter import DocumentConverter
        _docling_converter = DocumentConverter()
    return _docling_converter


def _extract_pdf_text(path: Path) -> str:
    """
    Convert a PDF to clean Markdown using Docling.

    Docling uses ML-based layout detection and table structure recognition,
    preserving headings, tables, reading order, and (optionally) OCR for
    scanned pages — producing much better LLM input than raw pymupdf text.
    """
    converter = _get_docling_converter()
    result = converter.convert(str(path))
    markdown = result.document.export_to_markdown()
    if not markdown.strip():
        raise ValueError("PDF contains no extractable content (may be scanned/image-only with OCR disabled).")
    return markdown


def _mime(ext: str) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
        ".gif": "image/gif",  ".bmp": "image/bmp",
    }.get(ext, "image/png")


async def file_handler(
    message: str,
    history: list[dict],
    file_path: Path,
) -> tuple[str, float, list[str]]:
    t0 = time.perf_counter()

    ext = file_path.suffix.lower()
    if ext not in _IMAGE_EXTS | _PDF_EXTS | _TEXT_EXTS:
        raise ValueError(f"Unsupported file type: {ext}")

    logger.info("File handler: %s (%d bytes)", file_path.name, file_path.stat().st_size)

    if ext in _TEXT_EXTS:
        text_content = file_path.read_text(encoding="utf-8", errors="replace")
        user_content = (
            f"{message}\n\n---\n\n{text_content}"
            if message and message.strip()
            else f"Here is the content of the text file:\n\n---\n\n{text_content}"
        )
        messages = [{"role": "user", "content": user_content}]
        response, tools_used, agents_trace = await run_agent(get_orchestrator(), messages)
        return response, time.perf_counter() - t0, tools_used, agents_trace

    if ext in _PDF_EXTS:
        pdf_text = _extract_pdf_text(file_path)
        # Strip markdown noise — Docling sometimes returns "*" or whitespace-only output
        pdf_text_clean = pdf_text.strip().strip("*").strip()
        if not pdf_text_clean:
            raise ValueError("PDF contains no extractable text content.")
        logger.info("Extracted %d chars from PDF via Docling", len(pdf_text_clean))
        user_content = (
            f"{message}\n\n---\n\n{pdf_text_clean}"
            if message.strip()
            else f"Summarise this document:\n\n---\n\n{pdf_text_clean}"
        )
        messages: list[dict] = [{"role": "user", "content": user_content}]

    else:
        mime = _mime(ext)
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        user_text = message.strip() if message and message.strip() else "Describe this image."
        messages = [{"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}]

    response, tools_used, agents_trace = await run_agent(get_orchestrator(), messages)
    return response, time.perf_counter() - t0, tools_used, agents_trace
