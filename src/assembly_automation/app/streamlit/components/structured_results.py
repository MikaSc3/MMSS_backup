from __future__ import annotations

from hashlib import sha256
from html import escape
from typing import Any, Callable, Mapping

from ..artifact_presenters import artifact_metrics
from ..selection import (OUTPUT_LABELS, SelectionContext, available_output_scopes,
                         entity_selections)


ASSEMBLY_FIELDS = (
    ("assembly_name_guess", "Assembly name"), ("primary_function", "Primary function"),
    ("assembly_description", "Assembly description"), ("uncertainties", "Uncertainties"),
)

DISPLAY_LABELS = {
    "subprozesse": "Subprocesses",
    "vereinzelung": "Separation",
    "handhabung": "Handling",
    "positionierung": "Positioning",
    "fuegen": "Joining",
    "pruefen": "Inspection",
    "uebergeben": "Handover",
    "ausfuehrung": "Execution mode",
    "loesung": "Solution",
    "equipment_names": "Equipment",
    "montageschritt_nr": "Assembly step",
    "basisteil": "Base part",
    "fuegeteil": "Joining part",
    "bereitstellungsart": "Provisioning method",
    "bereitstellungsstatus": "Provisioning status",
    "strategie": "Strategy",
    "massnahmen": "Measures",
    "beschreibung": "Description",
    "verantwortlich": "Responsible",
}

EXECUTION_MODES = {
    "manuell": "Manual",
    "automatisiert": "Automated",
    "manuell_mit_technischer_unterstuetzung": "Manual with technical support",
    "nicht_erforderlich": "Not required",
}
PART_FIELDS = (
    ("part_name_guess", "Part name"), ("part_identification", "Part identification"),
    ("intrinsic_summary", "Intrinsic summary"),
    ("material_and_mechanical_behavior", "Material and mechanical behavior"),
    ("geometric_characteristics", "Geometric characteristics"),
    ("bulk_behavior", "Bulk behavior"), ("magazine_behavior", "Magazine behavior"),
    ("nature_of_provision_guess", "Likely provision method"),
    ("orientation_analysis", "Orientation analysis"),
    ("gripping_analysis", "Gripping analysis"),
    ("handling_implications", "Handling implications"),
    ("assumptions", "Assumptions"),
)
SEQUENCE_FIELDS = (
    ("assembly_description", "Process description"),
    ("sequence_rationale", "Sequence rationale"), ("sequence_notation", "Sequence notation"),
    ("assumptions", "Assumptions"),
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
        format_func=lambda value: OUTPUT_LABELS[value], width="content", wrap=True)
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
        geometry = record.get("geometry") if isinstance(record.get("geometry"), Mapping) else {}
        size = geometry.get("size") if isinstance(geometry.get("size"), Mapping) else {}
        analysis = (record.get("part_analysis")
                    if isinstance(record.get("part_analysis"), Mapping) else {})
        part_name = analysis.get("part_name_guess") or record.get("name") or "—"
        intrinsic_summary = analysis.get("intrinsic_summary")
        with st.container(border=True, key="part_summary_card"):
            cols = st.columns((2.2, 1.2, .7))
            cols[0].metric("Part name", part_name)
            cols[1].metric("Part ID", record.get("part_id", "—"))
            cols[2].metric("Quantity", record.get("quantity", "—"))
            if size:
                st.caption("Calculated size · " + " × ".join(
                    f"{axis.upper()} {float(size.get(axis, 0)):.2f} mm"
                    for axis in ("x", "y", "z")))
            if intrinsic_summary:
                st.markdown("**Intrinsic summary**")
                _render_value(st, intrinsic_summary)


def _assembly_summary(st: Any, record: Mapping[str, Any], snapshot: Any) -> None:
    """Show the assembly identity and concise description in a compact card."""
    partslist = record.get("partslist")
    components = [item for item in partslist if isinstance(item, Mapping)] if isinstance(partslist, list) else []
    part_count = sum(len(item.get("instance_ids")) for item in components
                     if isinstance(item.get("instance_ids"), list))
    if not components and isinstance(partslist, list):
        part_count = len(partslist)
    assembly_artifact = snapshot.artifact("assembly")
    assembly_data = (assembly_artifact.data
                     if assembly_artifact and isinstance(assembly_artifact.data, Mapping)
                     else {})
    geometry = (assembly_data.get("geometry")
                if isinstance(assembly_data.get("geometry"), Mapping) else {})
    size = geometry.get("size") if isinstance(geometry.get("size"), Mapping) else {}
    with st.container(border=True, key="assembly_summary_card"):
        name, count = st.columns((3, 1))
        name.metric("Assembly name", record.get("assembly_name_guess") or "—")
        count.metric("Parts", part_count if part_count else "—")
        if size:
            st.caption("Calculated size · " + " × ".join(
                f"{axis.upper()} {float(size.get(axis, 0)):.2f} mm"
                for axis in ("x", "y", "z")))
        description = record.get("assembly_description")
        if description:
            st.markdown("**Assembly description**")
            _render_value(st, description)


def _sequence_summary(st: Any, record: Mapping[str, Any]) -> None:
    """Show the sequence identity and process overview in a compact card."""
    steps = record.get("steps") if isinstance(record.get("steps"), list) else []
    with st.container(border=True, key="sequence_summary_card"):
        sequence, count = st.columns((3, 1))
        sequence.metric("Sequence", "Assembly sequence")
        count.metric("Steps", len(steps) if steps else "—")
        notation = record.get("sequence_notation")
        if notation:
            st.caption(f"Sequence notation · {notation}")
        _render_sequence_steps(st, record)


def _title(value: str) -> str:
    return DISPLAY_LABELS.get(value, value.replace("_", " ").strip().title())


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
        st.markdown(EXECUTION_MODES.get(value, {
            "vorgegeben": "Specified",
            "planungsannahme": "Planning assumption",
            "halbautomatisiert": "Semi-automated",
            "vollautomatisiert": "Fully automated",
        }.get(value, value)) or "—")
    else:
        st.write(value if value is not None else "—")


def _render_assembly_partslist(st: Any, partslist: Any) -> None:
    """Render assembly components as readable engineering cards, not raw JSON."""
    if not isinstance(partslist, list):
        st.info("No component overview is available.")
        return
    components = [item for item in partslist if isinstance(item, Mapping)]
    if not components:
        # Keep legacy sessions readable while new schema results use cards.
        _render_value(st, partslist)
        return
    for index, component in enumerate(components, 1):
        name = str(component.get("name") or f"Component {index}")
        instance_ids = component.get("instance_ids")
        ids = [str(value) for value in instance_ids] if isinstance(instance_ids, list) else []
        color = component.get("rendered_color")
        with st.container(border=True):
            quantity = len(ids) if ids else "—"
            st.markdown(
                '<div class="part-card-header">'
                f'<span class="part-card-name">{escape(name)}</span>'
                f' <span>· Quantity: {escape(str(quantity))}'
                f' · Render color: {escape(str(color or "—"))}</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            if ids:
                st.caption("Instance IDs · " + ", ".join(ids))
            geometry = component.get("geometry")
            role = component.get("assembly_role")
            if isinstance(geometry, list) and geometry:
                st.markdown("**Geometry**")
                _render_value(st, geometry)
            if isinstance(role, list) and role:
                st.markdown("**Assembly role**")
                _render_value(st, role)


def _render_fields_as_expanders(st: Any, record: Mapping[str, Any], *,
                                expanded: set[str] | None = None,
                                omit: set[str] | None = None) -> None:
    """Give every saved top-level field one consistent, collapsible view."""
    expanded = expanded or set()
    omit = omit or set()
    for key, value in record.items():
        if key in omit:
            continue
        with st.expander(_title(str(key)), expanded=key in expanded):
            _render_value(st, value)


def _render_assembly_analysis(st: Any, record: Mapping[str, Any]) -> None:
    """Use expanders for all assembly fields, with a component-aware parts list."""
    for key, value in record.items():
        with st.expander(_title(str(key)), expanded=key in {"assembly_name_guess", "primary_function"}):
            if key == "partslist":
                _render_assembly_partslist(st, value)
            else:
                _render_value(st, value)


def _strip_list_marker(value: str) -> str:
    """Normalize accidental Markdown list markers inside array items."""
    import re

    return re.sub(r"^(?:[-*]|\d+[.)])\s+", "", value)


def _render_overall_ffa(st: Any, value: Any) -> None:
    """Render the four subprocess summaries as one compact comparison table."""
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        _render_value(st, value)
        return
    rows = []
    for item in value:
        potential = str(item.get("automation_potential") or "—")
        normalized = potential.strip().lower()
        status = next((level for level in ("low", "medium", "high")
                       if normalized.startswith(level)), "neutral")
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('subprocess') or '—').title())}</td>"
            f'<td class="ffa-potential-{status}">{escape(potential)}</td>'
            f"<td>{escape(str(item.get('risks') or '—'))}</td>"
            "</tr>"
        )
    st.markdown(
        '<table class="overall-ffa-table">'
        '<thead><tr><th>Subprocess</th><th>Automation potential</th><th>Risks</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>',
        unsafe_allow_html=True,
    )


def _compact_lines(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "—"
    return str(value) if value not in {None, ""} else "—"


def _layout_number(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _render_automation_idea_summary(st: Any, record: Mapping[str, Any]) -> None:
    architecture = record.get("system_architecture")
    with st.container(border=True, key="automation_idea_summary_card"):
        st.markdown("**System architecture**")
        _render_value(st, architecture if architecture else "—")


def _render_subprocess_summary(st: Any, value: Any) -> None:
    if not isinstance(value, Mapping):
        _render_value(st, value)
        return
    mode = value.get("ausfuehrung") or value.get("automation_mode") or "—"
    mode = EXECUTION_MODES.get(str(mode), mode)
    solution = value.get("loesung") or value.get("solution") or "—"
    equipment = value.get("equipment_names") or value.get("equipment") or []
    st.markdown(
        f"**{_title(str(value.get('name') or 'Subprocess'))}** · "
        f"{escape(str(mode))}<br>{escape(str(solution))}<br>"
        f"<span class='structured-muted'>Equipment: {escape(_compact_lines(equipment))}</span>",
        unsafe_allow_html=True,
    )


def _render_equipment_summary(st: Any, equipment: Any, *, layout: bool = False) -> None:
    if not isinstance(equipment, list):
        return
    if layout:
        rows = []
        for item in equipment:
            if not isinstance(item, Mapping):
                continue
            rows.append({
                "Name": item.get("name") or "Equipment",
                "X": _layout_number(item.get("x", "—")),
                "Y": _layout_number(item.get("y", "—")),
                "Size": _layout_number(item.get("size", "—")),
            })
        if rows:
            st.table(rows)
        return
    for item in equipment:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name") or "Equipment"
        step_ids = item.get("step_ids") or item.get("step_id") or "—"
        task = item.get("function") or item.get("task")
        specimen = item.get("specimen") or "—"
        task_text = f" · {escape(str(task))}" if task else ""
        st.markdown(
            f"<span class='equipment-name'>{escape(str(name))}</span> · "
            f"Step IDs: {escape(_compact_lines(step_ids))}"
            f"{task_text}<br><span class='structured-muted'>Specimen: "
            f"{escape(_compact_lines(specimen))}</span>",
            unsafe_allow_html=True,
        )


def _render_planning_record(st: Any, artifact_id: str, record: Mapping[str, Any]) -> None:
    if artifact_id == "automation_idea":
        _render_automation_idea_summary(st, record)
    if artifact_id == "detailed_step_plans":
        subprocesses = record.get("subprozesse")
        if isinstance(subprocesses, Mapping):
            with st.container(border=True, key="subprocess_summary_card"):
                for name, value in subprocesses.items():
                    if isinstance(value, Mapping):
                        _render_subprocess_summary(st, dict(value) | {"name": name})
        with st.container(border=True, key="detailed_equipment_summary_card"):
            st.markdown("**Equipment**")
            _render_equipment_summary(st, record.get("equipment"))
    elif artifact_id == "automation_concept":
        with st.container(border=True, key="concept_equipment_summary_card"):
            _render_equipment_summary(st, record.get("equipment"))
    elif artifact_id == "layout":
        with st.container(border=True, key="layout_equipment_summary_card"):
            _render_equipment_summary(st, record.get("equipment"), layout=True)


def _render_step_analysis(st: Any, artifact_id: str, record: Mapping[str, Any]) -> None:
    step = record.get("step") if isinstance(record.get("step"), Mapping) else {}
    payload_key = "interaction_analysis" if artifact_id == "interaction_analysis" else "ffa_assessment"
    payload = record.get(payload_key)
    featured_key = "geometric_interaction" if artifact_id == "interaction_analysis" else "overall_ffa"
    card_key = ("interaction_summary_card" if artifact_id == "interaction_analysis"
                else "ffa_summary_card")
    with st.container(border=True, key=card_key):
        refs = st.columns((.55, 1.3, 1.3, 1.05))
        refs[0].metric("Step", step.get("step_id", "—"))
        refs[1].metric("Base", _reference(step.get("base_part"), "Initial placement"))
        refs[2].metric("Joining", _reference(step.get("joining_part")))
        refs[3].metric("Process", _reference(step.get("joining_process")))
        description = step.get("step_description")
        if description:
            st.caption(str(description))
        if isinstance(payload, Mapping) and featured_key in payload:
            st.markdown(f"**{_title(featured_key)}**")
            if featured_key == "overall_ffa":
                _render_overall_ffa(st, payload[featured_key])
            else:
                _render_value(st, payload[featured_key])
    if not isinstance(payload, Mapping):
        st.info("This step result is being prepared.")
        return
    for key, value in payload.items():
        if key == featured_key:
            continue
        with st.expander(_title(str(key)), expanded=False):
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
    on_field_edits: Callable[[str, str, dict[str, Any], str, str, str, str], None],
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
    edits: dict[str, Any] = {}
    with st.container(border=True):
        st.caption("Editable descriptive fields")
        for field, field_label in fields:
            if field not in values:
                continue
            original_value = values.get(field)
            if isinstance(original_value, str):
                original = original_value
                list_field = False
            elif (isinstance(original_value, list)
                  and all(isinstance(item, str) for item in original_value)):
                original = "\n".join(original_value)
                list_field = True
            else:
                continue
            generation = st.session_state.get("structured_editor_generation", 0)
            widget_key = f"domain_field::{generation}::{selection_key}::{field}"
            edited = st.text_area(field_label, value=original, key=widget_key,
                                  height=92 if len(original) > 100 else 68)
            new_value: str | list[str] = (
                [line.strip() for line in edited.splitlines() if line.strip()]
                if list_field else edited.strip())
            if new_value != original_value:
                edits[field] = new_value
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


def _editable_fields(record: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    fields = []
    for key, value in record.items():
        if isinstance(value, (str, list)) and (
                isinstance(value, str) or all(isinstance(item, str) for item in value)):
            fields.append((str(key), _title(str(key))))
    return tuple(fields)


def render_structured_results(
    st: Any, snapshot: Any, selection: SelectionContext | None, *, busy: bool,
    on_field_edits: Callable[[str, str, dict[str, Any], str, str, str, str], None],
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
    # A selected part already has its own ID and quantity card below. Do not
    # distract with BOM-wide counts. Assembly gets a purpose-built summary.
    edit_fields = fields or _editable_fields(record)
    header, edit_control = st.columns((4.8, 1.2), vertical_alignment="center")
    with header:
        st.markdown(
            f'<div class="structured-output-header">{escape(label)}</div>',
            unsafe_allow_html=True,
        )
    with edit_control:
        edit_mode = st.toggle(
            "Edit mode", key=f"edit_mode::{selection.key}", disabled=busy,
            label_visibility="visible",
        )
    if edit_mode and not edit_fields:
        st.info("This output has no safely editable top-level fields.")
    if artifact_id == "assembly_overview":
        _assembly_summary(st, record, snapshot)
    elif artifact_id == "sequence":
        _sequence_summary(st, record)
    metrics = artifact_metrics(artifact.artifact_id, artifact.data)
    # These outputs are presented one selected assembly step at a time. Their
    # step view already identifies the current step, so an artifact-wide total
    # rendered as a large metric is redundant and visually misleading.
    if metrics and artifact_id not in {
        "assembly_overview", "bom", "sequence", "interaction_analysis", "ffa_assessment",
        "detailed_step_plans", "layout",
    }:
        columns = st.columns(len(metrics))
        for column, (name, value) in zip(columns, metrics.items()):
            column.metric(name, value)
    _render_readonly(st, artifact_id, record)
    if edit_mode:
        _render_editable_fields(
            st, artifact_id=artifact_id, artifact=artifact, record=record,
            entity_id=entity_id, fields=edit_fields, selection=selection, label=label,
            busy=busy, on_field_edits=on_field_edits)
    elif artifact_id in {"interaction_analysis", "ffa_assessment"}:
        _render_step_analysis(st, artifact_id, record)
    elif artifact_id in {"automation_idea", "detailed_step_plans", "automation_concept", "layout", "cost_estimate"}:
        _render_planning_record(st, artifact_id, record)
        _render_fields_as_expanders(st, record, omit={"equipment"} if artifact_id == "layout" else set())
    else:
        values = record.get("part_analysis", {}) if artifact_id == "bom" else record
        if isinstance(values, Mapping):
            if artifact_id == "assembly_overview":
                _render_assembly_analysis(st, values)
            else:
                _render_fields_as_expanders(
                    st, values, expanded={"part_name_guess", "part_identification", "assembly_description"},
                    omit={"steps"} if artifact_id == "sequence" else set())
    if st.toggle("Show raw JSON", key=f"raw_json::{selection.key}"):
        st.json(record, expanded=2)
