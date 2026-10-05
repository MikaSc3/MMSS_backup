"""LangChain agent runtime adapters for the product-facing workflow agent.

This module deliberately keeps domain artifacts and manifests outside graph
state.  They remain the durable engineering record; LangChain state is used to
run one conversational turn with explicit, state-dependent capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Non-persisted context available to one agent invocation."""

    allowed_tool_names: frozenset[str]
    user_message: str
    emit: Callable[[str], None] | None = None


class AllowedToolsMiddleware(AgentMiddleware):
    """Expose only workflow capabilities legal for the current session state."""

    def wrap_model_call(self, request: ModelRequest, handler: Callable[..., Any]) -> Any:
        context = request.runtime.context
        allowed = (context.allowed_tool_names
                   if isinstance(context, AgentRuntimeContext) else frozenset())
        tools = [tool for tool in request.tools if getattr(tool, "name", None) in allowed]
        return handler(request.override(tools=tools))


class ToolEventMiddleware(AgentMiddleware):
    """Emit application events around tool calls without a hand-written loop."""

    def __init__(self, callback: Callable[[str, Mapping[str, Any]], None]):
        self.callback = callback

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[..., Any]) -> Any:
        call = request.tool_call
        context = request.runtime.context
        user_message = context.user_message if isinstance(context, AgentRuntimeContext) else ""
        raw_fields = {
            "revise_sequence": "raw_user_message",
            "automation_concept_idea_generator": "raw_user_message",
            "revise_automation_concept": "raw_user_message",
            "layout_planner": "raw_user_message",
            "revise_layout": "raw_user_message",
            "cost_planner": "raw_user_message",
        }
        field = raw_fields.get(str(call.get("name", "")))
        if field:
            call = {**call, "args": {**(call.get("args") or {}), field: user_message}}
            request = request.override(tool_call=call)
        name = str(call.get("name", ""))
        arguments = call.get("args") or {}
        self.callback("started", {"tool": name, "arguments": arguments})
        try:
            result = handler(request)
        except Exception as exc:
            self.callback("completed", {
                "tool": name,
                "result": {"status": "error", "error": f"{type(exc).__name__}: {exc}"},
            })
            raise
        self.callback("completed", {"tool": name, "result": result})
        return result
