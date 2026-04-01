"""Helper functions for Mermaid diagram generation (mmdc CLI)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

MERMAID_THEMES = {"default", "dark", "forest", "neutral"}


def get_diagrams_dir() -> str:
    return load_config()["storage"]["diagrams_dir"]


def mmdc_available() -> bool:
    try:
        result = subprocess.run(
            ["mmdc", "--version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def build_diagram_paths(diagrams_dir: str, title: str) -> tuple[str, str]:
    """Return (mmd_path, png_path) for a new diagram, with path traversal guard."""
    os.makedirs(diagrams_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    safe_title = safe_title.replace(" ", "-")[:60]
    base = Path(diagrams_dir).resolve()
    mmd_path = (base / f"{timestamp}-{safe_title}.mmd").resolve()
    png_path = (base / f"{timestamp}-{safe_title}.png").resolve()
    if not str(mmd_path).startswith(str(base)) or not str(png_path).startswith(str(base)):
        raise ValueError("Generated diagram paths escape the diagrams directory.")
    return str(mmd_path), str(png_path)


def run_mmdc(
    mmd_path: str,
    png_path: str,
    theme: str = "default",
    bg_color: str = "white",
    width: int = 1920,
    height: int = 1080,
) -> tuple[bool, str]:
    """Invoke mmdc CLI. Returns (success, message_or_path)."""
    timeout = load_config().get("diagrams", {}).get("timeout_seconds", 60)
    try:
        result = subprocess.run(
            [
                "mmdc",
                "--input", mmd_path,
                "--output", png_path,
                "--theme", theme,
                "--backgroundColor", bg_color,
                "--width", str(width),
                "--height", str(height),
                "--puppeteerConfigFile", "/app/puppeteer-config.json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = result.stderr.strip()[:500] or result.stdout.strip()[:500]
            return False, f"mmdc failed (exit {result.returncode}): {err}"
        return True, png_path
    except subprocess.TimeoutExpired:
        return False, "mmdc timed out while generating the diagram."
    except Exception as exc:
        return False, f"Error running mmdc: {exc}"
