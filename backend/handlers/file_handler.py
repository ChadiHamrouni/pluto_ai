from __future__ import annotations

import time
from pathlib import Path

from helpers.agents.execution.runner import run_agent
from helpers.agents.routing.prompt_utils import format_chat_history
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.file_parser import extract_pdf, ocr_image
from models.results import HandlerResult
from agent.single import get_single_agent

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_PDF_EXTS = {".pdf"}
_TEXT_EXTS = {".txt", ".md"}


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

    elif ext in _PDF_EXTS:
        pdf_text = extract_pdf(file_path)
        if not pdf_text:
            raise ValueError("PDF contains no extractable content.")
        logger.info("PDF extracted: %d chars", len(pdf_text))
        prefix = (
            "[ATTACHED DOCUMENT — answer from this content only, "
            "do NOT search the web]"
        )
        doc_block = f"{prefix}\n\n{pdf_text}"
        user_content = (
            f"{message}\n\n---\n\n{doc_block}"
            if message and message.strip()
            else f"Summarise this document:\n\n---\n\n{doc_block}"
        )
        messages = [{"role": "user", "content": user_content}]

    else:
        # Image — OCR then pass as plain text
        extracted = ocr_image(file_path)
        user_text = message.strip() if message and message.strip() else "Describe this image."
        if extracted:
            logger.info("Image OCR extracted: %d chars", len(extracted))
            user_content = f"{user_text}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{extracted}"
        else:
            logger.warning(
                "Image OCR returned nothing for %s — sending message only", file_path.name
            )
            user_content = (
                f"{user_text}\n\n"
                "[An image was attached but OCR could not extract any text from it.]"
            )
        messages = [{"role": "user", "content": user_content}]

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    messages = list(format_chat_history(windowed_history)) + messages

    result = await run_agent(get_single_agent(), messages)
    return HandlerResult(
        response=result.response,
        elapsed=time.perf_counter() - t0,
        tools_used=result.tools_used,
        agents_trace=result.agents_trace,
        user_content=user_content,
    )
