from __future__ import annotations

from agents import Agent, function_tool

from helpers.agents.instructions_loader import load_instructions
from helpers.agents.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.memory_tools import forget_memory, prune_memory, store_memory
from tools.notes_tools import create_note, get_note, list_notes
from tools.slides_tools import draft_slides, render_slides

_executor: Agent | None = None

# Shared result storage — the executor writes here, the loop reads it
_last_step_result: dict = {"success": False, "summary": "", "error": ""}


@function_tool
def report_step_result(success: bool, summary: str, error: str = "") -> str:
    """Report the result of executing the current plan step.

    Call this when the step is complete (success or failure).

    Args:
        success: True if the step completed successfully, False otherwise.
        summary: Brief description of what was accomplished or attempted.
        error:   Error message if success is False, otherwise empty string.

    Returns:
        Acknowledgement string.
    """
    global _last_step_result
    _last_step_result = {"success": success, "summary": summary, "error": error}
    return "Step result recorded."


def get_last_step_result() -> dict:
    """Retrieve the result reported by the executor for the last step."""
    return _last_step_result.copy()


def reset_step_result() -> None:
    """Reset the step result before each execution."""
    global _last_step_result
    _last_step_result = {"success": False, "summary": "No result reported", "error": ""}


def get_executor_agent() -> Agent:
    global _executor
    if _executor is None:
        cfg = load_config()
        model_name = cfg.get("autonomous", {}).get("model", cfg["orchestrator"]["model"])
        _executor = Agent(
            name="Executor",
            model=get_model(model_name),
            instructions=load_instructions("executor"),
            tools=[
                store_memory,
                forget_memory,
                prune_memory,
                create_note,
                list_notes,
                get_note,
                draft_slides,
                render_slides,
                report_step_result,
            ],
        )
    return _executor
