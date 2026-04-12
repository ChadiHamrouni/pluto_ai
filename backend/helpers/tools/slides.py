"""Helper functions for slide generation (Marp)."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

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

<style>
/* ── Base: clean white slide ─────────────────────────────────── */
section {{
  background: #ffffff;
  color: #1a1a1a;
  font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-size: 28px;
  line-height: 1.6;
}}
h1 {{
  font-size: 1.85em;
  color: #111111;
  letter-spacing: -0.5px;
}}
h2 {{
  font-size: 1.3em;
  color: #111111;
  border-bottom: 3px solid #1a1a1a;
  padding-bottom: 0.2em;
  margin-bottom: 0.5em;
}}
li {{
  margin-bottom: 0.4em;
  color: #222222;
}}

/* ── Code block: VS Code Dark+ ───────────────────────────────── */
pre {{
  background: #1e1e1e;
  border-left: 5px solid #569cd6;
  border-radius: 6px;
  padding: 0.8em 1.1em;
  margin-top: 0.7em;
  overflow: auto;
}}
pre code {{
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 0.75em;
  background: transparent;
  color: #d4d4d4;
}}
/* Inline code in bullet text */
li code, p code {{
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 0.8em;
  background: #f0f0f0;
  color: #c7254e;
  padding: 0.1em 0.35em;
  border-radius: 3px;
}}

/* ── highlight.js VS Code Dark+ token colours ────────────────── */
.hljs-keyword,
.hljs-selector-tag,
.hljs-built_in,
.hljs-name,
.hljs-tag {{ color: #569cd6; }}

.hljs-string,
.hljs-doctag,
.hljs-template-string {{ color: #ce9178; }}

.hljs-comment,
.hljs-quote {{ color: #6a9955; font-style: italic; }}

.hljs-number,
.hljs-literal,
.hljs-regexp {{ color: #b5cea8; }}

.hljs-title,
.hljs-section,
.hljs-selector-id {{ color: #dcdcaa; }}

.hljs-class .hljs-title,
.hljs-type {{ color: #4ec9b0; }}

.hljs-variable,
.hljs-params,
.hljs-attr {{ color: #9cdcfe; }}

.hljs-meta,
.hljs-meta .hljs-keyword {{ color: #9b9b9b; }}

.hljs-symbol,
.hljs-bullet {{ color: #ce9178; }}

.hljs-operator,
.hljs-punctuation {{ color: #d4d4d4; }}
</style>

"""


def get_slides_dir() -> str:
    return load_config()["storage"]["slides_dir"]


def build_slide_paths(slides_dir: str, title: str) -> SlidePaths:
    """Return md_path and pdf_path for a new presentation."""
    max_len = load_config()["storage"].get("title_slug_max_length", 60)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
    safe_title = safe_title.replace(" ", "-")[:max_len]
    md_path = Path(os.path.join(slides_dir, f"{timestamp}-{safe_title}.md")).resolve()
    pdf_path = Path(os.path.join(slides_dir, f"{timestamp}-{safe_title}.pdf")).resolve()
    base = Path(slides_dir).resolve()
    if not str(md_path).startswith(str(base)) or not str(pdf_path).startswith(str(base)):
        raise ValueError("Generated slide paths escape the slides directory.")
    return SlidePaths(
        md_path=str(md_path),
        pdf_path=str(pdf_path),
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

        code = slide.get("code")
        if code is not None:
            if not isinstance(code, dict):
                errors.append(
                    f"Slide {i + 1}: 'code' must be an object with 'language' and 'content' keys."
                )
            elif (
                not isinstance(code.get("content", ""), str)
                or not code.get("content", "").strip()
            ):
                errors.append(f"Slide {i + 1}: 'code.content' must be a non-empty string.")

    return errors


# ---------------------------------------------------------------------------
# Code-line auto-detection helpers
# ---------------------------------------------------------------------------

# Matches lines that look like code statements rather than natural-language bullets.
_CODE_LINE_RE = re.compile(
    r"^("
    r"(from|import|def|class|if|elif|else|for|while|return|try|except|with"
    r"|raise|pass|break|continue|print|async|await|var|let|const|public|private"
    r"|protected|static|void|int|str|bool|float)\s"
    r"|[\w][\w.]*\s*[+\-*/]?=\s*"   # assignment: x = ... or x += ...
    r"|[\w][\w.]*\("                  # function call: foo(
    r"|#"                              # Python comment
    r"|//"                             # JS/Java comment
    r"|\{|\["                          # starts with { or [
    r")"
)


def _all_code_lines(bullets: list[str]) -> bool:
    """Return True if every non-empty bullet looks like a code statement."""
    non_empty = [b.strip() for b in bullets if b.strip()]
    return bool(non_empty) and all(_CODE_LINE_RE.match(b) for b in non_empty)


def _guess_language(bullets: list[str], heading: str) -> str:
    """Heuristically pick a language tag for an auto-detected code block."""
    h = heading.lower()
    content = " ".join(bullets)
    if "python" in h or any(kw in content for kw in ["def ", "print(", "from ", "import "]):
        return "python"
    if "javascript" in h or " js " in h or "node" in h:
        return "javascript"
    if "typescript" in h:
        return "typescript"
    if "java" in h and "javascript" not in h:
        return "java"
    if "sql" in h:
        return "sql"
    if "bash" in h or "shell" in h or "terminal" in h:
        return "bash"
    if "cpp" in h or "c++" in h:
        return "cpp"
    return ""


def build_marp_markdown(title: str, slides: list[dict], theme: str) -> str:
    """Convert a validated outline into Marp markdown."""
    header = _MARP_HEADER.format(theme=theme)

    parts = [f"# {title}"]
    for slide in slides:
        parts.append("---")
        heading = slide["heading"]
        parts.append(f"## {heading}")
        bullets = slide.get("bullets", [])

        # If the LLM dumped pure code lines as bullets, auto-wrap as a fenced block.
        explicit_code = slide.get("code")
        if explicit_code is None and _all_code_lines(bullets):
            lang = _guess_language(bullets, heading)
            content = "\n".join(b.strip() for b in bullets if b.strip())
            parts.append(f"\n```{lang}\n{content}\n```")
        else:
            for bullet in bullets:
                parts.append(f"- {bullet}")
            # Explicit code field provided by the agent
            if explicit_code and isinstance(explicit_code, dict):
                lang = explicit_code.get("language", "")
                content = explicit_code.get("content", "").strip()
                if content:
                    parts.append(f"\n```{lang}\n{content}\n```")

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
            ["marp", md_path, "--pdf", "--output", pdf_path],
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
