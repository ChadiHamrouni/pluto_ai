"""
Shared fixtures for all tests.

No Docker, no real Ollama — everything is mocked at the AsyncOpenAI boundary.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make sure `backend/` is on sys.path so imports work when running from repo root
BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chat_response(content: str, finish_reason: str = "stop") -> MagicMock:
    """Build a fake openai ChatCompletion response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_tool_response(tool_name: str, arguments: str, tool_call_id: str = "call_1") -> MagicMock:
    """Build a fake response that triggers a single tool call."""
    tc = MagicMock()
    tc.id = tool_call_id
    tc.function.name = tool_name
    tc.function.arguments = arguments

    msg = MagicMock()
    msg.content = ""
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_llm_response():
    """Return the helper so individual tests can build responses."""
    return _make_chat_response


@pytest.fixture
def mock_ollama_client():
    """
    Patch get_openai_client() so no real HTTP calls happen.
    Returns the mock AsyncOpenAI client so tests can configure side effects.
    """
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_chat_response("Hello! How can I help you?")
    )

    # runner.py lazily imports get_openai_client inside run_agent().
    # Patch the source so the lazy import picks up the mock.
    with patch("helpers.agents.ollama_client.get_openai_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def tmp_db(tmp_path):
    """Create a fresh SQLite DB in a temp dir and point config at it."""
    db_file = tmp_path / "memory.db"
    with patch("helpers.tools.memory.get_db_path", return_value=str(db_file)):
        from helpers.core.db import init_db
        import asyncio
        asyncio.run(init_db(str(db_file)))
        yield str(db_file)
