# -*- coding: utf-8 -*-
"""Conversation component for the three interactive workflow agents."""

import html
from datetime import datetime

import streamlit as st

from ui.state import add_message, get_messages


AGENT_META = {
    "agent1": ("A1", "Assembly Discussion", "#179C7D"),
    "agent2": ("A2", "Assembly Order Discussion", "#0E7C9B"),
    "agent3": ("A3", "FfA Discussion", "#6D5BD0"),
    "agent": ("AI", "Agent", "#179C7D"),
    "user": ("IN", "You", "#1F2933"),
}


def render_chat_window():
    """Render the agent conversation and the shared user input."""
    messages = [
        msg for msg in get_messages()
        if msg.get("role") != "system" and msg.get("content", "").strip()
    ]

    chat_container = st.container(height=600)
    with chat_container:
        if not messages:
            _render_pending_agents()
        else:
            for msg in messages:
                _render_message(msg)

    _render_input_area()


def _render_input_area():
    workflow_running = st.session_state.get("workflow_started") and not st.session_state.get("workflow_complete")
    workflow_error = st.session_state.get("workflow_error")
    awaiting_input = st.session_state.get("awaiting_user_input", False)

    if workflow_error:
        st.error(workflow_error)
        return

    if st.session_state.get("workflow_complete"):
        if st.session_state.get("ffa_pdf_path"):
            st.success("Workflow completed. The final FFA PDF report is ready.")
        else:
            st.success("Workflow completed.")
        return

    if not workflow_running:
        st.caption("Upload a STEP file to start.")
        return

    active_agent = st.session_state.get("active_agent") or "agent"
    prompt = st.session_state.get("input_prompt")

    if awaiting_input:
        agent_name = AGENT_META.get(active_agent, AGENT_META["agent"])[1]
        st.info(prompt or f"{agent_name} is waiting for your answer.")
    else:
        st.caption("Input unlocks when an agent asks for feedback.")

    def _on_user_input():
        user_input = st.session_state.get("user_input_field", "").strip()
        if not user_input:
            return

        input_queue = st.session_state.get("input_queue")
        if input_queue:
            input_queue.put(user_input)

        add_message("user", user_input)
        st.session_state.awaiting_user_input = False
        st.session_state.input_prompt = None
        st.session_state.user_input_field = ""
        st.rerun()

    col_input, col_send = st.columns([5, 1])
    with col_input:
        st.text_input(
            "Your message",
            placeholder="Reply to the active agent...",
            key="user_input_field",
            label_visibility="collapsed",
            disabled=not awaiting_input,
            on_change=_on_user_input,
        )

    with col_send:
        if st.button("Send", key="send_btn", width="stretch", disabled=not awaiting_input):
            _on_user_input()


def _render_message(msg: dict):
    """Render one chat message."""
    role = msg.get("role", "unknown")
    content = html.escape(msg.get("content", ""))

    if role == "user":
        icon, label, accent = AGENT_META["user"]
        bg_color = "#eef7f1"
        border_color = accent
        text_color = "#14301f"
        align = "right"
    else:
        icon, label, accent = AGENT_META.get(role, AGENT_META["agent"])
        bg_color = "#FFFFFF"
        border_color = accent
        text_color = "#1f2937"
        align = "left"

    timestamp = _format_timestamp(msg.get("timestamp"))
    status = _message_status(role)
    status_class = status.lower().replace(" ", "-")

    st.markdown(
        f"""
        <div style="display:flex; justify-content:{'flex-end' if align == 'right' else 'flex-start'}; margin:0.72rem 0;">
          <div class="agent-card {status_class}" style="width:100%; background:{bg_color}; border:1px solid #D9E2E7; border-left:4px solid {border_color}; border-radius:12px; padding:0.85rem 0.95rem; box-shadow:0 10px 24px rgba(17,24,39,0.045);">
            <div style="display:flex; gap:0.75rem; align-items:flex-start;">
              <div style="width:38px; height:38px; border-radius:50%; background:{border_color}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:0.88rem; flex:0 0 auto;">{icon}</div>
              <div style="min-width:0; flex:1;">
                <div style="display:flex; justify-content:space-between; gap:0.75rem; align-items:center;">
                  <div style="color:#111827; font-size:1.02rem; font-weight:760;">{label}</div>
                  <div style="color:#6B7280; font-size:0.82rem;">{timestamp}</div>
                </div>
                <div style="display:flex; gap:0.45rem; margin:0.35rem 0 0.45rem 0; flex-wrap:wrap;">
                  <span style="border:1px solid #D9E2E7; border-radius:999px; padding:0.12rem 0.45rem; color:#6B7280; font-size:0.78rem;">{status}</span>
                  <span style="border:1px solid rgba(23,156,125,0.25); background:rgba(23,156,125,0.09); border-radius:999px; padding:0.12rem 0.45rem; color:#08745D; font-size:0.78rem;">Confidence: n/a</span>
                </div>
                <div style="color:{text_color}; font-size:1.06rem; line-height:1.5; white-space:pre-wrap; overflow-wrap:anywhere;">{content}</div>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pending_agents():
    for role in ("agent1", "agent2", "agent3"):
        icon, label, accent = AGENT_META[role]
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #D9E2E7; border-radius:12px; padding:0.85rem; margin:0.6rem 0; opacity:0.74;">
              <div style="display:flex; align-items:center; gap:0.7rem;">
                <div style="width:34px; height:34px; border-radius:50%; border:1px solid {accent}; color:{accent}; display:flex; align-items:center; justify-content:center; font-weight:800;">{icon}</div>
                <div>
                  <div style="font-weight:760; color:#1F2933;">{label}</div>
                  <div style="color:#6B7280; font-size:0.9rem;">Pending</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _message_status(role: str) -> str:
    if role == "user":
        return "Submitted"
    if st.session_state.get("awaiting_user_input") and st.session_state.get("active_agent") == role:
        return "Feedback requested"
    if st.session_state.get("active_agent") == role and not st.session_state.get("workflow_complete"):
        return "Active"
    return "Completed"


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "--:--:--"
    try:
        return datetime.fromisoformat(value).strftime("%H:%M:%S")
    except ValueError:
        return "--:--:--"
