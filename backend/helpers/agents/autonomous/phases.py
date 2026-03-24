"""The three phases of the autonomous loop: planning, step execution, and synthesis."""

from __future__ import annotations

import json

from agents import RunConfig, Runner
from agents.items import ToolCallItem
from agents.stream_events import RunItemStreamEvent

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.core.logger import get_logger
from models.plan import ExecutionPlan, PlanStep
from models.results import StepResult

logger = get_logger(__name__)

_RUN_CONFIG = RunConfig(tracing_disabled=True)
_SYNTHESIS_INSTRUCTION = load_instructions("autonomous/synthesizer")


# ── Utility ───────────────────────────────────────────────────────────────────


def extract_url_from_tool_call(item: ToolCallItem) -> str | None:
    """Return the URL (or None) from a fetch_page or web_search tool call item."""
    try:
        raw = item.raw_item
        fn = getattr(raw, "function", None)
        name: str = getattr(fn, "name", None) or getattr(raw, "name", None) or ""
        args_str: str = getattr(fn, "arguments", None) or getattr(raw, "arguments", None) or "{}"
        args: dict = json.loads(args_str) if isinstance(args_str, str) else args_str
        if name == "fetch_page":
            return args.get("url") or None
        if name == "web_search":
            query = args.get("query", "")
            return f"search:{query}" if query else None
    except Exception:
        pass
    return None


# ── Phase 1: Planning ─────────────────────────────────────────────────────────


async def run_planning(task: str) -> list[PlanStep]:
    """Ask the planner agent to decompose *task* into PlanStep objects."""
    from my_agents.planner_agent import get_planner_agent

    logger.info("─── Planning: %s ───", task[:120])
    try:
        result = await Runner.run(
            starting_agent=get_planner_agent(),
            input=f"Task: {task}",
            run_config=_RUN_CONFIG,
        )
        plan_output = result.final_output
        logger.info("Planner output: %s", repr(plan_output)[:300])
        if not plan_output or not plan_output.steps:
            logger.error("Planner returned no steps")
            return []
        steps = [PlanStep(id=s.id, description=s.description) for s in plan_output.steps]
        for s in steps:
            logger.info("  Step %d: %s", s.id, s.description)
        return steps
    except Exception as exc:
        logger.error("Planning failed: %s", exc, exc_info=True)
        return []


# ── Phase 2: Step execution ───────────────────────────────────────────────────


def build_step_context(
    task: str, plan: ExecutionPlan, step: PlanStep, previous_results: list[str]
) -> str:
    """Build the input prompt for the executor agent for a single step."""
    lines = [f"Task: {task}\n\nFull plan:"]
    for s in plan.steps:
        lines.append(f"  Step {s.id}: {s.description} [{s.status}]")
    if previous_results:
        lines.append("\nPrevious step results:")
        for r in previous_results:
            lines.append(f"  - {r}")
    lines.append(f"\nNow execute step {step.id}: {step.description}")
    return "\n".join(lines)


async def execute_step(
    step: PlanStep,
    context: str,
    on_link: callable,
) -> StepResult:
    """Run a single step via streaming so tool calls are visible in real-time.

    Args:
        step: The plan step to execute.
        context: The full input prompt for the executor agent.
        on_link: Callback(url: str) invoked immediately when a link is discovered.
    """
    from my_agents.executor_agent import get_executor_agent

    logger.info("─── Executing step %d: %s ───", step.id, step.description)

    links: list[str] = []
    tool_names: list[str] = []

    try:
        streamed = Runner.run_streamed(
            starting_agent=get_executor_agent(),
            input=context,
            run_config=_RUN_CONFIG,
            max_turns=20,
        )
        async for event in streamed.stream_events():
            if not isinstance(event, RunItemStreamEvent):
                continue
            if event.name != "tool_called":
                continue
            item = event.item
            if not isinstance(item, ToolCallItem):
                continue

            raw = item.raw_item
            fn = getattr(raw, "function", None)
            name: str = getattr(fn, "name", None) or getattr(raw, "name", None) or ""
            if name:
                tool_names.append(name)

            url = extract_url_from_tool_call(item)
            if url and url not in links:
                links.append(url)
                on_link(url)

        summary = (streamed.final_output or "").strip()

    except Exception as exc:
        logger.warning("Executor raised for step %d: %s", step.id, exc, exc_info=True)
        return StepResult(success=False, error=str(exc))

    logger.info(
        "Step %d — tools=%s links=%d summary_len=%d",
        step.id, tool_names, len(links), len(summary),
    )

    if not tool_names and not summary:
        logger.warning("Step %d: no tools called and no output", step.id)
        return StepResult(
            success=False,
            error="Executor produced no output and called no tools.",
            links=links,
        )

    if not summary and tool_names:
        summary = f"Used: {', '.join(tool_names)}"

    return StepResult(success=True, summary=summary, links=links)


# ── Phase 3: Synthesis ────────────────────────────────────────────────────────


async def synthesise(task: str, previous_results: list[str]) -> str:
    """Produce a coherent final answer from all step summaries."""
    from my_agents.orchestrator import get_orchestrator

    logger.info("─── Synthesising final answer (%d results) ───", len(previous_results))
    user_content = (
        f"Original task: {task}\n\n"
        "Step results:\n"
        + "\n".join(f"  - {r}" for r in previous_results)
    )
    synthesizer = get_orchestrator().clone(instructions=_SYNTHESIS_INSTRUCTION)
    try:
        result = await Runner.run(
            starting_agent=synthesizer,
            input=user_content,
            run_config=_RUN_CONFIG,
            max_turns=3,
        )
        response = (result.final_output or "").strip()
        logger.info("Synthesis complete — %d chars", len(response))
        return response
    except Exception as exc:
        logger.warning("Synthesis failed: %s", exc, exc_info=True)
        return "\n".join(previous_results)
