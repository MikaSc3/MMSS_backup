"""Normalized product events shared by the controller and Streamlit UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


def product_event(event_type: str, *, session_id: str | None = None,
                  correlation_id: str | None = None, **payload: Any) -> dict[str, Any]:
    return {"event_id": uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type, "session_id": session_id,
            "correlation_id": correlation_id, **payload}


AGENT_TYPES = {
    "assistant_message": "agent.message.completed",
    "tool_started": "tool.started",
    "tool_completed": "tool.completed",
}

WORKFLOW_TYPES = {
    "stage_started": "workflow.stage.started",
    "stage_progress": "workflow.stage.progress",
    "stage_completed": "workflow.stage.completed",
    "stage_failed": "workflow.stage.failed",
    "checkpoint": "workflow.checkpoint",
    "workflow_completed": "session.completed",
    "artifact_updated": "artifact.updated",
}


def normalize_agent_event(raw: Mapping[str, Any], *, session_id: str,
                          correlation_id: str) -> dict[str, Any]:
    event_type = AGENT_TYPES.get(str(raw.get("type")), f"agent.{raw.get('type', 'event')}")
    payload = {key: value for key, value in raw.items() if key != "type"}
    return product_event(event_type, session_id=session_id,
                         correlation_id=correlation_id, **payload)


def normalize_workflow_event(raw: Mapping[str, Any], *, session_id: str,
                             correlation_id: str | None) -> dict[str, Any]:
    event_type = WORKFLOW_TYPES.get(str(raw.get("type")), f"workflow.{raw.get('type', 'event')}")
    payload = {key: value for key, value in raw.items()
               if key not in {"type", "session_id"}}
    return product_event(event_type, session_id=session_id,
                         correlation_id=correlation_id, **payload)
