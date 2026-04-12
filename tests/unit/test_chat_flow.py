"""
Integration tests for POST /chat

Mocks:
- Runner.run (OpenAI Agents SDK) — no real Ollama
- JWT auth — skips real token validation
- SQLite DB — uses tmp_db fixture

Verifies request/response contract, session handling, and attachment rejection.
"""
from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Stub out heavy optional dependencies so the full import chain resolves
# without needing GPU/colpali/torch installed in the test environment.
for _mod in ("colpali_engine", "torch", "PIL", "pdf2image", "ddgs", "fitz", "numpy", "numpy.typing", "sounddevice", "soundfile"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sdk_result(text: str = "Hello from Pluto!") -> MagicMock:
    result = MagicMock()
    result.final_output = text
    result.new_items = []
    return result


def _make_app(tmp_db_path: str):
    """Create a test FastAPI app with auth bypassed and DB pointed at tmp_db."""
    with patch("helpers.core.db.init_db", return_value=None):
        from main import create_app
        return create_app()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_override():
    """Return a dependency override that always authenticates successfully."""
    from helpers.routes.dependencies import get_current_user
    async def _override():
        return {"username": "admin"}
    return get_current_user, _override


@pytest.fixture
def client(tmp_db, auth_override):
    """TestClient with mocked auth and DB."""
    with (
        patch("helpers.core.db.init_db", new=AsyncMock(return_value=None)),
        patch("helpers.tools.memory.get_db_path", return_value=tmp_db),
        patch("helpers.tools.calendar.get_db_path", return_value=tmp_db),
    ):
        from main import create_app
        app = create_app()
        dep_key, dep_val = auth_override
        app.dependency_overrides[dep_key] = dep_val
        with TestClient(app, raise_server_exceptions=True, headers={"X-Requested-With": "XMLHttpRequest"}) as c:
            yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_chat_returns_200_with_response(client, tmp_db):
    sdk_result = _sdk_result("I'm Pluto, here to help!")
    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)),
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        resp = client.post("/chat", data={"message": "Hello!"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "I'm Pluto, here to help!"
    assert isinstance(body["tools_used"], list)
    assert isinstance(body["agents_trace"], list)


def test_chat_empty_message_ok(client, tmp_db):
    sdk_result = _sdk_result("")
    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)),
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
    ):
        resp = client.post("/chat", data={"message": ""})

    assert resp.status_code == 200


def test_chat_unsupported_attachment_returns_415(client, tmp_db):
    resp = client.post(
        "/chat",
        data={"message": "process this"},
        files=[("attachments", ("evil.exe", b"\x00\x01\x02", "application/octet-stream"))],
    )
    assert resp.status_code == 415


def test_chat_session_create_and_use(client, tmp_db):
    """Create a session, send a message with it, verify session persists."""
    # Create session
    with (
        patch("helpers.agents.session.session_store._db_path", return_value=tmp_db),
    ):
        sess_resp = client.post("/chat/session")
    assert sess_resp.status_code == 200
    session_id = sess_resp.json()["session_id"]
    assert session_id

    sdk_result = _sdk_result("Session reply.")
    with (
        patch("helpers.agents.execution.runner.Runner.run", new=AsyncMock(return_value=sdk_result)),
        patch("helpers.agents.routing.message_builder._calendar_context", return_value=""),
        patch("helpers.agents.session.session_store._db_path", return_value=tmp_db),
    ):
        chat_resp = client.post(
            "/chat",
            data={"message": "first message", "session_id": session_id},
        )

    assert chat_resp.status_code == 200
    assert chat_resp.json()["response"] == "Session reply."


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
