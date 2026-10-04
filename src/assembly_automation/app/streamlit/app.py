"""Three-pane product UI for the durable assembly assessment workflow."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import queue
import sys
import time
import zipfile

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = WORKSPACE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import streamlit as st

from assembly_automation.app.streamlit.components.chat import render_chat
from assembly_automation.app.streamlit.components.structured_results import (
    render_output_navigation, render_structured_results)
from assembly_automation.app.streamlit.components.topbar import render_topbar
from assembly_automation.app.streamlit.components.visuals import images_for_selection, render_visuals
from assembly_automation.app.streamlit.controller import SessionController
from assembly_automation.app.streamlit.activity_console import render_activity_console
from assembly_automation.app.streamlit.image_catalog import build_image_catalog
from assembly_automation.app.streamlit.progress import render_progress
from assembly_automation.app.streamlit.selection import SelectionContext, available_output_scopes
from assembly_automation.app.streamlit.session_view import load_session_snapshot
from assembly_automation.app.streamlit.styles import CSS


st.set_page_config(page_title="FfA · Assembly Intelligence", page_icon="⚙", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)


def _state() -> None:
    if "product_events" not in st.session_state:
        st.session_state.product_events = []
    if "controller" not in st.session_state:
        st.session_state.controller = SessionController(workspace_root=WORKSPACE_ROOT)
    if "session_root" not in st.session_state:
        st.session_state.session_root = str(st.session_state.controller.draft_root)
    if "busy" not in st.session_state:
        st.session_state.busy = False
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "active_selection" not in st.session_state:
        st.session_state.active_selection = None
    if "structured_drafts" not in st.session_state:
        st.session_state.structured_drafts = {}
    if "structured_editor_generation" not in st.session_state:
        st.session_state.structured_editor_generation = 0
    if "pending_user_message" not in st.session_state:
        st.session_state.pending_user_message = None
    if "active_command_id" not in st.session_state:
        st.session_state.active_command_id = None
    if "pre_session_messages" not in st.session_state:
        st.session_state.pre_session_messages = []
    if "intro_started" not in st.session_state:
        st.session_state.intro_started = False
    if "intro_error" not in st.session_state:
        st.session_state.intro_error = None
    if "upload_reveal_at" not in st.session_state:
        st.session_state.upload_reveal_at = None
    if "upload_revealed" not in st.session_state:
        st.session_state.upload_revealed = False
    if not st.session_state.intro_started:
        st.session_state.intro_started = True
        try:
            st.session_state.intro_command_id = st.session_state.controller.start_introduction()
        except Exception as exc:
            st.session_state.intro_error = f"{type(exc).__name__}: {exc}"


def _drain_events() -> int:
    controller: SessionController = st.session_state.controller
    count = 0
    while True:
        try:
            event = controller.events.get_nowait()
        except queue.Empty:
            break
        seen = {item.get("event_id") for item in st.session_state.product_events}
        if event.get("event_id") in seen:
            continue
        count += 1
        st.session_state.product_events.append(event)
        st.session_state.product_events = st.session_state.product_events[-120:]
        event_type = event.get("type", "")
        correlation_id = event.get("correlation_id")
        tool_result = event.get("result")
        edit_succeeded = (isinstance(tool_result, dict)
                          and tool_result.get("status") != "error")
        if (event_type == "tool.completed"
                and event.get("tool") in {
                    "change_artifact", "edit_artifact_fields", "edit_intermediate_artifact"}
                and edit_succeeded):
            _clear_structured_editor_state()
            # An explicit structured-editor save is complete as soon as its
            # tool event arrives. Do not keep the chat composer disabled while
            # the controller is only finishing bookkeeping for this command.
            if correlation_id == st.session_state.active_command_id:
                st.session_state.busy = False
                st.session_state.active_command_id = None
                st.session_state.pending_user_message = None
        if event_type == "tool.completed" and event.get("tool") in {"layout_planner", "revise_layout"}:
            st.session_state.active_selection = SelectionContext("layout", group="Automation planning")
        if event_type == "tool.completed" and event.get("tool") == "cost_planner":
            st.session_state.active_selection = SelectionContext("cost_estimate", group="Automation planning")
        if event_type in {"session.draft.created", "session.created", "session.resumed"} and event.get("session_root"):
            st.session_state.session_root = event["session_root"]
        if event_type == "agent.message.completed" and event.get("pre_session"):
            content = str(event.get("content") or "").strip()
            if content and not any(item.get("content") == content
                                   for item in st.session_state.pre_session_messages):
                st.session_state.pre_session_messages.append(
                    {"role": "assistant", "content": content})
                if st.session_state.upload_reveal_at is None:
                    st.session_state.upload_reveal_at = time.monotonic() + 1.0
        if (event_type == "agent.message.completed"
                and not event.get("intermediate")
                and st.session_state.active_command_id is not None
                and (correlation_id == st.session_state.active_command_id
                     or not event.get("pre_session"))):
            # A final assistant message is emitted after the agent has
            # finished all tool calls. Treat it as the turn boundary instead
            # of relying solely on the trailing controller event, which may
            # be observed by a different fragment rerun.
            st.session_state.busy = False
            st.session_state.active_command_id = None
            st.session_state.pending_user_message = None
        if event_type == "agent.turn.failed":
            if correlation_id == st.session_state.active_command_id:
                st.session_state.busy = False
                st.session_state.active_command_id = None
                st.session_state.pending_user_message = None
                st.session_state.last_error = event.get("error", "The operation failed")
                st.session_state.pop("save_draft_key", None)
                st.session_state.pop("navigation_after_save", None)
            elif event.get("command") == "introduce":
                st.session_state.intro_error = event.get("error", "Introduction failed")
        elif event_type == "agent.turn.completed":
            command_matches = correlation_id == st.session_state.active_command_id
            # Some normalized completion events from explicit UI tool actions
            # can arrive without the correlation id. There is only one active
            # command per browser session, so the command kind is a safe
            # fallback and prevents the composer remaining disabled forever.
            explicit_tool_completion = (
                event.get("command") == "tool_action"
                and st.session_state.active_command_id is not None)
            if command_matches or explicit_tool_completion:
                st.session_state.busy = False
                st.session_state.active_command_id = None
                st.session_state.pending_user_message = None
                saved = st.session_state.pop("save_draft_key", None)
                if saved:
                    draft = st.session_state.structured_drafts.get(saved)
                    st.session_state.structured_drafts.pop(saved, None)
                    if isinstance(draft, dict):
                        for field in draft.get("changes", {}):
                            st.session_state.pop(f"domain_field::{saved}::{field}", None)
                        st.session_state.pop(f"edit_reason::{saved}", None)
                after_save = st.session_state.pop("navigation_after_save", None)
                if after_save is not None:
                    st.session_state.active_selection = after_save
    return count


def _clear_structured_editor_state() -> None:
    """Drop widget drafts after an authoritative artifact update."""
    st.session_state.structured_drafts.clear()
    st.session_state.pending_selection = None
    st.session_state.pop("navigation_after_save", None)
    st.session_state.structured_editor_generation += 1


_state()
_drain_events()


@st.fragment(run_every=0.8)
def _activity_pulse() -> None:
    changed = _drain_events()
    reveal_at = st.session_state.upload_reveal_at
    if (reveal_at is not None and not st.session_state.upload_revealed
            and time.monotonic() >= reveal_at):
        st.session_state.upload_revealed = True
        changed = True
    if changed:
        # The chat transcript is rendered outside this polling fragment. A
        # fragment-only rerun refreshes progress but leaves completed agent
        # messages invisible until the user causes another page rerun.
        st.rerun(scope="app")
    with st.container(key="activity_strip"):
        progress_column, terminal_column = st.columns([2.1, 1.0], gap="small")
        with progress_column:
            render_progress(st, _snapshot(), st.session_state.product_events,
                            busy=st.session_state.busy)
        with terminal_column:
            with st.container(key="live_activity"):
                render_activity_console(st, st.session_state.product_events,
                                        busy=st.session_state.busy)


def _snapshot():
    root = st.session_state.session_root
    if not root:
        return None
    try:
        return load_session_snapshot(root)
    except (OSError, ValueError):
        return None


@st.fragment(run_every=2.0)
def _visual_pulse() -> None:
    """Discover renderings written by the background workflow as they appear."""
    current_snapshot = _snapshot()
    catalog = build_image_catalog(current_snapshot) if current_snapshot else []
    selection = st.session_state.active_selection
    selected = images_for_selection(catalog, selection)
    if st.session_state.busy:
        def modified(entry) -> int:
            try:
                return entry.path.stat().st_mtime_ns
            except OSError:
                return 0
        live_entries = sorted(catalog, key=modified, reverse=True)[:8]
    else:
        live_entries = []
    expanded = bool(selected or live_entries)
    with st.expander("Visual workspace", expanded=expanded):
        if live_entries:
            st.caption("Live rendering progress · updates every 2 seconds")
            render_visuals(st, live_entries, None, show_header=False,
                           use_all_entries=True)
        else:
            render_visuals(st, catalog, selection, show_header=False)


def _submit(method, *args, **kwargs) -> None:
    try:
        command_id = method(*args, **kwargs)
    except Exception as exc:
        st.session_state.last_error = f"{type(exc).__name__}: {exc}"
        st.session_state.pop("save_draft_key", None)
        st.session_state.pending_user_message = None
    else:
        st.session_state.active_command_id = command_id
        st.session_state.busy = True
        st.session_state.last_error = None
    st.rerun()


def _message(text: str) -> None:
    st.session_state.pending_user_message = text
    _submit(st.session_state.controller.submit_user_turn, text)


def _field_edits(artifact: str, entity_id: str, changes: dict[str, str],
                 expected_sha256: str, reason: str, raw: str,
                 draft_key: str) -> None:
    snapshot = _snapshot()
    st.session_state.save_draft_key = draft_key
    _submit(st.session_state.controller.submit_tool_action, "edit_artifact_fields",
            {"artifact": artifact, "entity_id": entity_id,
             "changes_json": json.dumps(changes, ensure_ascii=False),
             "expected_sha256": expected_sha256, "reason": reason,
             "raw_user_message": raw,
             "revision_id": snapshot.active_revision if snapshot and artifact == "sequence" else ""},
             user_message=raw, visible_in_chat=False)


@st.dialog("Unsaved changes", dismissible=False, icon=":material/edit_note:")
def _confirm_navigation() -> None:
    current: SelectionContext = st.session_state.active_selection
    requested: SelectionContext = st.session_state.pending_selection
    draft = st.session_state.structured_drafts.get(current.key)
    if not isinstance(draft, dict):
        # The background save completion can rerun the app between opening the
        # dialog and its button callback. In that case there is nothing left
        # to save, so navigation must not crash or present stale confirmation.
        st.session_state.active_selection = requested
        st.session_state.pending_selection = None
        st.rerun()
    requested_label = requested.scope.replace("_", " ").title()
    st.write(f"Your edits to **{draft['label']}** are not saved yet.")
    st.write(f"What should happen before opening **{requested_label}**?")
    save, discard, stay = st.columns(3)
    if save.button("Save changes and open", type="primary", width="stretch"):
        st.session_state.navigation_after_save = requested
        raw = f"Updated {draft['label']}: User-edited structured result"
        _field_edits(draft["artifact"], draft["entity_id"], draft["changes"],
                     draft["expected_sha256"], "User-edited structured result",
                     raw, current.key)
    if discard.button("Discard changes and open", width="stretch"):
        for field in draft.get("changes", {}):
            st.session_state.pop(f"domain_field::{current.key}::{field}", None)
        st.session_state.pop(f"edit_reason::{current.key}", None)
        st.session_state.structured_drafts.pop(current.key, None)
        st.session_state.active_selection = requested
        st.session_state.pending_selection = None
        st.rerun()
    if stay.button("Cancel and stay", width="stretch"):
        st.session_state.structured_selection_override = current
        st.session_state.pending_selection = None
        st.rerun()


def _session_archive(root: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root))
    return buffer.getvalue()


def _report_files(snapshot) -> list[Path]:
    artifact = snapshot.artifact("rendered_reports") if snapshot else None
    if artifact is None or not artifact.exists or not isinstance(artifact.data, dict):
        return []
    files = []
    for record in (artifact.data.get("artifacts") or {}).values():
        value = record.get("html") if isinstance(record, dict) else None
        if not isinstance(value, str):
            continue
        path = Path(value).resolve()
        try:
            path.relative_to(snapshot.root)
        except ValueError:
            continue
        if path.is_file() and path.suffix.lower() == ".html":
            files.append(path)
    return files


def _render_data_upload(snapshot) -> None:
    draft_session = snapshot is None or snapshot.workflow_status == "draft"
    with st.expander("Data upload", expanded=draft_session and st.session_state.upload_revealed):
        upload_tab, resume_tab = st.tabs(["New", "Resume"])
        with upload_tab:
            step_column, document_column = st.columns(2, gap="small")
            with step_column:
                step = st.file_uploader("STEP assembly", type=["step", "stp"])
            with document_column:
                supporting = st.file_uploader(
                    "Supporting data", accept_multiple_files=True,
                    type=["pdf", "txt", "md", "json", "csv"])
            navigator_ready = bool(st.session_state.pre_session_messages)
            if draft_session and step is None and navigator_ready:
                st.markdown("<span class='data-upload-next-focus'></span>", unsafe_allow_html=True)
            if not navigator_ready:
                st.caption("FfA Navigator is initializing. You can select files while it gets ready.")
            start_ready = (draft_session and step is not None and navigator_ready
                           and not st.session_state.busy)
            with st.container(key="start_assessment_action"):
                start_clicked = st.button(
                    "Start assessment", type="primary", width="stretch",
                    disabled=step is None or st.session_state.busy or not navigator_ready)
                if start_ready and not start_clicked:
                    st.markdown("<span class='start-assessment-next-focus'></span>",
                                unsafe_allow_html=True)
            if start_clicked:
                step_bytes = step.getvalue()
                attachments = [(item.name, item.getvalue()) for item in supporting]
                total_bytes = len(step_bytes) + sum(len(value) for _, value in attachments)
                if total_bytes > 500 * 1024 * 1024:
                    st.error("The combined upload exceeds the 500 MB session limit.")
                else:
                    _submit(st.session_state.controller.start_session, step_name=step.name,
                            step_bytes=step_bytes, supporting_files=attachments)
        with resume_tab:
            sessions = SessionController.list_sessions(WORKSPACE_ROOT)
            selected = st.selectbox(
                "Existing session", sessions,
                format_func=lambda path: path.name if path else "No sessions",
                disabled=not sessions)
            manual = st.text_input(
                "Or session folder", placeholder=str(WORKSPACE_ROOT / "data/sessions/..."))
            if st.button(
                    "Resume session", width="stretch",
                    disabled=(not sessions and not manual.strip()) or st.session_state.busy):
                target = Path(manual.strip()) if manual.strip() else selected
                st.session_state.session_root = str(Path(target).resolve())
                _submit(st.session_state.controller.resume_session, target)
        if snapshot and snapshot.workflow_status != "draft":
            revision, archive = st.columns(2)
            revision.caption(f"Revision: {snapshot.active_revision or '—'}")
            if archive.button("Prepare ZIP", width="stretch"):
                archive_data = _session_archive(snapshot.root)
                archive.download_button(
                    "Download ZIP", archive_data, file_name=f"{snapshot.session_id}.zip",
                    mime="application/zip", width="stretch")
            reports = _report_files(snapshot)
            if reports:
                report_columns = st.columns(len(reports))
                for column, report in zip(report_columns, reports):
                    column.download_button(
                        f"Download {report.stem}", report.read_bytes(), file_name=report.name,
                        mime="text/html", width="stretch")


snapshot = _snapshot()
render_topbar(st, snapshot, busy=st.session_state.busy)
_activity_pulse()

if st.session_state.last_error:
    st.error(st.session_state.last_error)
if st.session_state.intro_error and not st.session_state.pre_session_messages:
    st.warning(f"FfA Navigator could not initialize: {st.session_state.intro_error}")

structured_available = bool(available_output_scopes(snapshot)) if snapshot else False
left, middle, right = st.columns([1.35, 0.8, 1.35], gap="medium")
with left:
    with st.container(key="dialogue_column"):
        _render_data_upload(snapshot)
        with st.container(border=True, key="dialogue_panel"):
            chat_ready = (snapshot is not None and not st.session_state.busy
                          and snapshot.checkpoint != "complete")
            if chat_ready:
                st.markdown("<span class='chat-next-focus'></span>", unsafe_allow_html=True)
            render_chat(st, snapshot, busy=st.session_state.busy, on_message=_message,
                        pending_message=st.session_state.pending_user_message,
                        pre_session_messages=st.session_state.pre_session_messages)
with middle:
    with st.expander("Structured output", expanded=structured_available):
        requested_selection = render_output_navigation(
            st, snapshot, st.session_state.active_selection)
        if requested_selection is not None:
            active = st.session_state.active_selection
            if active is None:
                st.session_state.active_selection = requested_selection
            elif requested_selection.key != active.key:
                if st.session_state.structured_drafts.get(active.key) and not st.session_state.busy:
                    st.session_state.pending_selection = requested_selection
                    _confirm_navigation()
                else:
                    st.session_state.active_selection = requested_selection
        render_structured_results(st, snapshot, st.session_state.active_selection,
                                  busy=st.session_state.busy,
                                  on_field_edits=_field_edits, show_header=False)
        if st.session_state.product_events:
            with st.expander("Activity log"):
                for event in reversed(st.session_state.product_events[-12:]):
                    detail = event.get("stage") or event.get("tool") or ""
                    st.caption(f"{event.get('type')} ? {detail}")
with right:
    _visual_pulse()
