from __future__ import annotations

from hashlib import sha256
from typing import Any, Callable, Mapping

from ..artifact_presenters import artifact_metrics
from ..selection import (OUTPUT_LABELS, SelectionContext, available_output_scopes,
                         entity_selections)


ASSEMBLY_FIELDS = (
    ("assembly_name_guess", "Assembly name"), ("primary_function", "Primary function"),
    ("assembly_description", "Assembly description"),
)
PART_FIELDS = (
    ("part_name_guess", "Part name"), ("part_identification", "Part identification"),
    ("intrinsic_summary", "Intrinsic summary"),
    ("material_and_mechanical_behavior", "Material and mechanical behavior"),
    ("geometric_characteristics", "Geometric characteristics"),
    ("bulk_behavior", "Bulk behavior"), ("magazine_behavior", "Magazine behavior"),
    ("nature_of_provision_guess", "Likely provision method"),
    ("gripping_analysis", "Gripping analysis"),
    ("handling_implications", "Handling implications"),
)
SEQUENCE_FIELDS = (
    ("assembly_name", "Assembly name"), ("assembly_description", "Process description"),
    ("sequence_rationale", "Sequence rationale"), ("sequence_notation", "Sequence notation"),
)


def render_output_navigation(st: Any, snapshot: Any,
                             current: SelectionContext | None) -> SelectionContext | None:
    """Render the master artifact selector and its optional part/step level."""
    scopes = available_output_scopes(snapshot)
    if not scopes:
        st.info("Artifacts appear here as stages complete.")
        return None
    override = st.session_state.pop("structured_selection_override", None)
    preferred_scope = override.scope if isinstance(override, SelectionContext) else (
        current.scope if current and current.scope in scopes else scopes[0])
    if st.session_state.get("structured_scope") not in scopes or override is not None:
        st.session_state["structured_scope"] = preferred_scope
    scope = st.segmented_control(
        "Output type", scopes, key="structured_scope", required=True,
        format_func=lambda value: OUTPUT_LABELS[value], width="stretch", wrap=True)
    if scope is None:
        scope = preferred_scope
    options = entity_selections(snapshot, scope)
    if not options:
        st.info(f"{OUTPUT_LABELS[scope]} is being prepared.")
        return None
    if len(options) == 1:
        return options[0][1]
    key = f"structured_entity::{scope}"
    desired = override if isinstance(override, SelectionContext) and override.scope == scope else current
    desired_index = next((index for index, (_label, selection) in enumerate(options)
                          if desired and selection.key == desired.key), 0)
    existing = st.session_state.get(key)
    if override is not None or type(existing) is not int or not 0 <= existing < len(options):
        st.session_state[key] = desired_index
    noun = "Part" if scope == "part" else "Assembly step"
    selected_index = st.selectbox(
        noun, range(len(options)), key=key,
        format_func=lambda index: options[index][0], label_visibility="collapsed")
    return options[selected_index][1]


def _selected_document(snapshot: Any, selection: SelectionContext | None):
    if selection is None:
        return None
    if selection.scope == "assembly":
        artifact = snapshot.artifact("assembly_overview")
        if artifact and isinstance(artifact.data, dict):
            return ("assembly_overview", "Assembly analysis", artifact, artifact.data,
                    "assembly", ASSEMBLY_FIELDS)
    if selection.scope == "part":
        artifact = snapshot.artifact("enriched_bom")
        if artifact and isinstance(artifact.data, dict):
            matches = [part for part in artifact.data.get("parts", [])
                       if isinstance(part, dict) and part.get("part_id") == selection.entity_id]
            if len(matches) == 1 and isinstance(matches[0].get("part_analysis"), dict):
                return ("bom", f"Part · {selection.entity_id}", artifact,
                        matches[0], selection.entity_id, PART_FIELDS)
    if selection.scope == "sequence":
        artifact = snapshot.artifact("assembly_sequence")
        if artifact and isinstance(artifact.data, dict):
            return ("sequence", "Assembly sequence", artifact, artifact.data,
                    "sequence", SEQUENCE_FIELDS)
    if selection.scope in {"interaction", "ffa"}:
        artifact_id = "interaction_analysis" if selection.scope == "interaction" else "ffa_assessment"
        artifact = snapshot.artifact(artifact_id)
        if artifact and isinstance(artifact.data, dict):
            matches = [item for item in artifact.data.get("steps", [])
                       if isinstance(item, dict) and isinstance(item.get("step"), dict)
                       and item["step"].get("step_id") == selection.step_id]
            if len(matches) == 1:
                label = ("Interaction analysis" if selection.scope == "interaction"
                         else "FfA analysis")
                return (artifact_id, f"{label} · Step {selection.step_id}", artifact,
                        matches[0], f"step:{selection.step_id}", ())
    if selection.scope in {"automation_idea", "automation_concept", "layout", "cost_estimate"}:
        artifact_id = selection.scope
        artifact = snapshot.artifact(artifact_id)
        if artifact and isinstance(artifact.data, dict):
            return (artifact_id, OUTPUT_LABELS[selection.scope], artifact, artifact.data,
                    selection.scope, ())
    if selection.scope == "detailed_plans":
        artifact = snapshot.artifact("detailed_step_plans")
        if artifact and isinstance(artifact.data, dict):
            matches = [item for item in artifact.data.get("steps", [])
                       if isinstance(item, dict)
                       and item.get("montageschritt_nr") == selection.step_id]
            if len(matches) == 1:
                return ("detailed_step_plans", f"Detailed plan · Step {selection.step_id}",
                        artifact, matches[0], f"step:{selection.step_id}", ())
    return None


def _render_readonly(st: Any, artifact: str, record: Mapping[str, Any]) -> None:
    if artifact == "bom":
        cols = st.columns(2)
        cols[0].metric("Part ID", record.get("part_id", "—"))
        cols[1].metric("Quantity", record.get("quantity", "—"))
        geometry = record.get("geometry") if isinstance(record.get("geometry"), Mapping) else {}
        size = geometry.get("size") if isinstance(geometry.get("size"), Mapping) else {}
        if size:
            st.caption("Calculated size · " + " × ".join(
                f"{axis.upper()} {float(size.get(axis, 0)):.2f} mm" for axis in ("x", "y", "z")))


def _title(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _reference(value: Any, fallback: str = "—") -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or fallback
    return str(value) if value not in {None, ""} else fallback


def _render_value(st: Any, value: Any, *, depth: int = 0) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            st.markdown(f"**{_title(str(key))}**")
            _render_value(st, nested, depth=depth + 1)
    elif isinstance(value, list):
        if all(not isinstance(item, (Mapping, list)) for item in value):
            lines = [_strip_list_marker(str(item).strip()) for item in value]
            st.markdown("\n".join(f"- {line}" for line in lines if line))
        else:
            for index, item in enumerate(value, 1):
                if isinstance(item, Mapping):
                    st.caption(f"Item {index}")
                _render_value(st, item, depth=depth + 1)
    elif isinstance(value, str):
        st.markdown(value or "—")
    else:
        st.write(value if value is not None else "—")


def _strip_list_marker(value: str) -> str:
    """Normalize accidental Markdown list markers inside array items."""
    import re

    return re.sub(r"^(?:[-*]|\d+[.)])\s+", "", value)


def _render_step_analysis(st: Any, artifact_id: str, record: Mapping[str, Any]) -> None:
    step = record.get("step") if isinstance(record.get("step"), Mapping) else {}
    st.caption(str(step.get("step_description") or ""))
    refs = st.columns(3)
    refs[0].metric("Base", _reference(step.get("base_part"), "Initial placement"))
    refs[1].metric("Joining", _reference(step.get("joining_part")))
    refs[2].metric("Process", _reference(step.get("joining_process")))
    payload_key = "interaction_analysis" if artifact_id == "interaction_analysis" else "ffa_assessment"
    payload = record.get(payload_key)
    if not isinstance(payload, Mapping):
        st.info("This step result is being prepared.")
        return
    expanded = {"geometric_interaction", "overall_ffa"}
    for key, value in payload.items():
        with st.expander(_title(str(key)), expanded=key in expanded):
            _render_value(st, value)


def _render_sequence_steps(st: Any, record: Mapping[str, Any]) -> None:
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    st.markdown("**Assembly steps**")
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        step_id = step.get("step_id", "—")
        process = step.get("joining_process") or "Operation"
        with st.expander(f"Step {step_id} · {process}", expanded=False):
            st.markdown(str(step.get("step_description") or "—"))
            st.caption(
                f"Base: {_reference(step.get('base_part'), 'Initial placement')} · "
                f"Joining: {_reference(step.get('joining_part'))} · "
                f"Context: {_reference(step.get('belongs_to'))}")


def _render_editable_fields(
    st: Any, *, artifact_id: str, artifact: Any, record: Mapping[str, Any],
    entity_id: str, fields: tuple[tuple[str, str], ...], selection: SelectionContext,
    label: str, busy: bool,
    on_field_edits: Callable[[str, str, dict[str, str], str, str, str, str], None],
) -> None:
    values = record.get("part_analysis", {}) if artifact_id == "bom" else record
    if not isinstance(values, Mapping):
        st.error("The selected product record has an invalid structure.")
        return
    try:
        expected_hash = sha256(artifact.path.read_bytes()).hexdigest()
    except OSError:
        st.info("The selected artifact is being updated. It will reappear automatically.")
        return
    selection_key = selection.key
    known_hashes = st.session_state.setdefault("structured_artifact_hashes", {})
    previous_hash = known_hashes.get(selection_key)
    if previous_hash is not None and previous_hash != expected_hash:
        # The selected artifact changed outside this form. The persisted JSON
        # is authoritative; never let a widget value from the old document
        # become a new manual edit.
        known_hashes[selection_key] = expected_hash
        st.session_state.setdefault("structured_drafts", {}).clear()
        st.session_state.pending_selection = None
        st.session_state.pop("navigation_after_save", None)
        st.session_state.structured_editor_generation = (
            st.session_state.get("structured_editor_generation", 0) + 1)
        st.rerun()
    known_hashes[selection_key] = expected_hash
    edits: dict[str, str] = {}
    with st.container(border=True):
        st.caption("Editable descriptive fields")
        for field, field_label in fields:
            if field not in values:
                continue
            original_value = values.get(field)
            if isinstance(original_value, list):
                continue
            if not isinstance(original_value, str):
                continue
            original = original_value or ""
            generation = st.session_state.get("structured_editor_generation", 0)
            widget_key = f"domain_field::{generation}::{selection_key}::{field}"
            edited = st.text_area(field_label, value=original, key=widget_key,
                                  height=92 if len(original) > 100 else 68)
            if edited != original:
                edits[field] = edited
        drafts = st.session_state.setdefault("structured_drafts", {})
        if edits:
            drafts[selection_key] = {"artifact": artifact_id, "entity_id": entity_id,
                                     "changes": edits, "expected_sha256": expected_hash,
                                     "label": label}
            st.warning(f"{len(edits)} unsaved field change(s)")
            reason = st.text_input(
                "Change note", value="User-edited structured result",
                key=f"edit_reason::{generation}::{selection_key}")
            saving = busy and st.session_state.get("save_draft_key") == selection_key
            if saving:
                st.info("Saving changes…")
            elif st.button("Save changes", type="primary", disabled=busy,
                           width="stretch", key=f"save_fields::{selection_key}"):
                raw = f"Updated {label}: {reason}"
                on_field_edits(artifact_id, entity_id, edits, expected_hash,
                               reason, raw, selection_key)
        else:
            drafts.pop(selection_key, None)


def render_structured_results(
    st: Any, snapshot: Any, selection: SelectionContext | None, *, busy: bool,
    on_field_edits: Callable[[str, str, dict[str, str], str, str, str, str], None],
    show_header: bool = True,
) -> None:
    if show_header:
        st.markdown("#### Structured output")
        st.caption("Select an output, then a part or assembly step")
    if snapshot is None or selection is None:
        return
    chosen = _selected_document(snapshot, selection)
    if chosen is None:
        st.info("The selected result is being prepared.")
        return
    artifact_id, label, artifact, record, entity_id, fields = chosen
    if not artifact.path.is_file():
        st.info("The selected artifact is being updated. It will reappear automatically.")
        return
    st.markdown(f"**{label}**")
    metrics = artifact_metrics(artifact.artifact_id, artifact.data)
    if metrics:
        columns = st.columns(len(metrics))
        for column, (name, value) in zip(columns, metrics.items()):
            column.metric(name, value)
    _render_readonly(st, artifact_id, record)
    if artifact_id in {"interaction_analysis", "ffa_assessment"}:
        _render_step_analysis(st, artifact_id, record)
    elif artifact_id in {"automation_idea", "detailed_step_plans", "automation_concept", "layout", "cost_estimate"}:
        _render_value(st, record)
    else:
        values = record.get("part_analysis", {}) if artifact_id == "bom" else record
        if isinstance(values, Mapping):
            _render_value(st, values)
        if artifact_id == "sequence":
            _render_sequence_steps(st, record)
        _render_editable_fields(
            st, artifact_id=artifact_id, artifact=artifact, record=record,
            entity_id=entity_id, fields=fields, selection=selection, label=label,
            busy=busy, on_field_edits=on_field_edits)
    if st.toggle("Show raw JSON", key=f"raw_json::{selection.key}"):
        st.json(record, expanded=2)
