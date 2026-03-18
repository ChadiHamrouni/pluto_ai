from __future__ import annotations

import os

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.slides import (
    MARP_THEMES,
    build_marp_markdown,
    build_slide_paths,
    get_slides_dir,
    marp_available,
    run_marp,
)

logger = get_logger(__name__)


@function_tool
def generate_slides(title: str, markdown_content: str, theme: str = "default") -> str:
    """
    Generate a Marp presentation PDF from the supplied markdown content.

    Writes a ``.md`` source file with a Marp front-matter header, then
    invokes the ``marp`` CLI to convert it to PDF.

    Args:
        title:            Presentation title (used as filename base).
        markdown_content: Marp-compatible markdown. Separate slides with ``---``.
        theme:            Marp theme: default | gaia | uncover.

    Returns:
        The absolute path to the generated PDF, or an error description.
    """
    if theme not in MARP_THEMES:
        theme = "default"
        logger.warning("Unknown theme requested; falling back to 'default'.")

    slides_dir = get_slides_dir()
    os.makedirs(slides_dir, exist_ok=True)

    md_path, pdf_path = build_slide_paths(slides_dir, title)
    full_md = build_marp_markdown(title, markdown_content, theme)

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(full_md)
        logger.info("Wrote Marp source to %s", md_path)
    except Exception as exc:
        return f"Error writing markdown file: {exc}"

    if not marp_available():
        logger.warning("marp CLI not found; returning markdown path instead.")
        return (
            f"marp CLI is not installed or not on PATH. "
            f"Markdown source saved at: {md_path}. "
            f"Install with: npm install -g @marp-team/marp-cli"
        )

    success, message = run_marp(md_path, pdf_path)
    if success:
        logger.info("Generated slides PDF at %s", message)
        return f"Slides generated successfully: {message}"
    return message
