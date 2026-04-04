from __future__ import annotations

import json
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
    validate_outline,
)

logger = get_logger(__name__)


@function_tool
def draft_slides(title: str, slides_json: str) -> str:
    """
    Validate a slide outline before rendering. Call this FIRST.

    You must research the topic thoroughly, then create a detailed outline.
    Each slide needs a heading and 3-6 substantive bullet points with real
    facts, numbers, or explanations — not vague filler.

    Args:
        title: Presentation title (e.g. "Quantum Computing Fundamentals").
        slides_json: A JSON array of slide objects. Each object has:
            - "heading": slide title string (required)
            - "bullets": array of bullet point strings, 3-6 per slide (required)
            - "code": optional object for a syntax-highlighted code block:
                {"language": "python", "content": "def hello():\n    print('hi')"}
                Supported languages: python, java, javascript, typescript, sql, bash, cpp, etc.
                Use this on slides that demonstrate or explain code — always pair with bullets
                that describe what the code does.
            Example:
            [
              {"heading": "What is Quantum Computing?", "bullets": [
                "Uses qubits instead of bits",
                "Leverages superposition and entanglement",
                "Can solve certain problems exponentially faster"]},
              {"heading": "Hello World in Python", "bullets": [
                "print() writes output to the console",
                "Strings use single or double quotes"],
               "code": {"language": "python", "content": "print('Hello, World!')"}}
            ]

    Returns:
        On success: confirmation with slide count, ready for render_slides.
        On failure: specific validation errors to fix.
    """
    try:
        slides = json.loads(slides_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}. Fix the JSON array and call draft_slides again."

    errors = validate_outline(slides)
    if errors:
        return (
            "Outline has issues:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nFix these and call draft_slides again."
        )

    slide_count = len(slides)
    total_bullets = sum(len(s.get("bullets", [])) for s in slides)
    logger.info("Outline validated: %d slides, %d bullets", slide_count, total_bullets)
    return (
        f"Outline validated: {slide_count} slides, {total_bullets} bullet points."
        " Now call render_slides with the same title and slides_json."
    )


@function_tool
def render_slides(title: str, slides_json: str, theme: str = "default") -> str:
    """
    Render a validated outline into a PDF. Call this AFTER draft_slides succeeds.

    Args:
        title: Same title passed to draft_slides.
        slides_json: Same JSON array passed to draft_slides.
        theme: Visual theme — one of: default, gaia, uncover.
               Use "default" for clean white background with black text (recommended).

    Returns:
        On success: the file path to the generated PDF.
        On failure: an error description.
    """
    if theme not in MARP_THEMES:
        theme = "default"

    try:
        slides = json.loads(slides_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    errors = validate_outline(slides)
    if errors:
        return "Outline invalid — call draft_slides first to fix: " + "; ".join(errors)

    slides_dir = get_slides_dir()
    os.makedirs(slides_dir, exist_ok=True)

    paths = build_slide_paths(slides_dir, title)
    full_md = build_marp_markdown(title, slides, theme)

    try:
        with open(paths.md_path, "w", encoding="utf-8") as f:
            f.write(full_md)
        logger.info("Wrote Marp source to %s", paths.md_path)
    except Exception as exc:
        return f"Error writing markdown file: {exc}"

    if not marp_available():
        return f"marp CLI not installed. Markdown saved at: {paths.md_path}"

    success, message = run_marp(paths.md_path, paths.pdf_path)
    if success:
        logger.info("Generated slides PDF at %s", message)
        return f"Slides generated successfully: {message}"
    return message
