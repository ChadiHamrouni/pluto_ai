from __future__ import annotations

from agents.items import ToolCallItem, ToolCallOutputItem
from rich.console import Console

console = Console()


def _tool_name(raw_item) -> str:
    if hasattr(raw_item, "name"):
        return raw_item.name
    fn = raw_item.get("function", {}) if isinstance(raw_item, dict) else getattr(raw_item, "function", None)
    if isinstance(fn, dict):
        return fn.get("name", "?")
    return getattr(fn, "name", "?") if fn else "?"


def _tool_args(raw_item) -> str:
    if hasattr(raw_item, "arguments"):
        return raw_item.arguments or ""
    fn = raw_item.get("function", {}) if isinstance(raw_item, dict) else getattr(raw_item, "function", None)
    if isinstance(fn, dict):
        return fn.get("arguments", "")
    return getattr(fn, "arguments", "") or "" if fn else ""


def print_trace(result, source: str = "orchestrator") -> None:
    """Print agent routing, tool calls, and outputs for a Runner result."""
    console.print(f"\n  [dim]Route:[/dim]  [dim]{source}[/dim] → [bold cyan]{result.last_agent.name}[/bold cyan]")

    calls   = [i for i in result.new_items if isinstance(i, ToolCallItem)]
    outputs = [i for i in result.new_items if isinstance(i, ToolCallOutputItem)]

    if calls:
        for idx, call in enumerate(calls):
            name   = _tool_name(call.raw_item)
            args   = _tool_args(call.raw_item)
            output = str(outputs[idx].output) if idx < len(outputs) else "?"
            console.print(f"  [dim]Tool:[/dim]   [magenta]{name}[/magenta]({args})  →  [yellow]{output}[/yellow]")
    else:
        console.print("  [dim]Tools:[/dim]  [dim]none[/dim]")

    console.print()
