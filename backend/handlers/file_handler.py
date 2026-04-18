from __future__ import annotations

import time
from pathlib import Path

from agent.single import get_single_agent
from helpers.agents.execution.runner import run_agent
from helpers.agents.routing.prompt_utils import format_chat_history
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.file_parser import extract_pdf, ocr_image
from models.results import HandlerResult

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_PDF_EXTS = {".pdf"}
_TEXT_EXTS = {".txt", ".md"}


def _extract_file_block(file_path: Path, filename: str) -> str:
    """Extract text content from a single file and return a labelled block."""
    ext = file_path.suffix.lower()

    if ext in _TEXT_EXTS:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return f"<attachment type=\"text\" name=\"{filename}\">\n{content}\n</attachment>"

    if ext in _PDF_EXTS:
        pdf_text = extract_pdf(file_path)
        if not pdf_text:
            return f"<attachment type=\"pdf\" name=\"{filename}\">\n[No extractable text found.]\n</attachment>"
        logger.info("PDF extracted: %d chars from %s", len(pdf_text), filename)
        return f"<attachment type=\"pdf\" name=\"{filename}\">\n{pdf_text}\n</attachment>"

    if ext in _IMAGE_EXTS:
        extracted = ocr_image(file_path)
        if extracted:
            logger.info("Image content extracted: %d chars from %s", len(extracted), filename)
            return f"<attachment type=\"image\" name=\"{filename}\">\n{extracted}\n</attachment>"
        logger.warning("Image analysis returned nothing for %s", filename)
        return f"<attachment type=\"image\" name=\"{filename}\">\n[Could not extract any content.]\n</attachment>"

    return f"<attachment type=\"file\" name=\"{filename}\">\n[Unsupported file type: {ext}]\n</attachment>"


async def file_handler(
    message: str,
    history: list[dict],
    file_paths: list[Path],
    attachment_meta: list | None = None,
) -> HandlerResult:
    t0 = time.perf_counter()

    blocks: list[str] = []
    for i, fp in enumerate(file_paths):
        filename = attachment_meta[i].filename if attachment_meta else fp.name
        logger.info("File handler: %s (%d bytes)", filename, fp.stat().st_size)
        blocks.append(_extract_file_block(fp, filename))

    combined = "\n\n".join(blocks)
    user_text = message.strip() if message and message.strip() else "Analyse the attached file(s)."
    user_content = f"{user_text}\n\n<attachments count=\"{len(blocks)}\">\n{combined}\n</attachments>"

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    messages = list(format_chat_history(windowed_history)) + [
        {"role": "user", "content": user_content}
    ]

    result = await run_agent(get_single_agent(), messages)
    return HandlerResult(
        response=result.response,
        elapsed=time.perf_counter() - t0,
        tools_used=result.tools_used,
        agents_trace=result.agents_trace,
        user_content=user_content,
    )
