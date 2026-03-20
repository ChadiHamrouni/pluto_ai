"""Helper functions for slide generation (Marp)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

MARP_THEMES = {"default", "gaia", "uncover"}

_MARP_HEADER = """\
---
marp: true
theme: {theme}
paginate: true
---

"""


def get_slides_dir() -> str:
    return load_config()["storage"]["slides_dir"]


def build_slide_paths(slides_dir: str, title: str) -> tuple[str, str]:
    """Return (md_path, pdf_path) for a new presentation."""
    max_len = load_config()["storage"].get("title_slug_max_length", 60)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    safe_title = safe_title.replace(" ", "-")[:max_len]
    return (
        os.path.join(slides_dir, f"{timestamp}-{safe_title}.md"),
        os.path.join(slides_dir, f"{timestamp}-{safe_title}.pdf"),
    )


def build_marp_markdown(title: str, markdown_content: str, theme: str) -> str:
    header = _MARP_HEADER.format(theme=theme)
    title_slide = f"# {title}\n\n---\n\n" if not markdown_content.strip().startswith("#") else ""
    return header + title_slide + markdown_content


def marp_available() -> bool:
    timeout = load_config()["slides"].get("marp_check_timeout_seconds", 10)
    try:
        return subprocess.run(["marp", "--version"], capture_output=True, timeout=timeout).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_marp(md_path: str, pdf_path: str) -> tuple[bool, str]:
    """Invoke marp CLI. Returns (success, message)."""
    timeout = load_config()["slides"].get("marp_timeout_seconds", 120)
    try:
        result = subprocess.run(
            ["marp", md_path, "--pdf", "--output", pdf_path, "--allow-local-files", "--no-sandbox"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return False, f"marp failed (exit {result.returncode}). stderr: {result.stderr.strip()[:500]}"
        return True, pdf_path
    except subprocess.TimeoutExpired:
        return False, "marp timed out while generating the PDF."
    except Exception as exc:
        return False, f"Error running marp: {exc}"
