from __future__ import annotations

import os
import subprocess
from datetime import datetime

from agents import function_tool

from helpers.config_loader import load_config
from helpers.logger import get_logger

logger = get_logger(__name__)

MARP_THEMES = {"default", "gaia", "uncover"}

MARP_HEADER = """\
---
marp: true
theme: {theme}
paginate: true
---

"""


def _get_slides_dir() -> str:
    return load_config()["storage"]["slides_dir"]


def _ensure_marp_available() -> bool:
    try:
        result = subprocess.run(
            ["marp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@function_tool
def generate_slides(
    title: str,
    markdown_content: str,
    theme: str = "default",
) -> str:
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

    slides_dir = _get_slides_dir()
    os.makedirs(slides_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    safe_title = safe_title.replace(" ", "-")[:60]

    md_filename = f"{timestamp}-{safe_title}.md"
    pdf_filename = f"{timestamp}-{safe_title}.pdf"

    md_path = os.path.join(slides_dir, md_filename)
    pdf_path = os.path.join(slides_dir, pdf_filename)

    header = MARP_HEADER.format(theme=theme)
    title_slide = f"# {title}\n\n---\n\n" if not markdown_content.strip().startswith("#") else ""
    full_md = header + title_slide + markdown_content

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(full_md)
        logger.info("Wrote Marp source to %s", md_path)
    except Exception as exc:
        return f"Error writing markdown file: {exc}"

    if not _ensure_marp_available():
        logger.warning("marp CLI not found; returning markdown path instead.")
        return (
            f"marp CLI is not installed or not on PATH. "
            f"Markdown source saved at: {md_path}. "
            f"Install with: npm install -g @marp-team/marp-cli"
        )

    try:
        result = subprocess.run(
            ["marp", md_path, "--pdf", "--output", pdf_path, "--allow-local-files"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("marp exited with code %d: %s", result.returncode, result.stderr)
            return (
                f"marp failed (exit {result.returncode}). "
                f"stderr: {result.stderr.strip()[:500]}"
            )

        logger.info("Generated slides PDF at %s", pdf_path)
        return f"Slides generated successfully: {pdf_path}"

    except subprocess.TimeoutExpired:
        return "Error: marp timed out while generating the PDF."
    except Exception as exc:
        logger.error("Unexpected error running marp: %s", exc)
        return f"Error running marp: {exc}"
