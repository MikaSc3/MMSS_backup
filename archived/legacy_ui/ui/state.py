# -*- coding: utf-8 -*-
"""
Session state management for STEP2FFA UI.

Initializes and manages all Streamlit session state variables.
"""

import streamlit as st
import queue
from threading import Lock


def init_session_state():
    """Initialize session state variables."""
    
    # Upload & Session
    if "session_root" not in st.session_state:
        st.session_state.session_root = None
    
    if "assembly_name" not in st.session_state:
        st.session_state.assembly_name = None
    
    if "workflow_started" not in st.session_state:
        st.session_state.workflow_started = False
    
    if "workflow_complete" not in st.session_state:
        st.session_state.workflow_complete = False
    
    if "workflow_error" not in st.session_state:
        st.session_state.workflow_error = None

    if "ui_start_time" not in st.session_state:
        st.session_state.ui_start_time = None
    
    # Messages & UI
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "debug_messages" not in st.session_state:
        st.session_state.debug_messages = []

    if "activity_messages" not in st.session_state:
        st.session_state.activity_messages = []

    if "awaiting_user_input" not in st.session_state:
        st.session_state.awaiting_user_input = False

    if "active_agent" not in st.session_state:
        st.session_state.active_agent = None

    if "input_prompt" not in st.session_state:
        st.session_state.input_prompt = None
    
    # Workflow State
    if "workflow_phase" not in st.session_state:
        st.session_state.workflow_phase = "IDLE"
    
    if "workflow_state" not in st.session_state:
        st.session_state.workflow_state = {}
    
    if "progress_step" not in st.session_state:
        st.session_state.progress_step = 0

    if "ffa_assessment_path" not in st.session_state:
        st.session_state.ffa_assessment_path = None

    if "ffa_report_path" not in st.session_state:
        st.session_state.ffa_report_path = None

    if "ffa_pdf_path" not in st.session_state:
        st.session_state.ffa_pdf_path = None

    if "ffa_plot_path" not in st.session_state:
        st.session_state.ffa_plot_path = None

    if "ffa_metrics_json" not in st.session_state:
        st.session_state.ffa_metrics_json = None
    
    # Agent 2 Approval
    if "user_approval_pending" not in st.session_state:
        st.session_state.user_approval_pending = False
    
    if "approval_decision" not in st.session_state:
        st.session_state.approval_decision = None
    
    # Event queue for thread-safe communication
    if "event_queue" not in st.session_state:
        st.session_state.event_queue = queue.Queue()
    
    if "event_queue_lock" not in st.session_state:
        st.session_state.event_queue_lock = Lock()
    
    # Input queue for agent user input
    if "input_queue" not in st.session_state:
        st.session_state.input_queue = queue.Queue()


def process_event_queue() -> bool:
    """Process all pending events from the queue.
    
    Called by main thread every rerun to read events from worker thread.
    Thread-safe: worker thread puts events, main thread gets them.
    """
    if "event_queue" not in st.session_state:
        return False
    
    event_queue = st.session_state.event_queue
    processed = False
    
    while not event_queue.empty():
        try:
            event = event_queue.get_nowait()
            _handle_event(event)
            processed = True
        except queue.Empty:
            break

    return processed


def _handle_event(event: dict):
    """Handle a single event from the queue.
    
    Args:
        event: Event dict with keys: type, and other fields depending on type
    """
    event_type = event.get("type")
    
    if event_type == "session_created":
        # Session was created in worker thread
        st.session_state.session_root = event.get("session_root")
        st.session_state.assembly_name = event.get("assembly_name")
    
    elif event_type == "message":
        # Chat message from agent or system
        role = event.get("role", "system")
        content = event.get("content", "")
        if role == "system":
            add_activity_message(content)
        else:
            if role == "agent":
                phase = event.get("phase") or st.session_state.workflow_phase
                role = {
                    "AGENT_1": "agent1",
                    "AGENT_2_LOOP": "agent2",
                    "AGENT_3": "agent3",
                }.get(phase, st.session_state.get("active_agent") or "agent")
            add_message(
                role=role,
                content=content,
                phase=event.get("phase")
            )
    
    elif event_type == "status":
        # Status message for debug box
        content = event.get("content", "")
        add_debug_message(content)
        add_activity_message(content)

    elif event_type == "input_waiting":
        st.session_state.awaiting_user_input = True
        st.session_state.active_agent = event.get("agent")
        st.session_state.input_prompt = event.get("prompt")
        add_activity_message(event.get("prompt", "Waiting for user input."))

    elif event_type == "input_received":
        st.session_state.awaiting_user_input = False
        st.session_state.input_prompt = None
    
    elif event_type == "phase_changed":
        # Update current phase
        phase = event.get("phase", "IDLE")
        st.session_state.workflow_phase = phase
        phase_progress = {
            "PHASE_1": 1,
            "PHASE_1_STEPPARSER": 1,
            "PHASE_1_PATHS": 1,
            "PHASE_1_ANALYSIS": 2,
            "PHASE_2a": 2,
            "AGENT_1": 3,
            "PHASE_2b": 4,
            "PHASE_2B_MONOPARTS": 4,
            "PHASE_2B_SEQUENCE": 5,
            "AGENT_2_LOOP": 6,
            "PHASE_4": 7,
            "PHASE_4_RENDERING": 7,
            "PHASE_4_INTERACTIONS": 8,
            "PHASE_4_FFA": 9,
            "PHASE_4_REPORT": 10,
            "AGENT_3": 11,
            "DONE": 11,
        }
        if phase in phase_progress:
            st.session_state.progress_step = max(
                st.session_state.get("progress_step", 0),
                phase_progress[phase],
            )
    
    elif event_type == "progress":
        # Update progress bar step
        st.session_state.progress_step = max(
            st.session_state.get("progress_step", 0),
            event.get("step", 0),
        )

    elif event_type == "artifacts":
        st.session_state.ffa_assessment_path = event.get("ffa_assessment_path")
        st.session_state.ffa_report_path = event.get("ffa_report_path")
        st.session_state.ffa_pdf_path = event.get("ffa_pdf_path")
        st.session_state.ffa_plot_path = event.get("ffa_plot_path")
        st.session_state.ffa_metrics_json = event.get("ffa_metrics_json")
    
    elif event_type == "error":
        # Error occurred
        st.session_state.workflow_error = event.get("content", "Unknown error")
        add_debug_message(f"ERROR: {event.get('content', 'Unknown error')}")
        add_activity_message(f"ERROR: {event.get('content', 'Unknown error')}")
    
    elif event_type == "complete":
        # Workflow finished
        st.session_state.workflow_complete = True
        st.session_state.awaiting_user_input = False
        add_debug_message("Workflow complete")
        add_activity_message("Workflow complete")


def add_message(role: str, content: str, phase: str = None):
    """Add message to chat history.
    
    Args:
        role: "system" | "agent1" | "agent2" | "agent3" | "user"
        content: Message text
        phase: Current workflow phase
    """
    from datetime import datetime
    
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "phase": phase or st.session_state.workflow_phase
    }

    if st.session_state.messages:
        previous = st.session_state.messages[-1]
        if previous.get("role") == message["role"] and previous.get("content") == message["content"]:
            return

    st.session_state.messages.append(message)


def add_debug_message(msg: str):
    """Add status message to debug box (FIFO: max 4 lines).
    
    Args:
        msg: Status message (e.g., "✓ Phase 1 complete")
    """
    st.session_state.debug_messages.append(msg)
    
    # Keep only last 4 messages
    if len(st.session_state.debug_messages) > 4:
        st.session_state.debug_messages.pop(0)


def add_activity_message(msg: str):
    """Add workflow status to the activity feed."""
    if not msg:
        return
    if st.session_state.activity_messages and st.session_state.activity_messages[-1] == msg:
        return
    st.session_state.activity_messages.append(msg)
    if len(st.session_state.activity_messages) > 12:
        st.session_state.activity_messages.pop(0)


def get_messages() -> list:
    """Get all messages."""
    return st.session_state.messages


def get_debug_messages() -> list:
    """Get debug messages (last 4)."""
    return st.session_state.debug_messages


def get_activity_messages() -> list:
    """Get recent workflow activity messages."""
    return st.session_state.activity_messages


def clear_messages():
    """Clear chat history."""
    st.session_state.messages = []


def clear_debug_messages():
    """Clear debug messages."""
    st.session_state.debug_messages = []
