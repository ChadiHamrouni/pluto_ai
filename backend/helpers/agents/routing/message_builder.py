"""Shared message-preparation logic for text handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from helpers.agents.execution.ollama_client import get_openai_client
from helpers.agents.planning.extractor import extract_items, format_extracted_context, should_extract
from helpers.agents.planning.planner import build_plan, format_plan_context, is_multi_step_plan, should_plan
from helpers.agents.routing.command_parser import parse_command
from helpers.agents.routing.prompt_utils import _build_context_block, format_chat_history
from helpers.agents.session.compactor import compact_history
from helpers.agents.session.token_counter import needs_compaction
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.calendar import get_db_path as get_cal_db_path
from helpers.tools.calendar import upcoming_events
from helpers.tools.file_parser import ocr_image

logger = get_logger(__name__)


def _calendar_context() -> str:
    """Return a concise upcoming-events blurb for injection into the prompt."""
    try:
        events = upcoming_events(get_cal_db_path(), hours=24)
        if not events:
            return ""
        lines = ["## Upcoming events (next 24h)"]
        for ev in events:
            end = f" → {ev['end_time']}" if ev.get("end_time") else ""
            lines.append(f"- [{ev['id']}] {ev['title']} at {ev['start_time']}{end}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Calendar context skipped: %s", exc)
        return ""


async def build_messages(
    message: str,
    history: list[dict],
    image_path: Path | None = None,
    source: str = "",
) -> tuple[Any, list[dict[str, Any]], str]:
    """Parse the message, select a tool-scoped agent, build the message list, and compact.

    Slash commands are resolved to both an intent hint and a tool group so the
    agent cloned by get_agent_for_intent() only sees the tools relevant to this
    turn — typically 3–8 instead of all 29. This is the primary accuracy and
    latency lever for a small local model.

    Returns:
        (agent, messages, memory_context)
    """
    from agent.single import get_agent_for_intent, get_single_agent

    # Voice input: skip intent routing and give the agent all tools so it can
    # handle any request without a slash command prefix.
    is_slash_command = False
    if source == "voice":
        agent = get_single_agent()
        content = message
        logger.info(
            "Routing to %s | intent=voice (all tools) | tools=%d",
            agent.name,
            len(agent.tools),
        )
    else:
        parsed = parse_command(message)

        # Prepend [intent] hint so the agent knows which domain to focus on.
        if parsed.intent and parsed.content:
            content = f"[{parsed.intent}] {parsed.content}"
        elif parsed.intent and not parsed.content:
            # Bare command with no body (e.g. just "/dashboard") — intent is the message.
            content = parsed.intent
        else:
            content = message

        # Slash command → scoped tool group. Free-form text → all tools so the
        # agent can handle any natural-language request (voice, dictate, typing).
        if parsed.intent:
            is_slash_command = True
            agent = get_agent_for_intent(intent=parsed.intent, tool_group=parsed.tool_group)
        else:
            agent = get_single_agent()
        logger.info(
            "Routing to %s | intent=%s | tool_group=%s | tools=%d",
            agent.name,
            parsed.intent or "none",
            parsed.tool_group or "all",
            len(agent.tools),
        )

    config = load_config()
    window = config.get("orchestrator", {}).get("history_window", 20)
    windowed_history = history[-(window * 2):]
    if len(history) > len(windowed_history):
        logger.debug("History truncated: %d → %d messages", len(history), len(windowed_history))

    # Calendar context is injected as memory_context (appended as a system
    # message in runner.py, after the static instructions prefix, so it does
    # not invalidate the KV cache on the stable instructions prefix).
    memory_context = _calendar_context()

    # Pre-processing pass for free-form messages (not slash commands).
    # Two strategies, checked in priority order:
    #
    # 1. Planner — for complex multi-step tasks (slides, diagrams, research).
    #    Produces an ordered execution plan injected as a context block so the
    #    agent follows steps in sequence without re-deriving them.
    #
    # 2. Extractor — for multi-action prose (calendar + reminders + tasks in
    #    one message). Normalises items into a structured list for batch tools.
    #    Skipped when the planner already handled the message.
    if not is_slash_command:
        context_block = _build_context_block()
        plan_injected = False

        if should_plan(content):
            plan = await build_plan(content, context_block)
            if is_multi_step_plan(plan):
                plan_block = format_plan_context(plan, content)
                if plan_block:
                    memory_context = "\n\n---\n\n".join(filter(None, [memory_context, plan_block]))
                    logger.info(
                        "Planner injected %d-step plan into context",
                        len(plan.get("steps", [])),
                    )
                    plan_injected = True

        if not plan_injected:
            extract_cfg = config.get("extractor", {})
            threshold = extract_cfg.get("threshold_chars", 100)
            if should_extract(content, threshold):
                extracted_items = await extract_items(content, context_block)
                if extracted_items:
                    extraction_block = format_extracted_context(extracted_items)
                    memory_context = "\n\n---\n\n".join(filter(None, [memory_context, extraction_block]))
                    logger.info("Pre-extraction injected %d item(s) into context", len(extracted_items))

    messages: list[dict] = list(format_chat_history(windowed_history))

    if image_path and image_path.exists():
        ocr_text = ocr_image(image_path)
        logger.info(
            "Attaching image %s (%d bytes), OCR: %d chars",
            image_path.name,
            image_path.stat().st_size,
            len(ocr_text),
        )
        user_content = (
            f"{content or message}\n\n---\n\n[EXTRACTED FROM IMAGE]\n\n{ocr_text}"
            if ocr_text
            else content or message
        )
    else:
        user_content = content or message

    messages.append({"role": "user", "content": user_content})

    if needs_compaction(messages):
        model = (
            config.get("compactor", {}).get("model")
            or config.get("orchestrator", {}).get("model", "qwen2.5:3b")
        )
        messages = await compact_history(messages, get_openai_client(), model)

    return agent, messages, memory_context
