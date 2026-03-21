from __future__ import annotations

import base64
import time
from pathlib import Path

import fitz  # PyMuPDF — already in requirements

from helpers.agents.runner import run_agent
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.results import HandlerResult
from my_agents.orchestrator import get_orchestrator

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_PDF_EXTS = {".pdf"}
_TEXT_EXTS = {".txt", ".md"}

# Docling converter is expensive to initialise — create it once and reuse.
_docling_converter = None


def _get_docling_converter():
    global _docling_converter
    if _docling_converter is None:
        from docling.document_converter import DocumentConverter

        _docling_converter = DocumentConverter()
    return _docling_converter


def _pdf_needs_vision(path: Path) -> bool:
    """
    Scan the PDF with PyMuPDF to decide whether vision OCR is needed.

    Returns True if:
      - Any page has no text layer (scanned/image-only page)
      - Any page has embedded images occupying >20% of page area
        (charts, figures, diagrams dominate)
    """
    doc = fitz.open(str(path))
    try:
        for page in doc:
            # No text layer at all → scanned page
            if not page.get_text("text").strip():
                logger.info("PDF page %d has no text layer → routing to GLM-OCR", page.number + 1)
                return True

            # Check image coverage on the page
            page_area = page.rect.width * page.rect.height
            if page_area == 0:
                continue
            image_area = sum((img["width"] * img["height"]) for img in page.get_image_info())
            coverage = image_area / page_area
            if coverage > 0.20:
                logger.info(
                    "PDF page %d has %.0f%% image coverage → routing to GLM-OCR",
                    page.number + 1,
                    coverage * 100,
                )
                return True
    finally:
        doc.close()
    return False


def _extract_pdf_docling(path: Path) -> str:
    """Extract PDF text via Docling (fast, good for text-heavy PDFs)."""
    converter = _get_docling_converter()
    result = converter.convert(str(path))
    markdown = result.document.export_to_markdown()
    return markdown.strip().strip("*").strip()


def _extract_pdf_glm_ocr(path: Path) -> str:
    """
    Extract PDF content via GLM-OCR page by page.
    Each page is rendered to PNG and sent to the glm-ocr Ollama model.
    Requires: ollama pull glm-ocr
    """
    import httpx

    config = load_config()
    ollama_base = config.get("ollama", {}).get("base_url", "http://localhost:11434")
    ocr_model = config.get("pdf", {}).get("ocr_model", "glm-ocr")

    doc = fitz.open(str(path))
    pages_text: list[str] = []

    try:
        for page in doc:
            # Render page to PNG at 150 DPI (good balance of quality vs speed)
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            b64_image = base64.b64encode(png_bytes).decode()

            prompt = (
                "Convert the document to markdown. Preserve all tables, headings, and structure."
            )

            payload = {
                "model": ocr_model,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
            }

            try:
                resp = httpx.post(
                    f"{ollama_base}/api/generate",
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                page_text = resp.json().get("response", "").strip()
                if page_text:
                    pages_text.append(f"<!-- Page {page.number + 1} -->\n{page_text}")
                    logger.info(
                        "GLM-OCR extracted %d chars from page %d", len(page_text), page.number + 1
                    )
            except Exception as exc:
                logger.warning("GLM-OCR failed on page %d: %s", page.number + 1, exc)
                # Fall back to raw PyMuPDF text for this page
                raw = page.get_text("text").strip()
                if raw:
                    pages_text.append(f"<!-- Page {page.number + 1} -->\n{raw}")
    finally:
        doc.close()

    return "\n\n".join(pages_text)


def _mime(ext: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


async def file_handler(
    message: str,
    history: list[dict],
    file_path: Path,
) -> HandlerResult:
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
            else f"Here is the content of the file:\n\n---\n\n{text_content}"
        )
        messages = [{"role": "user", "content": user_content}]
        result = await run_agent(get_orchestrator(), messages)
        return HandlerResult(
            response=result.response,
            elapsed=time.perf_counter() - t0,
            tools_used=result.tools_used,
            agents_trace=result.agents_trace,
        )

    if ext in _PDF_EXTS:
        use_vision = _pdf_needs_vision(file_path)

        if use_vision:
            logger.info("Routing PDF to GLM-OCR (visual content detected)")
            pdf_text = _extract_pdf_glm_ocr(file_path)
        else:
            logger.info("Routing PDF to Docling (text-heavy)")
            pdf_text = _extract_pdf_docling(file_path)

        if not pdf_text:
            raise ValueError("PDF contains no extractable content.")

        logger.info(
            "PDF extracted via %s: %d chars",
            "GLM-OCR" if use_vision else "Docling",
            len(pdf_text),
        )

        user_content = (
            f"{message}\n\n---\n\n{pdf_text}"
            if message and message.strip()
            else f"Summarise this document:\n\n---\n\n{pdf_text}"
        )
        messages: list[dict] = [{"role": "user", "content": user_content}]

    else:
        # Image file — send directly as vision input
        mime = _mime(ext)
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        user_text = message.strip() if message and message.strip() else "Describe this image."
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ]

    result = await run_agent(get_orchestrator(), messages)
    return HandlerResult(
        response=result.response,
        elapsed=time.perf_counter() - t0,
        tools_used=result.tools_used,
        agents_trace=result.agents_trace,
    )
