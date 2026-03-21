"""
Unit tests for helpers/agents/guardrails.py

Tests the LLM-based output guardrails by mocking Runner.run.
No real Ollama, no DB, no network.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from helpers.agents.guardrails import (
    GuardrailResult,
    get_output_guardrails,
    relevance_guardrail,
    repetition_guardrail,
)
from agents import GuardrailFunctionOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_ctx(user_message: str = "hello"):
    ctx = MagicMock()
    ctx.turn_input = [{"role": "user", "content": user_message}]
    return ctx


def _mock_agent(name: str = "Orchestrator"):
    agent = MagicMock()
    agent.name = name
    return agent


def _sdk_run_result(verdict: GuardrailResult) -> MagicMock:
    result = MagicMock()
    result.final_output = verdict
    return result


# ---------------------------------------------------------------------------
# repetition_guardrail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repetition_guardrail_triggers_on_looping_output():
    verdict = GuardrailResult(triggered=True, reason="Phrase repeats 5 times.")
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(return_value=_sdk_run_result(verdict)),
    ):
        output = await repetition_guardrail(_mock_ctx(), _mock_agent(), "blah blah blah blah blah")

    assert isinstance(output, GuardrailFunctionOutput)
    assert output.tripwire_triggered is True
    assert output.output_info.reason == "Phrase repeats 5 times."


@pytest.mark.asyncio
async def test_repetition_guardrail_passes_clean_output():
    verdict = GuardrailResult(triggered=False, reason="No repetition detected.")
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(return_value=_sdk_run_result(verdict)),
    ):
        output = await repetition_guardrail(_mock_ctx(), _mock_agent(), "Here is your answer.")

    assert output.tripwire_triggered is False


@pytest.mark.asyncio
async def test_repetition_guardrail_does_not_raise_on_eval_failure():
    """If the evaluator LLM call fails, the guardrail must not raise — fail open."""
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(side_effect=RuntimeError("connection refused")),
    ):
        output = await repetition_guardrail(_mock_ctx(), _mock_agent(), "some output")

    assert output.tripwire_triggered is False
    assert output.output_info.reason == "eval_error"


# ---------------------------------------------------------------------------
# relevance_guardrail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relevance_guardrail_triggers_on_incoherent_output():
    verdict = GuardrailResult(triggered=True, reason="Response is gibberish.")
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(return_value=_sdk_run_result(verdict)),
    ):
        output = await relevance_guardrail(
            _mock_ctx("what is 2+2?"), _mock_agent(), "banana helicopter 77"
        )

    assert output.tripwire_triggered is True


@pytest.mark.asyncio
async def test_relevance_guardrail_passes_relevant_output():
    verdict = GuardrailResult(triggered=False, reason="Response is coherent.")
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(return_value=_sdk_run_result(verdict)),
    ):
        output = await relevance_guardrail(
            _mock_ctx("what is 2+2?"), _mock_agent(), "2 + 2 equals 4."
        )

    assert output.tripwire_triggered is False


@pytest.mark.asyncio
async def test_relevance_guardrail_does_not_raise_on_eval_failure():
    with patch(
        "helpers.agents.guardrails.Runner.run",
        new=AsyncMock(side_effect=RuntimeError("timeout")),
    ):
        output = await relevance_guardrail(_mock_ctx(), _mock_agent(), "some response")

    assert output.tripwire_triggered is False
    assert output.output_info.reason == "eval_error"


# ---------------------------------------------------------------------------
# get_output_guardrails
# ---------------------------------------------------------------------------

def test_get_output_guardrails_returns_list_when_enabled():
    with patch(
        "helpers.agents.guardrails.load_config",
        return_value={"guardrails": {"enabled": True, "model": "qwen2.5:3b"}, "orchestrator": {"model": "qwen2.5:3b"}},
    ):
        guardrails = get_output_guardrails()
    assert len(guardrails) == 2


def test_get_output_guardrails_returns_empty_when_disabled():
    with patch(
        "helpers.agents.guardrails.load_config",
        return_value={"guardrails": {"enabled": False}, "orchestrator": {"model": "qwen2.5:3b"}},
    ):
        guardrails = get_output_guardrails()
    assert guardrails == []
