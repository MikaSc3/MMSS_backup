"""Compact terminal-style presentation of normalized product events."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Mapping
from urllib.parse import quote

import streamlit as st


def _time(value: Any) -> str:
    if not isinstance(value, str):
        return "--:--:--"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return value[11:19] if len(value) >= 19 else "--:--:--"


def event_line(event: Mapping[str, Any]) -> str | None:
    kind = str(event.get("type", ""))
    stamp = _time(event.get("timestamp"))
    stage = str(event.get("stage") or "workflow")
    if kind == "session.created":
        message = f"[session] created {event.get('assembly_name') or event.get('session_id') or ''}"
    elif kind == "session.resumed":
        message = f"[session] resumed {event.get('assembly_name') or event.get('session_id') or ''}"
    elif kind == "session.setup.progress":
        message = f"[setup] {str(event.get('operation') or 'working').replace('_', ' ')}"
    elif kind == "session.setup.completed":
        message = "[setup] workflow agent ready"
    elif kind == "agent.turn.started":
        message = f"[agent] {str(event.get('command') or 'turn').replace('_', ' ')} started"
    elif kind == "agent.turn.completed":
        message = f"[agent] {str(event.get('command') or 'turn').replace('_', ' ')} complete"
    elif kind == "agent.turn.failed":
        message = f"[error] {event.get('error') or 'operation failed'}"
    elif kind == "terminal.output":
        message = f"[{event.get('stream') or 'stdout'}] {event.get('line') or ''}"
    elif kind == "workflow.stage.started":
        message = f"[{stage}] started"
    elif kind == "workflow.stage.progress":
        item = str(event.get("item") or "working").replace("_", " ")
        completed, total = event.get("completed"), event.get("total")
        counter = (f" {completed}/{total}" if type(completed) is int and type(total) is int
                   else f" {completed}" if type(completed) is int else "")
        message = f"[{stage}] {item}{counter}"
    elif kind == "workflow.stage.completed":
        message = f"[{stage}] complete"
    elif kind == "workflow.stage.failed":
        message = f"[{stage}] FAILED: {event.get('error') or 'unknown error'}"
    elif kind == "workflow.checkpoint":
        message = f"[checkpoint] {str(event.get('checkpoint') or 'review').replace('_', ' ')}"
    elif kind == "tool.started":
        message = f"[tool] {event.get('tool') or 'operation'} started"
    elif kind == "tool.completed":
        result = event.get("result")
        failed = isinstance(result, Mapping) and result.get("status") == "error"
        message = f"[tool] {event.get('tool') or 'operation'} {'failed' if failed else 'complete'}"
    elif kind == "session.completed":
        message = "[workflow] assessment complete"
    else:
        return None
    return f"{stamp}  {message}".rstrip()


def console_lines(events: list[dict[str, Any]], limit: int = 18) -> list[str]:
    lines = [line for event in events if (line := event_line(event))]
    return lines[-limit:]


def render_activity_console(st: Any, events: list[dict[str, Any]], *, busy: bool) -> None:
    lines = console_lines(events)
    if not lines and not busy:
        return
    if not lines:
        lines = ["--:--:--  [workflow] waiting for first event"]
    cursor = "\n<span class='console-cursor'>▋</span>" if busy else ""
    body = escape("\n".join(lines)).replace("\n", "<br>") + cursor
    document = f"""
        <style>
          html, body {{ margin:0; padding:0; overflow:hidden; background:transparent; }}
          .header {{ box-sizing:border-box; height:1.35rem; padding:.2rem .55rem;
            border:1px solid #9bb6c3; border-bottom:0; background:#dce9ee;
            color:#1d1d1d; font:700 .58rem monospace; letter-spacing:.12em; }}
          .terminal {{ box-sizing:border-box; height:calc(100% - 1.35rem); overflow-y:auto;
            padding:.45rem .55rem; border:1px solid #1d1d1d; background:#1d1d1d;
            color:#fff; font:500 .65rem/1.35 monospace; white-space:nowrap; }}
          .cursor {{ color:#e3a52f; }}
        </style>
        <div class="header">LIVE ACTIVITY</div>
        <div id="terminal" class="terminal">{body}</div>
        <script>
          const terminal = document.getElementById("terminal");
          terminal.scrollTop = terminal.scrollHeight;
        </script>
        """
    st.iframe("data:text/html;charset=utf-8," + quote(document), height=134)
