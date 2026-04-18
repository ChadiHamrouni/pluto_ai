"""Low-level file parsing helpers: PDF extraction (PyMuPDF + GLM-OCR) and image OCR."""

from __future__ import annotations

import base64
import re
from pathlib import Path

import fitz  # PyMuPDF

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


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
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"(?<![.!?:])\n(?=[a-z])", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> str:
    """Per-page extraction: PyMuPDF for text-heavy pages, GLM-OCR for image-heavy or scanned."""
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


def _resize_for_ocr(raw_bytes: bytes, max_pixels: int = 1536) -> bytes:
    """Downscale an image so its longest side is at most *max_pixels*, returned as PNG bytes."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(raw_bytes))
    w, h = img.size
    if max(w, h) > max_pixels:
        scale = max_pixels / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        logger.debug("Resized image for OCR: %dx%d → %dx%d", w, h, img.width, img.height)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _ocr_text_is_useful(text: str) -> bool:
    """Return True only if OCR text contains meaningful content (not just markup or whitespace)."""
    if not text:
        return False
    import re
    stripped = re.sub(r"<[^>]+>", "", text).strip()
    return len(stripped) >= 30


def _describe_image(b64_image: str, ollama_base: str, vision_model: str) -> str:
    """Ask the vision model to describe image contents using Ollama /api/generate."""
    import httpx

    payload = {
        "model": vision_model,
        "prompt": "What is in this image? Be concise and factual. One short paragraph.",
        "images": [b64_image],
        "stream": False,
    }
    try:
        resp = httpx.post(f"{ollama_base}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        logger.warning("Vision description failed: %s", exc)
        return ""


def ocr_image(path: Path) -> str:
    """Extract text from an image via GLM-OCR; fall back to vision description if no text found."""
    import httpx

    config = load_config()
    ollama_base = config.get("ollama", {}).get("base_url", "http://localhost:11434")
    ocr_model = config.get("pdf", {}).get("ocr_model", "glm-ocr")
    vision_model = config.get("orchestrator", {}).get("model", "qwen3.5:4b")

    resized = _resize_for_ocr(path.read_bytes())
    b64_image = base64.b64encode(resized).decode()
    payload = {
        "model": ocr_model,
        "prompt": (
            "Extract all text from this image. "
            "Preserve tables, headings, and structure as markdown."
        ),
        "images": [b64_image],
        "stream": False,
    }
    try:
        resp = httpx.post(f"{ollama_base}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.warning("GLM-OCR failed on image %s: %s", path.name, exc)
        text = ""

    if _ocr_text_is_useful(text):
        return text

    logger.info("OCR result not useful for %s (%d chars) — falling back to vision description", path.name, len(text))
    description = _describe_image(b64_image, ollama_base, vision_model)
    return description
