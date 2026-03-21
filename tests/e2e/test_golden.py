"""
Golden dataset end-to-end tests.

Each test case sends a real message through text_handler (requires Ollama)
and asserts that the expected tools and agents appear in the result.

Marked with @pytest.mark.e2e — skip with:  pytest -m "not e2e"
Run with:                                   pytest tests/e2e/ -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATASET = Path(__file__).parent / "golden_dataset.json"

with DATASET.open(encoding="utf-8") as _f:
    _CASES: list[dict] = json.load(_f)


def _case_id(case: dict) -> str:
    return case["id"]


def _missing(actual: list[str], expected: list[str]) -> list[str]:
    return [e for e in expected if e not in actual]


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
async def test_golden(case: dict) -> None:
    """
    Sends case['input'] through text_handler and checks:
    - All expected_tools are present in result.tools_used
    - All expected_agents are present in result.agents_trace
    """
    from handlers.text_handler import text_handler

    result = await text_handler(case["input"], history=[])

    missing_tools = _missing(result.tools_used, case.get("expected_tools", []))
    missing_agents = _missing(result.agents_trace, case.get("expected_agents", []))

    assert not missing_tools, (
        f"[{case['id']}] Missing tools: {missing_tools}\n"
        f"  got tools_used={result.tools_used}\n"
        f"  expected={case.get('expected_tools')}"
    )
    assert not missing_agents, (
        f"[{case['id']}] Missing agents: {missing_agents}\n"
        f"  got agents_trace={result.agents_trace}\n"
        f"  expected={case.get('expected_agents')}"
    )
