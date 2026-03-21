"""
E2E test configuration.

Requires a running Ollama instance with the configured models pulled.
Run from the repo root:

    pytest tests/e2e/ -v

Or just the e2e suite:

    pytest tests/e2e/ -v -m e2e
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest

# Put backend/ on sys.path so all imports resolve
BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("OPENAI_API_KEY", "no-tracing")
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"


def _ollama_reachable() -> bool:
    try:
        r = httpx.get("http://localhost:11434", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Skip all e2e tests automatically when Ollama is not reachable."""
    if _ollama_reachable():
        return
    skip = pytest.mark.skip(reason="Ollama not reachable — skipping e2e tests")
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop shared across the entire e2e session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_backend():
    """Initialise DB and storage dirs once before any e2e test runs."""
    from helpers.core.config_loader import load_config
    from helpers.core.db import init_db

    config = load_config()
    for key in ("notes_dir", "slides_dir"):
        os.makedirs(config["storage"][key], exist_ok=True)
    await init_db(config["memory"]["db_path"])
