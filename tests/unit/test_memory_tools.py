"""
Tests for tools/memory_tools.py + helpers/tools/memory.py

Uses a real in-process SQLite DB (tmp_db fixture) — no Ollama, no Docker.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Tests: insert + search
# ---------------------------------------------------------------------------

def test_insert_and_search_memory(tmp_db):
    from helpers.tools.memory import insert_memory, search_memories

    insert_memory(tmp_db, content="I love hiking in the mountains", category="personal", tags_json='["hobby"]')
    insert_memory(tmp_db, content="I am a teaching assistant at university", category="career", tags_json='["work"]')

    results = search_memories(tmp_db, query="hiking", top_k=5)
    assert len(results) >= 1
    assert any("hiking" in r["content"] for r in results)


def test_search_returns_most_recent_fallback(tmp_db):
    """When no FTS match, should return most recent memories."""
    from helpers.tools.memory import insert_memory, search_memories

    insert_memory(tmp_db, content="bought groceries today", category="personal", tags_json="[]")
    insert_memory(tmp_db, content="met with supervisor", category="career", tags_json="[]")

    # query with no match → fallback to most recent
    results = search_memories(tmp_db, query="zzz_no_match_xyz", top_k=5)
    assert len(results) >= 1  # fallback should return something


def test_insert_memory_returns_id(tmp_db):
    from helpers.tools.memory import insert_memory

    mem_id = insert_memory(tmp_db, content="test content", category="personal", tags_json="[]")
    assert isinstance(mem_id, int)
    assert mem_id > 0


def test_delete_memory(tmp_db):
    from helpers.tools.memory import insert_memory, search_memories, delete_memory_by_id

    mem_id = insert_memory(tmp_db, content="delete me please", category="personal", tags_json="[]")
    delete_memory_by_id(tmp_db, mem_id)

    results = search_memories(tmp_db, query="delete me please", top_k=5)
    assert all("delete me please" not in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Tests: store_memory / forget_memory underlying functions
# (FunctionTool wrappers are not directly callable — test the helper layer)
# ---------------------------------------------------------------------------

def test_store_memory_helper(tmp_db):
    """Test the helper that store_memory tool delegates to."""
    from helpers.tools.memory import insert_memory, search_memories

    mem_id = insert_memory(tmp_db, content="likes coffee in the morning", category="personal", tags_json='["coffee"]')
    assert mem_id > 0

    results = search_memories(tmp_db, query="coffee", top_k=5)
    assert any("coffee" in r["content"] for r in results)


def test_forget_memory_helper(tmp_db):
    """Test that delete_memory_by_id removes from DB and FTS."""
    from helpers.tools.memory import insert_memory, search_memories, delete_memory_by_id

    mem_id = insert_memory(tmp_db, content="forget this fact", category="personal", tags_json="[]")
    delete_memory_by_id(tmp_db, mem_id)

    results = search_memories(tmp_db, query="forget this fact", top_k=5)
    assert all("forget this fact" not in r["content"] for r in results)
