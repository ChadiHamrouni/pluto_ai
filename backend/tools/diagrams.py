"""Diagram generation @function_tool wrapper for the DashboardAgent."""

from __future__ import annotations

import os

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.diagrams import (
    MERMAID_THEMES,
    build_diagram_paths,
    get_diagrams_dir,
    mmdc_available,
    run_mmdc,
)

logger = get_logger(__name__)


@function_tool
def generate_diagram(
    title: str,
    mermaid_code: str,
    theme: str = "default",
    width: int = 1920,
    height: int = 1080,
) -> str:
    """
    Generate a diagram from Mermaid syntax and save it as a PNG image.

    Use this when the user wants any kind of visual diagram, chart, or graph.
    Write the Mermaid code yourself based on what the user describes.

    Supported Mermaid diagram types and their syntax starters:
    - flowchart TD (or LR)  — processes, workflows, decision trees
    - sequenceDiagram        — interactions between people or systems
    - gantt                  — project timelines and schedules
    - mindmap                — brainstorming, topic breakdowns
    - pie title X            — distributions, breakdowns by percentage
    - timeline               — historical or planned events
    - classDiagram           — data models, object relationships
    - erDiagram              — database schemas

    Example Mermaid code for a flowchart:
        flowchart TD
            A[Start] --> B{Decision}
            B -->|Yes| C[Do it]
            B -->|No| D[Skip it]
            C --> E[End]
            D --> E

    Example for a Gantt chart:
        gantt
            title Project Timeline
            dateFormat YYYY-MM-DD
            section Phase 1
            Task A :a1, 2026-04-01, 7d
            Task B :a2, after a1, 5d

    Example for a mindmap:
        mindmap
          root((Main Topic))
            Branch A
              Sub A1
              Sub A2
            Branch B
              Sub B1

    Args:
        title:        REQUIRED. Short descriptive title used for the filename.
        mermaid_code: REQUIRED. Valid Mermaid diagram syntax (the full diagram text).
        theme:        Visual theme. One of: default, dark, forest, neutral. Default: default.
        width:        Output image width in pixels. Default: 1920.
        height:       Output image height in pixels. Default: 1080.

    Returns:
        "Diagram saved: {png_path}" on success, or an error message.
        If mmdc is not installed, returns installation instructions.
    """
    if not mmdc_available():
        return (
            "Mermaid CLI (mmdc) is not installed or not on PATH.\n"
            "Install it with: npm install -g @mermaid-js/mermaid-cli\n"
            "Then restart the backend."
        )

    if theme not in MERMAID_THEMES:
        return f"Error: theme must be one of {sorted(MERMAID_THEMES)}, got '{theme}'."
    if width < 100 or height < 100:
        return "Error: width and height must be at least 100px."

    diagrams_dir = get_diagrams_dir()
    try:
        mmd_path, png_path = build_diagram_paths(diagrams_dir, title)
    except ValueError as exc:
        return f"Error: {exc}"

    # Write the .mmd source file
    try:
        with open(mmd_path, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
    except Exception as exc:
        logger.error("Failed to write mmd file: %s", exc)
        return f"Failed to write diagram source: {exc}"

    success, result = run_mmdc(mmd_path, png_path, theme=theme, width=width, height=height)

    if not success:
        # Clean up the .mmd file on failure
        try:
            os.remove(mmd_path)
        except OSError:
            pass
        logger.error("mmdc failed for '%s': %s", title, result)
        return f"Diagram generation failed: {result}"

    logger.info("Diagram saved: %s", png_path)
    # Write sidecar metadata so diagrams are searchable via Ctrl+P
    try:
        from pathlib import Path as _Path

        from helpers.tools.diagram_meta import write_diagram_meta
        write_diagram_meta(_Path(png_path).name, title, mermaid_code)
    except Exception:
        pass  # non-fatal
    return f"Diagram saved: {png_path}"
