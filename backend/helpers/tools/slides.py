"""Helper functions for slide generation (Marp)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.results import SlidePaths

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


def build_slide_paths(slides_dir: str, title: str) -> SlidePaths:
    """Return md_path and pdf_path for a new presentation."""
    max_len = load_config()["storage"].get("title_slug_max_length", 60)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    safe_title = safe_title.replace(" ", "-")[:max_len]
    return SlidePaths(
        md_path=os.path.join(slides_dir, f"{timestamp}-{safe_title}.md"),
        pdf_path=os.path.join(slides_dir, f"{timestamp}-{safe_title}.pdf"),
    )


def validate_outline(slides: list[dict]) -> list[str]:
    """Validate a slide outline. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not isinstance(slides, list):
        return ["slides_json must be a JSON array of slide objects."]

    if len(slides) < 3:
        errors.append(
            f"Too few slides ({len(slides)}). Create at least 3 slides"
            " for a meaningful presentation."
        )

    for i, slide in enumerate(slides):
        if not isinstance(slide, dict):
            errors.append(f"Slide {i + 1}: must be an object with 'heading' and 'bullets'.")
            continue

        heading = slide.get("heading", "")
        if not heading or not heading.strip():
            errors.append(f"Slide {i + 1}: missing 'heading'.")

        bullets = slide.get("bullets", [])
        if not isinstance(bullets, list):
            errors.append(f"Slide {i + 1}: 'bullets' must be an array of strings.")
        elif len(bullets) < 2:
            errors.append(
                f"Slide {i + 1} ('{heading}'): too few bullets ({len(bullets)}). Add at least 2."
            )
        else:
            for j, b in enumerate(bullets):
                if not isinstance(b, str) or len(b.strip()) < 10:
                    errors.append(
                        f"Slide {i + 1}, bullet {j + 1}: too short or empty."
                        " Write substantive points (10+ chars)."
                    )

    return errors


def build_marp_markdown(title: str, slides: list[dict], theme: str) -> str:
    """Convert a validated outline into Marp markdown."""
    header = _MARP_HEADER.format(theme=theme)

    parts = [f"# {title}"]
    for slide in slides:
        parts.append("---")
        parts.append(f"## {slide['heading']}")
        for bullet in slide.get("bullets", []):
            parts.append(f"- {bullet}")

    return header + "\n\n".join(parts) + "\n"


def marp_available() -> bool:
    timeout = load_config()["slides"].get("marp_check_timeout_seconds", 10)
    try:
        return (
            subprocess.run(["marp", "--version"], capture_output=True, timeout=timeout).returncode
            == 0
        )
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
            return (
                False,
                f"marp failed (exit {result.returncode}). stderr: {result.stderr.strip()[:500]}",
            )
        return True, pdf_path
    except subprocess.TimeoutExpired:
        return False, "marp timed out while generating the PDF."
    except Exception as exc:
        return False, f"Error running marp: {exc}"
