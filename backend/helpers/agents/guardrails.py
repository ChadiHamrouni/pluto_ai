"""LLM-based output guardrails using the OpenAI Agents SDK.

Uses a small, fast model to evaluate agent responses before they reach the user.

**Relevance guard** — detects completely incoherent or gibberish responses.

Implemented as an SDK OutputGuardrail that plugs into RunConfig.output_guardrails.
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
# Relevance / coherence guardrail
# ---------------------------------------------------------------------------

_RELEVANCE_AGENT = None


def _get_relevance_agent() -> Agent[GuardrailResult]:
    global _RELEVANCE_AGENT
    if _RELEVANCE_AGENT is None:
        _RELEVANCE_AGENT = Agent(
            name="RelevanceGuard",
            model=get_model(_get_guardrail_model()),
            instructions=(
                "You are a quality-control assistant detecting completely broken LLM output.\n\n"
                "ONLY trigger (triggered=true) when the response is OBVIOUSLY broken — "
                "meaning pure gibberish, random characters, or a response that has absolutely "
                "no connection to any plausible interpretation of the user message.\n\n"
                "Do NOT trigger for:\n"
                "- Long, detailed, or structured responses (outlines, lists, markdown)\n"
                "- Responses that ask clarifying questions before acting\n"
                "- Responses that partially address the request\n"
                "- Quality or style issues (too verbose, wrong tone, incomplete)\n"
                "- Responses that seem reasonable even if not perfect\n\n"
                "A normal helpful assistant response of any length or format = triggered=false.\n"
                "The bar for triggering is VERY HIGH. When in doubt, do NOT trigger.\n\n"
                "Respond with JSON only:\n"
                '{"triggered": true/false, "reason": "one short sentence"}'
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

relevance_output_guardrail = OutputGuardrail(guardrail_function=relevance_guardrail)


def get_output_guardrails() -> list[OutputGuardrail]:
    """Return all output guardrails. Disabled if config sets guardrails.enabled = false."""
    config = load_config()
    if not config.get("guardrails", {}).get("enabled", True):
        return []
    return [relevance_output_guardrail]
