"""Structured LLM invocation, with an optional bounded tool loop."""

from __future__ import annotations

from time import perf_counter
from typing import Any


def _usage(message: Any) -> dict[str, int] | None:
    value = getattr(message, "usage_metadata", None)
    if isinstance(value, dict):
        result = {key: int(value[key]) for key in ("input_tokens", "output_tokens", "total_tokens") if isinstance(value.get(key), int)}
        return result or None
    metadata = getattr(message, "response_metadata", None)
    value = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if isinstance(value, dict):
        result = {}
        for old, new in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"), ("total_tokens", "total_tokens")):
            if isinstance(value.get(old), int):
                result[new] = int(value[old])
        return result or None
    return None


def invoke_structured(llm: Any, messages: list[Any], schema: type, *, tools: list[Any] | None = None,
                      max_tool_rounds: int = 4) -> dict[str, Any]:
    """Invoke structured output; tools, when enabled, run in an allowlisted loop first."""
    started = perf_counter()
    working = list(messages)
    tool_calls = 0
    if tools:
        from langchain_core.messages import ToolMessage
        by_name = {tool.name: tool for tool in tools}
        model = llm.bind_tools(tools)
        for _ in range(max_tool_rounds):
            response = model.invoke(working)
            working.append(response)
            calls = getattr(response, "tool_calls", None) or []
            if not calls:
                break
            for call in calls:
                name = call.get("name")
                if name not in by_name:
                    raise ValueError(f"Model requested unavailable tool: {name}")
                value = by_name[name].invoke(call.get("args", {}))
                working.append(ToolMessage(content=str(value), tool_call_id=call["id"]))
                tool_calls += 1
        else:
            raise RuntimeError(f"Tool loop exceeded {max_tool_rounds} rounds")

    response = llm.with_structured_output(schema, include_raw=True).invoke(working)
    if isinstance(response, dict) and "parsed" in response:
        parsed, raw = response.get("parsed"), response.get("raw")
        if parsed is None:
            raise ValueError(f"Structured output parsing failed: {response.get('parsing_error')}")
    else:
        parsed, raw = response, None
    data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
    return {"result": data, "token_usage": _usage(raw),
            "elapsed_seconds": perf_counter() - started, "tool_calls": tool_calls}
