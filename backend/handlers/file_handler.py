from __future__ import annotations

import base64
import re
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

def _page_needs_vision(page: fitz.Page) -> bool:
    """Return True if this page should be processed with GLM-OCR instead of PyMuPDF."""
    if not page.get_text("text").strip():
        return True
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False
    image_area = sum(img["width"] * img["height"] for img in page.get_image_info())
    return (image_area / page_area) > 0.20


def _ocr_page_glm(page: fitz.Page, ollama_base: str, ocr_model: str) -> str:
    """Render one page to PNG and send to GLM-OCR. Returns extracted text or ''."""
    import httpx

    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page.get_pixmap(matrix=mat)
    b64_image = base64.b64encode(pix.tobytes("png")).decode()

    payload = {
        "model": ocr_model,
        "prompt": "Convert the document to markdown. Preserve all tables, headings, and structure.",
        "images": [b64_image],
        "stream": False,
    }
    try:
        resp = httpx.post(f"{ollama_base}/api/generate", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        logger.warning("GLM-OCR failed on page %d: %s", page.number + 1, exc)
        return ""


def _clean_text(text: str) -> str:
    """Normalize raw PDF text: collapse whitespace, fix broken lines."""
    # Collapse runs of spaces/tabs
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Remove hyphenation at line breaks (e.g. "infor-\nmation" → "information")
    text = re.sub(r"-\n(\w)", r"\1", text)
    # Merge lines that are mid-sentence (no punctuation before the break)
    text = re.sub(r"(?<![.!?:])\n(?=[a-z])", " ", text)
    # Collapse 3+ consecutive newlines to two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(path: Path) -> str:
    """
    Per-page extraction: PyMuPDF for text-heavy pages, GLM-OCR for image-heavy
    or scanned pages. Results are concatenated in page order with markdown structure.
    """
    config = load_config()
    ollama_base = config.get("ollama", {}).get("base_url", "http://localhost:11434")
    ocr_model = config.get("pdf", {}).get("ocr_model", "glm-ocr")

    doc = fitz.open(str(path))
    total = len(doc)
    pages_text: list[str] = []

    try:
        for page in doc:
            n = page.number + 1
            if _page_needs_vision(page):
                logger.info("Page %d: image-heavy or no text layer → GLM-OCR", n)
                text = _ocr_page_glm(page, ollama_base, ocr_model)
                if not text:
                    text = _clean_text(page.get_text("text"))
                method = "visual"
            else:
                text = _clean_text(page.get_text("text"))
                logger.info("Page %d: text-heavy → PyMuPDF (%d chars)", n, len(text))
                method = "text"

            if text:
                pages_text.append(f"### Page {n} of {total} ({method})\n\n{text}")
    finally:
        doc.close()

    if not pages_text:
        return ""

    filename = path.stem.replace("_", " ").replace("-", " ")
    header = f"## Document: {filename}\n\n---\n"
    return header + "\n\n---\n\n".join(pages_text)


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
        pdf_text = _extract_pdf(file_path)

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
