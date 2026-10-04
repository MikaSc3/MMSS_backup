"""Thread-safe Streamlit state handling for App V3."""

from __future__ import annotations

import queue
import time
from datetime import datetime
from typing import Any

import streamlit as st


DEFAULTS = {
    "v3_session_root": None,
    "v3_assembly_name": None,
    "v3_started": False,
    "v3_complete": False,
    "v3_error": None,
    "v3_started_at": None,
    "v3_messages": [],
    "v3_tools": [],
    "v3_activity": [],
    "v3_phase": "READY",
    "v3_phase_started_at": None,
    "v3_progress_step": 0,
    "v3_awaiting_input": False,
    "v3_input_prompt": None,
    "v3_input_request_id": 0,
    "v3_submitted_input_request_id": None,
    "v3_documents": [],
    "v3_ingestion_warnings": [],
    "v3_artifacts": {},
    "v3_intro_started": False,
    "v3_intro_error": None,
    "v3_last_autoscroll_message_count": -1,
    "v3_sequence_display_step": 0,
    "v3_sequence_display_changed_at": None,
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
    if "v3_event_queue" not in st.session_state:
        st.session_state.v3_event_queue = queue.Queue()
    if "v3_input_queue" not in st.session_state:
        st.session_state.v3_input_queue = queue.Queue()


def reset_state() -> None:
    event_queue = queue.Queue()
    input_queue = queue.Queue()
    for key, value in DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
    for widget_key in ("v3_step_upload", "v3_document_upload", "v3_user_input", "v3_render_mode"):
        st.session_state.pop(widget_key, None)
    st.session_state.v3_event_queue = event_queue
    st.session_state.v3_input_queue = input_queue


def process_events() -> bool:
    processed = False
    events = st.session_state.v3_event_queue
    while True:
        try:
            event = events.get_nowait()
        except queue.Empty:
            break
        _handle_event(event)
        processed = True
    return processed


def add_user_message(content: str) -> None:
    st.session_state.v3_messages.append(
        {"role": "user", "content": content, "timestamp": datetime.now().isoformat()}
    )


def _handle_event(event: dict[str, Any]) -> None:
    event_type = event.get("type")
    now = datetime.now().isoformat()

    if event_type == "session_created":
        st.session_state.v3_session_root = event.get("session_root")
        st.session_state.v3_assembly_name = event.get("assembly_name")
        _activity(f"Session created for {event.get('assembly_name')}")
    elif event_type == "agent_message":
        st.session_state.v3_messages.append(
            {
                "role": "agent",
                "content": event.get("content", ""),
                "timestamp": now,
                "phase": event.get("phase"),
            }
        )
    elif event_type == "input_waiting":
        if not st.session_state.v3_awaiting_input:
            st.session_state.v3_input_request_id += 1
        st.session_state.v3_awaiting_input = True
        st.session_state.v3_input_prompt = event.get("prompt")
        st.session_state.v3_phase = event.get("phase") or st.session_state.v3_phase
        checkpoint_progress = {
            "ASSEMBLY_DIALOGUE": 4,
            "SEQUENCE_DIALOGUE": 7,
            "REPORT_DIALOGUE": 11,
        }
        st.session_state.v3_progress_step = max(
            st.session_state.v3_progress_step,
            checkpoint_progress.get(st.session_state.v3_phase, 0),
        )
        _activity(event.get("prompt") or "Waiting for user input")
    elif event_type == "input_received":
        st.session_state.v3_awaiting_input = False
        st.session_state.v3_input_prompt = None
    elif event_type == "phase_changed":
        next_phase = event.get("phase", st.session_state.v3_phase)
        if next_phase != st.session_state.v3_phase:
            st.session_state.v3_phase_started_at = time.time()
        st.session_state.v3_phase = next_phase
        st.session_state.v3_progress_step = max(
            st.session_state.v3_progress_step,
            int(event.get("progress_step") or 0),
        )
    elif event_type == "documents_ingested":
        st.session_state.v3_documents = event.get("files") or []
        st.session_state.v3_ingestion_warnings = event.get("warnings") or []
        _activity(f"Read {event.get('count', 0)} supporting document(s)")
    elif event_type == "tool_started":
        record = {
            "id": event.get("tool_call_id") or f"{event.get('tool_name')}-{len(st.session_state.v3_tools)}",
            "name": event.get("tool_name", "Tool"),
            "status": "running",
            "started_at": now,
            "finished_at": None,
            "duration_seconds": None,
            "arguments": event.get("arguments") or {},
            "observation": "",
            "error": None,
            "phase": event.get("phase"),
        }
        st.session_state.v3_tools.append(record)
        _activity(f"Started {record['name']}")
    elif event_type in {"tool_completed", "tool_failed"}:
        record = _find_tool(event)
        if record is None:
            record = {
                "id": event.get("tool_call_id") or event.get("tool_name"),
                "name": event.get("tool_name", "Tool"),
                "arguments": event.get("arguments") or {},
                "started_at": None,
                "phase": event.get("phase"),
            }
            st.session_state.v3_tools.append(record)
        record.update(
            {
                "status": "complete" if event_type == "tool_completed" else "failed",
                "finished_at": now,
                "duration_seconds": event.get("duration_seconds"),
                "observation": event.get("observation", ""),
                "error": event.get("error"),
            }
        )
        _activity(f"{'Completed' if event_type == 'tool_completed' else 'Failed'} {record['name']}")
        if event_type == "tool_failed":
            st.session_state.v3_error = record["error"]
    elif event_type == "artifacts":
        st.session_state.v3_artifacts.update(event)
    elif event_type == "error":
        st.session_state.v3_error = event.get("content", "Unknown workflow error")
    elif event_type == "intro_error":
        st.session_state.v3_intro_error = event.get("content")
    elif event_type == "complete":
        st.session_state.v3_complete = True
        st.session_state.v3_awaiting_input = False
        st.session_state.v3_progress_step = 11
        st.session_state.v3_phase = "COMPLETE"
        _activity("Workflow finished")


def _find_tool(event: dict[str, Any]) -> dict[str, Any] | None:
    call_id = event.get("tool_call_id")
    name = event.get("tool_name")
    for record in reversed(st.session_state.v3_tools):
        if call_id and record.get("id") == call_id:
            return record
        if record.get("name") == name and record.get("status") == "running":
            return record
    return None


def _activity(message: str) -> None:
    if not message:
        return
    st.session_state.v3_activity.append(
        {"content": message, "timestamp": datetime.now().isoformat()}
    )
    st.session_state.v3_activity = st.session_state.v3_activity[-30:]
