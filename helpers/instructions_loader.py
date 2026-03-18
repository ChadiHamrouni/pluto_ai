"""Load agent instructions from markdown files in the instructions/ folder."""

from __future__ import annotations

import os

_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instructions")


def load_instructions(name: str) -> str:
    """
    Load instructions from instructions/<name>.md.

    Raises FileNotFoundError if the file does not exist.
    """
    path = os.path.join(_BASE, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()
