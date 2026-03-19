from __future__ import annotations

import asyncio

from agents import Agent

from helpers.core.logger import get_logger

logger = get_logger(__name__)

_AGENT_TIMEOUT = 120  # seconds


async def run_agent(agent: Agent, messages: list[dict]) -> str:
    """
    Run an agent turn by calling Ollama directly via the OpenAI-compat client.

    The OpenAI Agents SDK Runner crashes on Ollama responses that don't
    perfectly match OpenAI's API (tool call IDs, finish reasons, etc.).
    We bypass Runner entirely and call chat.completions.create directly —
    same approach used by the compactor which works reliably.

    Tool calls (store_memory, etc.) are handled by injecting the tool
    definitions and parsing the response manually when the model requests them.
    """
    from helpers.agents.ollama_client import get_openai_client
    from helpers.core.config_loader import load_config
    cfg = load_config()
    # Pick the model for this agent based on its name
    _model_map = {
        "Notes":      cfg.get("notes_agent", {}).get("model", cfg["orchestrator"]["model"]),
        "Slides":     cfg.get("slides_agent", {}).get("model", cfg["orchestrator"]["model"]),
        "Planner":    cfg.get("autonomous", {}).get("model", cfg["orchestrator"]["model"]),
        "Executor":   cfg.get("autonomous", {}).get("model", cfg["orchestrator"]["model"]),
    }
    model_name = _model_map.get(agent.name, cfg["orchestrator"]["model"])
    client = get_openai_client()

    # Build tool schemas from the agent's tool list
    tools_payload = []
    tool_map = {}
    for t in (agent.tools or []):
        schema = getattr(t, "params_json_schema", None)
        name = getattr(t, "name", None)
        desc = getattr(t, "description", "")
        if name and schema:
            tools_payload.append({
                "type": "function",
                "function": {"name": name, "description": desc, "parameters": schema},
            })
            tool_map[name] = t

    kwargs: dict = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.5,
    }
    if tools_payload:
        kwargs["tools"] = tools_payload

    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(**kwargs),
            timeout=_AGENT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Agent '%s' timed out after %ds", agent.name, _AGENT_TIMEOUT)
        raise RuntimeError(f"Agent timed out after {_AGENT_TIMEOUT}s")
    except Exception as exc:
        logger.exception("Agent '%s' LLM call failed: %s", agent.name, exc)
        raise RuntimeError(f"Agent LLM call failed: {exc}") from exc

    choice = resp.choices[0]

    # If model requested tool calls, execute them and do a follow-up turn
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        import json
        tool_results_msgs = [{"role": "assistant", "content": choice.message.content or "", "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in choice.message.tool_calls
        ]}]
        for tc in choice.message.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments or "{}")
            tool_fn = tool_map.get(fn_name)
            if tool_fn:
                try:
                    result = tool_fn(**fn_args)
                    if asyncio.iscoroutine(result):
                        result = await result
                    tool_result = str(result)
                except Exception as exc:
                    tool_result = f"Error: {exc}"
            else:
                tool_result = f"Unknown tool: {fn_name}"
            tool_results_msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

        follow_up_messages = messages + tool_results_msgs
        follow_kwargs = {**kwargs, "messages": follow_up_messages}
        follow_kwargs.pop("tools", None)  # no more tools on follow-up
        try:
            follow_resp = await asyncio.wait_for(
                client.chat.completions.create(**follow_kwargs),
                timeout=_AGENT_TIMEOUT,
            )
            return follow_resp.choices[0].message.content or ""
        except Exception as exc:
            logger.exception("Agent '%s' follow-up call failed: %s", agent.name, exc)
            raise RuntimeError(f"Agent follow-up failed: {exc}") from exc

    return choice.message.content or ""
