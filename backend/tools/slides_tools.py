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
    Generate a Marp presentation PDF from Marp-compatible markdown content.

    Use this tool immediately when the user asks for a presentation, slides,
    or a slide deck — regardless of topic or length. Do NOT output the
    markdown as text first. Draft the Marp markdown internally, then call
    this tool right away. Your entire reply to the user should be the file
    path returned by this tool, nothing else.

    Marp markdown format rules:
    - Start with a title slide using a top-level heading (# Title).
    - Separate each slide with ``---`` on its own line.
    - Use bullet points for content; max 5-6 bullets per slide.
    - End with a summary or conclusion slide.
    - Do NOT include the Marp front-matter header — this tool adds it automatically.

    Args:
        title:            Presentation title. Also used as the output filename
                          base (e.g. "AI Guardrails" → ai-guardrails.pdf).
                          Should be concise and descriptive.
        markdown_content: Full Marp-compatible slide markdown. Must use ``---``
                          as slide separators. Do not include front-matter.
                          Example:
                            # AI Guardrails
                            ## What they are and why they matter
                            ---
                            # Key Concepts
                            - Content safety filters
                            - Policy enforcement
        theme:            Visual theme for the presentation. Must be one of:
                          default, gaia, uncover. Defaults to "default" if
                          omitted or invalid.

    Returns:
        On success: the absolute file path to the generated PDF
        (e.g. /app/data/slides/ai-guardrails.pdf).
        On marp CLI missing: a message with the markdown source path and
        install instructions.
        On failure: an error description string.
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
