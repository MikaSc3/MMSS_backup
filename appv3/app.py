"""STEP2FfA Streamlit App V3."""

from __future__ import annotations

import base64
import io
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from appv3.runner import safe_assembly_name, start_initial_agent, start_workflow
from appv3.state import add_user_message, init_state, process_events
from appv3.visualization import VisualizationSnapshot, build_snapshot


PROGRESS_STEPS = [
    "Upload data",
    "Preprocess STEP",
    "Read documents",
    "Analyse assembly",
    "Confirm assembly",
    "Analyse monoparts",
    "Generate sequence",
    "Confirm sequence",
    "Render sequence",
    "Assess FfA",
    "Generate report",
    "Discuss report",
]

st.set_page_config(
    page_title="STEP2FfA App V3",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_state()
if not st.session_state.v3_intro_started:
    st.session_state.v3_intro_started = True
    start_initial_agent(
        workspace_root=WORKSPACE_ROOT,
        event_queue=st.session_state.v3_event_queue,
    )


def _css() -> None:
    st.markdown(
        """
        <style>
        * { font-family: "Segoe UI", Arial, sans-serif; letter-spacing: 0; }
        :root {
            --bg:#F7F9FA; --card:#FFFFFF; --green:#179C7D; --orange:#F58220;
            --cyan:#39C1CD; --ink:#111827; --muted:#6B7280; --line:#D9E2E7;
        }
        .stApp { background:var(--bg); color:var(--ink); }
        [data-testid="stHeader"] {
            background:transparent !important; border-bottom:none !important;
            box-shadow:none !important;
        }
        [data-testid="stMainBlockContainer"] { padding-top:4.2rem; padding-bottom:1rem; }
        [data-testid="column"] { min-width:0 !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background:var(--card); border-color:var(--line) !important;
            border-radius:8px !important; box-shadow:0 8px 24px rgba(17,24,39,.05);
        }
        div[data-testid="stFileUploader"] section {
            border-color:rgba(23,156,125,.45) !important;
            background:rgba(23,156,125,.05) !important;
            min-height:72px !important; padding:.55rem .75rem !important;
            align-items:center !important;
        }
        div[data-testid="stFileUploader"] section button,
        .st-key-v3_start_analysis button {
            min-height:42px !important;
        }
        .st-key-v3_start_analysis button {
            height:72px !important; margin-top:.1rem !important;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background:var(--cyan); border-color:var(--cyan); color:white;
            border-radius:8px; font-weight:700;
        }
        .st-key-v3_user_input input {
            border-color:#F58220 !important;
            background:#FFF9F3 !important;
        }
        .st-key-v3_user_input input:disabled {
            border-color:rgba(245,130,32,.65) !important;
            background:#FFF9F3 !important;
            opacity:.78 !important;
        }
        .st-key-v3_user_input input:not(:disabled) {
            box-shadow:0 0 0 3px rgba(245,130,32,.14) !important;
        }
        .st-key-v3_user_input input:not(:disabled):focus {
            border-color:#F58220 !important;
            box-shadow:0 0 0 4px rgba(245,130,32,.2) !important;
        }
        .st-key-v3_send_button button:not(:disabled) {
            background:#F58220 !important; border-color:#F58220 !important;
            color:#FFFFFF !important; font-weight:760 !important;
        }
        .st-key-v3_send_button button:not(:disabled):hover {
            background:#D96F12 !important; border-color:#D96F12 !important;
        }
        .st-key-v3_message_form button:not(:disabled) {
            background:#F58220 !important; border-color:#F58220 !important;
            color:#FFFFFF !important; font-weight:760 !important;
        }
        .st-key-v3_message_form button:not(:disabled):hover {
            background:#D96F12 !important; border-color:#D96F12 !important;
        }
        .st-key-v3_workflow_output_report_download button,
        div[data-testid="stDownloadButton"]:has(button[aria-label="Download FfA Reports"]) button {
            background:#179C7D !important; border-color:#179C7D !important;
            color:#FFFFFF !important; border-radius:8px !important; font-weight:760 !important;
        }
        .st-key-v3_workflow_output_report_download button:hover,
        div[data-testid="stDownloadButton"]:has(button[aria-label="Download FfA Reports"]) button:hover {
            background:#12866C !important; border-color:#12866C !important;
            color:#FFFFFF !important;
        }
        .brand { display:flex; align-items:center; min-height:48px; }
        .brand-main { font-size:1.65rem; line-height:1.2; font-weight:800; color:#111827; }
        .brand-logo { width:100%; max-width:350px; height:48px; object-fit:contain; }
        .pane-title { margin:.15rem 0 .45rem; color:#6B7280; font-size:.82rem;
            font-weight:750; text-transform:uppercase; letter-spacing:.08em; }
        .status-row { display:flex; gap:.7rem; align-items:flex-start; padding:.66rem .75rem;
            border-bottom:1px solid #E8EEF1; }
        .status-dot { width:10px; height:10px; margin-top:.32rem; border-radius:50%; flex:0 0 auto; }
        .queued { background:#B8C4CC; } .running { background:#F58220; box-shadow:0 0 0 4px rgba(245,130,32,.13); }
        .complete { background:#179C7D; } .failed { background:#C93C3C; }
        .status-name { color:#1F2933; font-weight:700; font-size:.94rem; }
        .status-meta { color:#6B7280; font-size:.82rem; margin-top:.12rem; }
        .chat-avatar { width:38px; height:38px; border-radius:50%; color:white;
            display:flex; align-items:center; justify-content:center; font-weight:800;
            font-size:.85rem; margin-top:.1rem; }
        .chat-avatar.agent { background:#179C7D; }
        .chat-avatar.user { background:#1F2933; }
        .chat-name { color:#111827; font-size:1rem; font-weight:760; }
        .chat-time { color:#6B7280; font-size:.78rem; text-align:right; padding-top:.15rem; }
        .chat-status-slot { box-sizing:border-box; min-height:52px; display:flex;
            align-items:center; color:#66737C; font-size:.9rem; line-height:1.3;
            padding:.35rem .15rem; }
        .chat-status-slot.waiting { color:#8A470D; font-weight:650; }
        .chat-status-slot.complete { color:#08745D; font-weight:650; }
        .st-key-v3_conversation_frame { border:2px solid #F58220 !important;
            border-radius:12px !important; box-shadow:0 10px 28px rgba(245,130,32,.08) !important;
            min-height:600px !important; overflow:visible !important; }
        .st-key-v3_conversation_frame div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color:#F58220 !important;
        }
        .visual-stage { position:relative; box-sizing:border-box; width:100%; height:600px;
            max-height:calc(100vh - 20rem); min-height:320px; border:1px solid #D9E2E7;
            border-radius:12px; background:#F8FAFC; display:flex; align-items:center;
            justify-content:center; overflow:hidden; box-shadow:0 10px 28px rgba(17,24,39,.06);
            padding:14px; }
        .visual-stage img { display:block; width:100%; height:100%; max-width:100%;
            max-height:100%; object-fit:contain; }
        .visual-step-badge { position:absolute; top:26px; left:26px; z-index:2;
            padding:.42rem .7rem; border-radius:999px; color:#FFFFFF;
            background:rgba(17,24,39,.84); font-size:.92rem; font-weight:760;
            box-shadow:0 4px 14px rgba(17,24,39,.18); }
        .visual-stage.empty:after { content:""; position:absolute; inset:14px;
            border:1px dashed #B8C4CC; border-radius:8px; }
        .empty-stage { color:#6B7280; font-weight:700; text-transform:uppercase; font-size:.9rem; }
        .visual-info { box-sizing:border-box; width:100%; min-height:320px;
            background:#FFFFFF; padding:.9rem 1rem; }
        .workspace-frame { box-sizing:border-box; width:100%; height:548px;
            max-height:calc(100vh - 20rem); min-height:320px; overflow:auto;
            background:#FFFFFF; border:1px solid #D9E2E7; border-radius:12px;
            box-shadow:0 10px 28px rgba(17,24,39,.06); padding:14px; }
        .visual-title { color:#111827; font-size:1.18rem; font-weight:760; }
        .visual-detail { color:#66737C; font-size:1rem; line-height:1.4; margin-top:.2rem; }
        .visual-facts { display:grid; gap:.18rem; margin-top:.45rem; }
        .visual-fact { color:#33404A; font-size:1rem; line-height:1.4; }
        .visual-fact:before { content:""; display:inline-block; width:5px; height:5px;
            border-radius:50%; background:#179C7D; margin:0 .45rem .1rem 0; }
        .visual-progress { height:4px; background:#E4EAED; border-radius:2px;
            overflow:hidden; margin-top:.55rem; }
        .visual-progress-fill { height:100%; background:#179C7D; border-radius:2px; }
        .progress-wrap { display:flex; align-items:flex-start; overflow-x:auto;
            padding:.8rem .2rem 1.55rem; margin-bottom:1rem; }
        .progress-item { min-width:82px; flex:1; text-align:center; position:relative; }
        .progress-item:after { content:""; position:absolute; height:2px; background:#D9E2E7;
            top:13px; left:50%; width:100%; z-index:0; }
        .progress-item:last-child:after { display:none; }
        .progress-item.done:after { background:#179C7D; }
        .progress-node { position:relative; z-index:1; margin:auto; width:26px; height:26px;
            border-radius:50%; border:1px solid #B8C4CC; background:white; display:flex;
            align-items:center; justify-content:center; font-size:.75rem; font-weight:700; }
        .progress-item.done .progress-node { border-color:#179C7D; color:#179C7D; }
        .progress-item.active .progress-node { background:#F58220; border-color:#F58220; color:white; }
        .progress-label { margin-top:.48rem; font-size:.88rem; line-height:1.25;
            font-weight:620; color:#4B5861; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logo_uri() -> str:
    path = WORKSPACE_ROOT / "ui" / "assets" / "logos" / "JointLogo.png"
    if not path.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _render_header() -> None:
    brand, _, logo = st.columns([2.6, .75, 1.15], gap="medium")
    with brand:
        st.markdown(
            '<div class="brand"><div class="brand-main">'
            'STEP2FfA - LLM based Fitness for Automation Assessment'
            '</div></div>',
            unsafe_allow_html=True,
        )
    with logo:
        uri = _logo_uri()
        if uri:
            st.markdown(f'<img class="brand-logo" src="{uri}" />', unsafe_allow_html=True)


def _render_uploads() -> None:
    if st.session_state.v3_started:
        return

    with st.container(border=True):
        step_col, docs_col, action_col = st.columns([1.45, 1.8, .75], gap="medium")
        initial_agent_message = next(
            (
                message.get("content", "")
                for message in st.session_state.v3_messages
                if message.get("role") == "agent" and message.get("content")
            ),
            "",
        )
        with step_col:
            step_file = st.file_uploader(
                "STEP File",
                type=["step", "stp"],
                key="v3_step_upload",
            )
        with docs_col:
            documents = st.file_uploader(
                "Supporting documents",
                type=["pdf", "docx", "csv", "xlsx", "txt", "md", "json"],
                accept_multiple_files=True,
                key="v3_document_upload",
            )
        with action_col:
            st.write("")
            st.write("")
            start = st.button(
                "Start Analysis",
                type="primary",
                width="stretch",
                disabled=step_file is None or not initial_agent_message,
                key="v3_start_analysis",
            )
        if step_file:
            label = safe_assembly_name(step_file.name)
            st.caption(f"Assembly: {label} | Supporting files: {len(documents or [])}")
        if start and step_file:
            st.session_state.v3_started = True
            st.session_state.v3_started_at = datetime.now().isoformat()
            st.session_state.v3_error = None
            start_workflow(
                step_name=step_file.name,
                step_bytes=step_file.getvalue(),
                additional_files=[(item.name, item.getvalue()) for item in documents or []],
                workspace_root=WORKSPACE_ROOT,
                event_queue=st.session_state.v3_event_queue,
                input_queue=st.session_state.v3_input_queue,
                initial_agent_message=initial_agent_message,
            )
            st.rerun()


def _render_progress() -> None:
    current = st.session_state.v3_progress_step
    html = '<div class="progress-wrap">'
    for index, label in enumerate(PROGRESS_STEPS):
        state = "done" if index < current else "active" if index == current else ""
        html += (
            f'<div class="progress-item {state}"><div class="progress-node">{index + 1}</div>'
            f'<div class="progress-label">{label}</div></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


@st.fragment(run_every=1.0)
def _live_workspace() -> None:
    process_events()
    _render_progress()
    left, right = st.columns([1.05, 1.7], gap="medium")
    with left:
        st.markdown('<div class="pane-title">Conversation</div>', unsafe_allow_html=True)
        _render_chat()
    with right:
        snapshot = build_snapshot(
            _session_root(),
            phase=st.session_state.v3_phase,
            tools=st.session_state.v3_tools,
            awaiting_input=st.session_state.v3_awaiting_input,
            workflow_complete=st.session_state.v3_complete,
            workflow_error=st.session_state.v3_error,
            sequence_display_step=st.session_state.v3_sequence_display_step,
            phase_started_at=(
                st.session_state.v3_phase_started_at
                or (
                    datetime.fromisoformat(st.session_state.v3_started_at).timestamp()
                    if st.session_state.v3_started_at
                    else None
                )
            ),
        )
        if snapshot.title == "Rendering assembly sequence" and snapshot.image_step:
            now = time.time()
            current_step = st.session_state.v3_sequence_display_step
            changed_at = st.session_state.v3_sequence_display_changed_at
            if current_step == 0:
                st.session_state.v3_sequence_display_step = snapshot.image_step
                st.session_state.v3_sequence_display_changed_at = now
            elif (
                snapshot.completed
                and current_step < snapshot.completed
                and (changed_at is None or now - changed_at >= 2)
            ):
                st.session_state.v3_sequence_display_step = current_step + 1
                st.session_state.v3_sequence_display_changed_at = now
        if snapshot.progress_step is not None:
            st.session_state.v3_progress_step = max(
                st.session_state.v3_progress_step,
                snapshot.progress_step,
            )
        _render_visualization(snapshot)


def _render_chat() -> None:
    waiting = st.session_state.v3_awaiting_input
    with st.container(border=True, key="v3_conversation_frame"):
        with st.container(height=430):
            if not st.session_state.v3_messages:
                st.caption("Starting the content agent...")
            for index, message in enumerate(st.session_state.v3_messages):
                role = message.get("role", "agent")
                label = "You" if role == "user" else "Content Agent"
                timestamp = _time_label(message.get("timestamp"))
                icon = "IN" if role == "user" else "AI"
                with st.container(border=True, key=f"v3_message_{index}_{role}"):
                    avatar_col, body_col = st.columns([0.14, 0.86], gap="small")
                    with avatar_col:
                        st.markdown(
                            f'<div class="chat-avatar {role}">{icon}</div>',
                            unsafe_allow_html=True,
                        )
                    with body_col:
                        name_col, time_col = st.columns([0.72, 0.28], gap="small")
                        with name_col:
                            st.markdown(f'<div class="chat-name">{label}</div>', unsafe_allow_html=True)
                        with time_col:
                            st.markdown(f'<div class="chat-time">{timestamp}</div>', unsafe_allow_html=True)
                        st.markdown(message.get("content", ""))
            st.markdown('<div id="v3-chat-bottom"></div>', unsafe_allow_html=True)
            message_count = len(st.session_state.v3_messages)
            if st.session_state.v3_last_autoscroll_message_count != message_count:
                st.session_state.v3_last_autoscroll_message_count = message_count
                _scroll_conversation_to_bottom()

        if st.session_state.v3_intro_error:
            st.warning(st.session_state.v3_intro_error)
        if st.session_state.v3_error:
            st.error(st.session_state.v3_error)
            return

        if not st.session_state.v3_started:
            status = "Upload an assembly to begin."
            status_class = ""
        elif waiting:
            status = st.session_state.v3_input_prompt or "The content agent is waiting for your reply."
            status_class = "waiting"
        elif st.session_state.v3_complete:
            status = "Dialogue finished."
            status_class = "complete"
        else:
            status = "The agent is working. Input unlocks when a response is needed."
            status_class = ""

        st.markdown(
            f'<div class="chat-status-slot {status_class}">{_escape_html(status)}</div>',
            unsafe_allow_html=True,
        )

        with st.form("v3_message_form", clear_on_submit=True, border=False):
            input_col, send_col = st.columns([5, 1])
            with input_col:
                value = st.text_input(
                    "Message",
                    key="v3_user_input",
                    label_visibility="collapsed",
                    placeholder="Reply to the content agent...",
                    disabled=not waiting,
                )
            with send_col:
                submitted = st.form_submit_button(
                    "Send",
                    width="stretch",
                    disabled=not waiting,
                )

        if submitted:
            request_id = st.session_state.v3_input_request_id
            already_submitted = (
                st.session_state.v3_submitted_input_request_id == request_id
            )
            value = value.strip()
            if value and waiting and not already_submitted:
                st.session_state.v3_submitted_input_request_id = request_id
                add_user_message(value)
                st.session_state.v3_input_queue.put(value)
                st.session_state.v3_awaiting_input = False
                st.session_state.v3_input_prompt = None
                st.rerun()


def _session_root() -> Path | None:
    value = st.session_state.v3_session_root
    return Path(value) if value else None


def _scroll_conversation_to_bottom() -> None:
    components.html(
        """
        <script>
        function scrollConversation() {
            const marker = window.parent.document.getElementById("v3-chat-bottom");
            if (!marker) return;
            let node = marker.parentElement;
            while (node) {
                const style = window.parent.getComputedStyle(node);
                const scrollable = node.scrollHeight > node.clientHeight + 4;
                if (scrollable && ["auto", "scroll"].includes(style.overflowY)) {
                    node.scrollTop = node.scrollHeight;
                    return;
                }
                node = node.parentElement;
            }
        }
        window.setTimeout(scrollConversation, 80);
        window.setTimeout(scrollConversation, 250);
        </script>
        """,
        height=0,
        width=0,
    )


def _render_visualization(snapshot: VisualizationSnapshot) -> None:
    progress_html = ""
    if snapshot.ratio is not None:
        progress_html = (
            '<div class="visual-progress">'
            f'<div class="visual-progress-fill" style="width:{snapshot.ratio * 100:.1f}%"></div>'
            "</div>"
        )
    facts_html = ""
    if snapshot.facts:
        facts_html = '<div class="visual-facts">' + "".join(
            f'<div class="visual-fact">{_escape_html(fact)}</div>'
            for fact in snapshot.facts
        ) + "</div>"
    info_html = (
        '<div class="visual-info">'
        f'<div class="visual-title">{_escape_html(snapshot.title)}</div>'
        f'<div class="visual-detail">{_escape_html(snapshot.detail)}</div>'
        f"{facts_html}"
        f"{progress_html}</div>"
    )
    info_col, image_col = st.columns([0.9, 1.3], gap="medium")
    with info_col:
        st.markdown('<div class="pane-title">Workflow detailed info</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="workspace-frame">{info_html}</div>', unsafe_allow_html=True)
        pdf_paths = _pdf_paths()
        if pdf_paths:
            report_package = io.BytesIO()
            with zipfile.ZipFile(report_package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for pdf_path in pdf_paths:
                    archive.write(pdf_path, arcname=pdf_path.name)
            st.download_button(
                "Download FfA Reports",
                data=report_package.getvalue(),
                file_name=f"{st.session_state.v3_assembly_name or 'ffa'}_reports.zip",
                mime="application/zip",
                width="stretch",
                key="v3_workflow_output_report_download",
            )
    with image_col:
        st.markdown('<div class="pane-title">Visualization</div>', unsafe_allow_html=True)
        if not snapshot.image_path or not snapshot.image_path.exists():
            st.markdown(
                '<div class="visual-stage empty"></div>',
                unsafe_allow_html=True,
            )
            return

        path = snapshot.image_path
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        step_badge = ""
        if snapshot.image_badge:
            step_badge = (
                f'<div class="visual-step-badge">'
                f'{_escape_html(snapshot.image_badge)}</div>'
            )
        elif snapshot.image_step:
            total = f" / {snapshot.image_step_total}" if snapshot.image_step_total else ""
            step_badge = (
                f'<div class="visual-step-badge">Assembly step '
                f'{snapshot.image_step}{total}</div>'
            )
        st.markdown(
            '<div class="visual-stage">'
            f"{step_badge}"
            f'<img src="data:{mime};base64,{encoded}" alt="{_escape_html(path.name)}" />'
            "</div>",
            unsafe_allow_html=True,
        )


def _pdf_paths() -> list[Path]:
    artifacts = st.session_state.v3_artifacts
    post = artifacts.get("ffa_post_processing_result") or {}
    paths = []
    for key in ("pdf_report", "pdf_report_v2"):
        value = post.get(key)
        if value and Path(value).exists():
            paths.append(Path(value))
    if paths:
        return paths
    root = _session_root()
    if root:
        return sorted(root.rglob("*_ffa_report*.pdf"))
    return []


def _time_label(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%H:%M:%S")
    except ValueError:
        return ""


def _escape_html(value: str) -> str:
    import html

    return html.escape(str(value))


_css()
_render_header()
_render_uploads()
_live_workspace()
