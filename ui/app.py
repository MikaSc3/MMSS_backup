# -*- coding: utf-8 -*-
"""
STEP2FFA - Streamlit UI Application

Single-window interface for assembly workflow orchestration.

Key Features:
  - Fixed layout (no vertical scrolling of components)
  - Threaded workflow execution (non-blocking UI)
  - Real-time chat, image, and status updates
  - Upload STEP files to start workflow

Run:
    streamlit run ui/app.py
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import re
import base64

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from ui.components.chat import render_chat_window
from ui.components.image_box import render_image_box
from ui.components.progress_bar import render_progress_bar
from ui.components.progress_bar import PROGRESS_STEPS
from ui.state import init_session_state, process_event_queue
from ui.workflow_runner import run_workflow_threaded


# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="STEP2FfA - Fitness for Automation Assessment",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Quiet technical styling. Keep this local so the app does not depend on
# external font/CDN loading.
st.markdown("""
    <style>
    * {
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 1rem;
    }

    :root {
        --apa-bg: #F7F9FA;
        --apa-card: #FFFFFF;
        --apa-green: #179C7D;
        --apa-orange: #F58220;
        --apa-ink: #111827;
        --apa-ink-2: #1F2933;
        --apa-muted: #6B7280;
        --apa-line: #D9E2E7;
        --apa-shadow: 0 10px 28px rgba(17, 24, 39, 0.06);
    }

    .stApp {
        background: var(--apa-bg);
        color: var(--apa-ink);
        overflow-x: hidden;
    }

    [data-testid="column"] {
        min-width: 0 !important;
    }
    
    h1, h2, h3 {
        font-family: 'Segoe UI', Arial, sans-serif;
        color: var(--apa-ink);
    }

    h1 {
        font-size: 1.9rem !important;
        margin-bottom: 0 !important;
    }

    h2, h3 {
        font-size: 1.05rem !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-top: 0.35rem !important;
    }

    .stCaption, [data-testid="stCaptionContainer"] {
        font-size: 0.98rem !important;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stFileUploader"] {
        font-size: 1rem !important;
    }

    div[data-testid="stFileUploader"] section {
        border-color: rgba(23, 156, 125, 0.45) !important;
        background: linear-gradient(180deg, rgba(23, 156, 125, 0.08), rgba(23, 156, 125, 0.03)) !important;
    }

    div[data-testid="stFileUploader"] button {
        background: var(--apa-green) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--apa-green) !important;
        border-radius: 8px !important;
        font-weight: 760 !important;
    }

    div[data-testid="stFileUploader"] button:hover {
        background: #12866C !important;
        border-color: #12866C !important;
        color: #FFFFFF !important;
    }

    div[data-testid="stButton"] button[kind="primary"] {
        background: var(--apa-action-color, #39C1CD) !important;
        border-color: var(--apa-action-color, #39C1CD) !important;
        color: #FFFFFF !important;
        font-weight: 760 !important;
        border-radius: 8px !important;
    }

    div[data-testid="stButton"] button[kind="primary"]:hover {
        background: var(--apa-action-hover, #2EAEB9) !important;
        border-color: var(--apa-action-hover, #2EAEB9) !important;
        color: #FFFFFF !important;
    }

    div[data-testid="stButton"] button[kind="primary"]:disabled,
    div[data-testid="stButton"] button[kind="primary"]:disabled:hover {
        background: var(--apa-action-color, #39C1CD) !important;
        border-color: var(--apa-action-color, #39C1CD) !important;
        color: #FFFFFF !important;
        opacity: 0.82 !important;
    }

    div[data-testid="stAlert"] {
        font-size: 1rem !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--apa-line) !important;
        border-radius: 12px !important;
        box-shadow: var(--apa-shadow);
        background: var(--apa-card);
    }

    div[role="radiogroup"] label {
        border-radius: 8px;
        padding: 0.18rem 0.35rem;
    }

    div[role="radiogroup"] label:has(input:checked) {
        color: var(--apa-green) !important;
        font-weight: 760;
    }
    
    [data-testid="stHeader"] {
        height: 3.25rem;
    }

    [data-testid="stMainBlockContainer"] {
        padding-top: 3.6rem;
        padding-bottom: 1rem;
    }
    
    button {
        font-family: 'Segoe UI', Arial, sans-serif;
    }

    .apa-shell {
        border-top: 1px solid var(--apa-line);
        padding-top: 0.85rem;
        margin-top: 0.35rem;
    }

    .apa-pane-title {
        color: var(--apa-muted);
        font-size: 0.9rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0 0 0.4rem 0;
    }

    .apa-card {
        background: var(--apa-card);
        border: 1px solid var(--apa-line);
        border-radius: 12px;
        box-shadow: var(--apa-shadow);
        padding: 0.9rem 1rem;
    }

    .apa-header {
        position: sticky;
        top: 3.25rem;
        z-index: 50;
        background: rgba(247, 249, 250, 0.94);
        backdrop-filter: blur(8px);
        border-bottom: 1px solid var(--apa-line);
        padding: 0.75rem 0 0.65rem 0;
        margin-bottom: 0.75rem;
    }

    .apa-brand {
        display: flex;
        align-items: center;
        gap: 1.4rem;
        min-height: 2.6rem;
    }

    .apa-header-logo {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        min-height: 2.6rem;
    }

    .apa-brand-logo {
        display: block;
        max-height: 54px;
        max-width: 260px;
        object-fit: contain;
    }

    .apa-brand-main {
        font-size: 1.48rem;
        font-weight: 760;
        color: var(--apa-ink);
        line-height: 1.05;
    }

    .apa-brand-sub {
        font-size: 0.9rem;
        color: var(--apa-muted);
        font-weight: 650;
        letter-spacing: 0;
        text-transform: none;
        line-height: 1.25;
        margin-top: 0.22rem;
    }

    .apa-status-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.42rem 0.65rem;
        border-radius: 999px;
        border: 1px solid var(--apa-line);
        background: #fff;
        color: var(--apa-muted);
        font-weight: 750;
        text-transform: uppercase;
        font-size: 0.9rem;
    }

    .apa-status-chip.ready { color: var(--apa-muted); }
    .apa-status-chip.running { color: var(--apa-green); border-color: rgba(23, 156, 125, 0.28); background: rgba(23, 156, 125, 0.08); }
    .apa-status-chip.feedback { color: var(--apa-orange); border-color: rgba(245, 130, 32, 0.35); background: rgba(245, 130, 32, 0.08); }
    .apa-status-chip.complete { color: var(--apa-green); border-color: rgba(23, 156, 125, 0.35); background: rgba(23, 156, 125, 0.09); }
    .apa-status-chip.error { color: #B42318; border-color: rgba(180, 35, 24, 0.35); background: rgba(180, 35, 24, 0.08); }

    .apa-progress-meter {
        height: 7px;
        border-radius: 999px;
        background: #DDE5EA;
        overflow: hidden;
        margin-top: 0.45rem;
    }

    .apa-progress-meter > div {
        height: 100%;
        background: var(--apa-green);
        border-radius: 999px;
    }

    .apa-small-label {
        color: var(--apa-muted);
        font-size: 0.82rem;
        font-weight: 650;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .apa-metric-value {
        color: var(--apa-ink);
        font-weight: 760;
        font-size: 1.12rem;
        line-height: 1.2;
    }
    </style>
""", unsafe_allow_html=True)


# ============================================================================
# MAIN APP
# ============================================================================

def render_report_download_action():
    """Render a compact report action for the header."""
    pdf_path = st.session_state.get("ffa_pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return

    pdf_file = Path(pdf_path)
    with pdf_file.open("rb") as handle:
        pdf_bytes = handle.read()
    st.download_button(
        "Download Report",
        data=pdf_bytes,
        file_name=pdf_file.name,
        mime="application/pdf",
        width="stretch",
    )


def workflow_status() -> tuple[str, str]:
    """Return status key and label for the header chip."""
    if st.session_state.get("workflow_error"):
        return "error", "Error"
    if st.session_state.get("workflow_complete"):
        return "complete", "Complete"
    if st.session_state.get("awaiting_user_input"):
        return "feedback", "Feedback required"
    if st.session_state.get("workflow_started"):
        return "running", "Running"
    return "ready", "Ready"


def progress_percent() -> int:
    step = st.session_state.get("progress_step", 0)
    if st.session_state.get("workflow_complete"):
        return 100
    return max(0, min(100, round((step / (len(PROGRESS_STEPS) - 1)) * 100)))


def runtime_metrics() -> tuple[str, str, str]:
    """Return start, elapsed, and rough remaining time strings."""
    start_raw = st.session_state.get("ui_start_time")
    if not start_raw:
        return "--:--:--", "00:00:00", "--:--:--"

    try:
        started = datetime.fromisoformat(start_raw)
    except ValueError:
        return "--:--:--", "00:00:00", "--:--:--"

    elapsed_seconds = max(0, int((datetime.now() - started).total_seconds()))
    percent = progress_percent()
    if percent > 4 and not st.session_state.get("workflow_complete"):
        total_estimate = int(elapsed_seconds / (percent / 100))
        remaining_seconds = max(0, total_estimate - elapsed_seconds)
    elif st.session_state.get("workflow_complete"):
        remaining_seconds = 0
    else:
        remaining_seconds = None

    return (
        started.strftime("%H:%M:%S"),
        _format_duration(elapsed_seconds),
        _format_duration(remaining_seconds) if remaining_seconds is not None else "--:--:--",
    )


def _format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def assembly_name_from_upload(uploaded_file) -> str:
    """Create a backend-safe assembly name from the uploaded STEP filename."""
    if not uploaded_file:
        return ""
    stem = Path(uploaded_file.name).stem
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_")
    return clean or "assembly"


def image_data_uri(path: Path) -> str:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""

    suffix = path.suffix.lower()
    mime = "image/svg+xml" if suffix == ".svg" else "image/png"
    return f"data:{mime};base64,{encoded}"


def reconcile_progress_from_artifacts() -> bool:
    """Promote visible progress when generated files prove the workflow moved on."""
    session_root = st.session_state.get("session_root")
    if not session_root or not st.session_state.get("workflow_started"):
        return False

    root = Path(session_root)
    current = st.session_state.get("progress_step", 0)
    phase = st.session_state.get("workflow_phase")

    if current < 7 and phase in {"PHASE_4", "PHASE_4_RENDERING"}:
        st.session_state.progress_step = 7
        if phase == "PHASE_4":
            st.session_state.workflow_phase = "PHASE_4_RENDERING"
        return True

    if current < 7 and any(root.rglob("assembly_sequence_run*/sequence_renderings/step_*.png")):
        st.session_state.progress_step = 7
        st.session_state.workflow_phase = "PHASE_4_RENDERING"
        return True

    if current < 8 and any(root.rglob("assembly_sequence_run*/interaction_analysis.json")):
        st.session_state.progress_step = 8
        st.session_state.workflow_phase = "PHASE_4_INTERACTIONS"
        return True

    return False


def main():
    """Main Streamlit application."""
    
    # Initialize session state
    init_session_state()
    
    # Process any pending events from worker thread
    process_event_queue()
    reconcile_progress_from_artifacts()
    
    # ========================================================================
    # HEADER + UPLOAD SECTION (Fixed at top)
    # ========================================================================
    
    joint_logo = image_data_uri(WORKSPACE_ROOT / "ui" / "assets" / "logos" / "JointLogo.png")

    header_brand, header_logo, header_report = st.columns([2.6, 1.15, 0.75], gap="medium")
    with header_brand:
        st.markdown(
            """
            <div class="apa-brand">
              <div>
                <div class="apa-brand-main">STEP2FfA</div>
                <div class="apa-brand-sub">Fitness for Automation Assessment for Assemblies based on STEP-Data</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_logo:
        st.markdown(
            f"""
            <div class="apa-header-logo">
              {'<img class="apa-brand-logo" src="' + joint_logo + '" alt="Fraunhofer IPA and University of Stuttgart" />' if joint_logo else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_report:
        render_report_download_action()

    render_progress_bar()

    workflow_started = st.session_state.get("workflow_started")
    workflow_complete = st.session_state.get("workflow_complete")
    if workflow_complete:
        action_label = "Assessment finished"
        action_color = "#F58220"
        action_hover = "#D96F12"
    elif workflow_started:
        action_label = "Processing"
        action_color = "#179C7D"
        action_hover = "#12866C"
    else:
        action_label = "Start Analysis"
        action_color = "#39C1CD"
        action_hover = "#2EAEB9"

    st.markdown(
        f"""
        <style>
        :root {{
            --apa-action-color: {action_color};
            --apa-action-hover: {action_hover};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        control_col, action_col = st.columns(
            [3.0, 1.05],
            gap="medium",
        )
        with control_col:
            uploaded_file = st.file_uploader(
                "Upload your STEP-File here",
                type=["STEP", "step"],
                key="file_uploader",
                disabled=st.session_state.get("workflow_started") and not st.session_state.get("workflow_complete"),
            )

        assembly_name = assembly_name_from_upload(uploaded_file)
        if uploaded_file and not st.session_state.get("workflow_started"):
            st.caption(f"Assembly name: {assembly_name}")

        with action_col:
            st.write("")
            st.write("")
            start_clicked = st.button(
                action_label,
                width="stretch",
                type="primary",
                disabled=not uploaded_file or workflow_started,
            )

        if start_clicked and uploaded_file:
            st.session_state.ui_start_time = datetime.now().isoformat()
            run_workflow_threaded(
                uploaded_file=uploaded_file,
                assembly_name=assembly_name,
                workspace_root=WORKSPACE_ROOT
            )
            st.session_state.workflow_started = True
            st.session_state.workflow_complete = False
            st.session_state.workflow_error = None
            st.rerun()

    st.markdown('<div class="apa-shell"></div>', unsafe_allow_html=True)
    
    # ========================================================================
    # MAIN LAYOUT: Chat (left) | Visualization (right)
    # ========================================================================
    
    col_chat, col_right = st.columns([0.85, 1.9], gap="medium")
    
    # ---- LEFT COLUMN: Chat Window ----
    with col_chat:
        st.markdown('<div class="apa-pane-title">Conversation</div>', unsafe_allow_html=True)
        render_chat_window()
    
    # ---- RIGHT COLUMN: Image ----
    with col_right:
        st.markdown('<div class="apa-pane-title">Visualization</div>', unsafe_allow_html=True)
        current_phase = st.session_state.get("workflow_phase", "IDLE")
        render_image_box(st.session_state.get("session_root"), workflow_phase=current_phase)


if __name__ == "__main__":
    main()
