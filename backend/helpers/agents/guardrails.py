"""LLM-based output guardrails using the OpenAI Agents SDK.

Uses a small, fast model to evaluate agent responses before they reach the user.
Two checks are applied:

1. **Repetition guard** — detects looping output (common in small models).
2. **Relevance guard** — detects hallucinated or incoherent responses.

Both are implemented as SDK OutputGuardrail functions so they plug directly into
RunConfig.output_guardrails and run in parallel with the main agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents import (
    Agent,
    GuardrailFunctionOutput,
    OutputGuardrail,
    RunConfig,
    RunContextWrapper,
    Runner,
)

from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Guardrail output schema
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    triggered: bool
    reason: str


# ---------------------------------------------------------------------------
# Shared: build the evaluator model
# ---------------------------------------------------------------------------


def _get_guardrail_model() -> str:
    """Use the orchestrator model for guardrail evaluation by default."""
    config = load_config()
    return config.get("guardrails", {}).get(
        "model",
        config["orchestrator"]["model"],
    )


# ---------------------------------------------------------------------------
# 1. Repetition guardrail
# ---------------------------------------------------------------------------

_REPETITION_AGENT = None


def _get_repetition_agent() -> Agent[GuardrailResult]:
    global _REPETITION_AGENT
    if _REPETITION_AGENT is None:
        _REPETITION_AGENT = Agent(
            name="RepetitionGuard",
            model=get_model(_get_guardrail_model()),
            instructions=(
                "You are a quality-control assistant. Your only job is to detect "
                "whether a given text response is repetitive — i.e., whether the "
                "same sentence or phrase is repeated 3 or more times in a row.\n\n"
                "Respond with a JSON object:\n"
                '{"triggered": true/false, "reason": "one short sentence explaining why"}\n\n'
                "Examples:\n"
                '- Repetitive looping text → {"triggered": true,'
                ' "reason": "Phrase X repeats 5 times."}\n'
                '- Normal varied response → {"triggered": false,'
                ' "reason": "No repetition detected."}'
            ),
            output_type=GuardrailResult,
        )
    return _REPETITION_AGENT


async def repetition_guardrail(
    ctx: RunContextWrapper,
    agent: Agent,
    output: str,
) -> GuardrailFunctionOutput:
    """Flag responses where the model has entered a repetition loop."""
    evaluator = _get_repetition_agent()
    try:
        result = await Runner.run(
            starting_agent=evaluator,
            input=f"Evaluate this response for repetition:\n\n{output[:2000]}",
            run_config=RunConfig(tracing_disabled=True),
        )
        verdict: GuardrailResult = result.final_output
        if verdict.triggered:
            logger.warning("Repetition guardrail triggered: %s", verdict.reason)
        return GuardrailFunctionOutput(
            output_info=verdict,
            tripwire_triggered=verdict.triggered,
        )
    except Exception as exc:
        logger.warning("Repetition guardrail skipped (eval failed): %s", exc)
        return GuardrailFunctionOutput(
            output_info=GuardrailResult(triggered=False, reason="eval_error"),
            tripwire_triggered=False,
        )


# ---------------------------------------------------------------------------
# 2. Relevance / coherence guardrail
# ---------------------------------------------------------------------------

_RELEVANCE_AGENT = None


def _get_relevance_agent() -> Agent[GuardrailResult]:
    global _RELEVANCE_AGENT
    if _RELEVANCE_AGENT is None:
        _RELEVANCE_AGENT = Agent(
            name="RelevanceGuard",
            model=get_model(_get_guardrail_model()),
            instructions=(
                "You are a quality-control assistant. You receive a user message and "
                "an assistant response. Decide whether the response is coherent and "
                "relevant — not gibberish, not a complete non-sequitur, and not an "
                "obvious hallucination (e.g. claiming to have done something impossible).\n\n"
                "Respond with a JSON object:\n"
                '{"triggered": true/false, "reason": "one short sentence"}\n\n'
                "Only trigger (true) when the response is clearly incoherent or nonsensical. "
                "Do NOT trigger for subjective quality issues — only hard failures."
            ),
            output_type=GuardrailResult,
        )
    return _RELEVANCE_AGENT


async def relevance_guardrail(
    ctx: RunContextWrapper,
    agent: Agent,
    output: str,
) -> GuardrailFunctionOutput:
    """Flag responses that are incoherent or completely off-topic."""
    # Retrieve the last user message from context for comparison
    try:
        user_turn = next(
            (m["content"] for m in reversed(ctx.turn_input or []) if m.get("role") == "user"),
            "",
        )
    except Exception:
        user_turn = ""

    evaluator = _get_relevance_agent()
    try:
        prompt = (
            f"User message: {user_turn[:500]}\n\n"
            f"Assistant response: {output[:2000]}\n\n"
            "Is this response coherent and relevant?"
        )
        result = await Runner.run(
            starting_agent=evaluator,
            input=prompt,
            run_config=RunConfig(tracing_disabled=True),
        )
        verdict: GuardrailResult = result.final_output
        if verdict.triggered:
            logger.warning("Relevance guardrail triggered: %s", verdict.reason)
        return GuardrailFunctionOutput(
            output_info=verdict,
            tripwire_triggered=verdict.triggered,
        )
    except Exception as exc:
        logger.warning("Relevance guardrail skipped (eval failed): %s", exc)
        return GuardrailFunctionOutput(
            output_info=GuardrailResult(triggered=False, reason="eval_error"),
            tripwire_triggered=False,
        )


# ---------------------------------------------------------------------------
# Pre-built guardrail instances for use in RunConfig
# ---------------------------------------------------------------------------

repetition_output_guardrail = OutputGuardrail(guardrail_function=repetition_guardrail)
relevance_output_guardrail = OutputGuardrail(guardrail_function=relevance_guardrail)


def get_output_guardrails() -> list[OutputGuardrail]:
    """Return all output guardrails. Disabled if config sets guardrails.enabled = false."""
    config = load_config()
    if not config.get("guardrails", {}).get("enabled", True):
        return []
    return [repetition_output_guardrail, relevance_output_guardrail]
