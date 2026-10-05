"""Product-phase progress derived from manifests and normalized events."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any


@dataclass(frozen=True)
class Phase:
    phase_id: str
    label: str
    stage_prefixes: tuple[str, ...]


PHASES = (
    Phase("setup", "Session setup", ()),
    Phase("preprocessing", "STEP preprocessing", ("step_preprocessing",)),
    Phase("assembly", "Assembly review", ("assembly_analysis",)),
    Phase("parts", "Part analysis", ("monopart_analysis", "bom_merge")),
    Phase("sequence", "Sequence generation", ("sequence_generation",)),
    Phase("sequence_review", "Sequence review", ()),
    Phase("feasibility", "Feasibility analysis", (
        "sequence_rendering", "interaction_analysis", "ffa_assessment",
        "ffa_scoring", "report_synthesis", "report_rendering",
    )),
    Phase("automation_idea", "Automation idea", ()),
    Phase("detailed_planning", "Detailed planning", ()),
    Phase("concept", "Automation concept", ()),
    Phase("layout", "Layout planning", ()),
    Phase("costing", "Cost calculation", ()),
)


def _stage_complete(stages: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        matching = [value for name, value in stages.items()
                    if name == prefix or name.startswith(prefix + ":")]
        if not matching or not all(isinstance(value, dict) and value.get("status") == "complete"
                                   for value in matching):
            return False
    return bool(prefixes)


def phase_states(snapshot: Any) -> dict[str, str]:
    states = {phase.phase_id: "queued" for phase in PHASES}
    # Keep the legacy report state available to callers while the rendered
    # track presents all feasibility work as one stable product phase.
    states["report"] = "queued"
    if snapshot is None:
        return states
    if snapshot.workflow_status == "draft":
        states["setup"] = "waiting"
        return states
    states["setup"] = "complete"
    stages = dict(snapshot.stages)
    for phase in PHASES:
        if phase.stage_prefixes and _stage_complete(stages, phase.stage_prefixes):
            states[phase.phase_id] = "complete"
    if _stage_complete(stages, ("report_synthesis", "report_rendering")):
        states["report"] = "complete"
    if snapshot.active_revision:
        states["sequence"] = "complete"
        states["sequence_review"] = ("complete" if snapshot.approved_revision
                                     or snapshot.workflow_status == "complete" else "waiting")
    waiting = {
        "awaiting_upload": "setup", "preparing": "preprocessing", "awaiting_assembly_review": "assembly",
        "awaiting_bom_review": "parts", "awaiting_sequence_generation": "sequence",
        "awaiting_sequence_approval": "sequence_review",         "sequence_approved": "feasibility",
        "planning_idea": "automation_idea",
        "awaiting_idea_review": "automation_idea",
        "planning_steps": "detailed_planning",
        "awaiting_concept_review": "concept",
        "awaiting_layout_review": "layout",
        "awaiting_cost_review": "costing",
    }.get(snapshot.checkpoint)
    planning_progress = {
        "planning_idea": (),
        "awaiting_idea_review": (),
        "planning_steps": ("automation_idea",),
        "awaiting_concept_review": ("automation_idea", "detailed_planning"),
        "awaiting_layout_review": ("automation_idea", "detailed_planning", "concept"),
        "awaiting_cost_review": ("automation_idea", "detailed_planning", "concept", "layout"),
    }
    for phase_id in planning_progress.get(snapshot.checkpoint, ()):
        states[phase_id] = "complete"
    if waiting and states.get(waiting) != "complete":
        states[waiting] = "waiting"
    return states


def _latest_activity(events: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    for event in reversed(events):
        kind = str(event.get("type", ""))
        if kind.startswith(("workflow.stage", "session.setup", "tool.")):
            if (kind == "workflow.stage.progress"
                    and event.get("stage") == "step_preprocessing"):
                return "STEP preprocessing", event
            raw = event.get("operation") or event.get("stage") or event.get("tool")
            if raw:
                return str(raw).replace("_", " ").replace(":", " · "), event
    return None, None


def _event_phase(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    kind = str(event.get("type") or "")
    if kind.startswith("session.setup"):
        return "setup"
    if kind.startswith("tool."):
        return {
            "automation_concept_idea_generator": "automation_idea",
            "automation_concept_planner": "detailed_planning",
            "revise_automation_concept": "concept",
            "layout_planner": "layout",
            "revise_layout": "layout",
            "cost_planner": "costing",
        }.get(str(event.get("tool") or ""))
    stage = str(event.get("stage") or "").split(":", 1)[0]
    if stage == "step_preprocessing":
        return "preprocessing"
    if stage in {"sequence_rendering", "interaction_analysis", "ffa_assessment",
                 "ffa_scoring", "report_synthesis", "report_rendering"}:
        return "feasibility"
    for phase in PHASES:
        if stage in phase.stage_prefixes:
            return phase.phase_id
    return None


def render_progress(st: Any, snapshot: Any, events: list[dict[str, Any]], *, busy: bool) -> None:
    states = phase_states(snapshot)
    _activity, event = _latest_activity(events)
    failed = bool(events and events[-1].get("type") == "agent.turn.failed")
    active = _event_phase(event) if busy else None
    if active is None:
        active = next((phase.phase_id for phase in PHASES
                       if states[phase.phase_id] == "waiting"), None)
    visible_until = next(
        (index for index, phase in enumerate(PHASES)
         if states[phase.phase_id] != "complete"),
        len(PHASES) - 1,
    )
    if active is not None:
        visible_until = max(visible_until, next(
            index for index, phase in enumerate(PHASES) if phase.phase_id == active))
    # Future stages used to be rendered as empty, unlabeled dots. Limit the
    # track to the known path so every visible node has a meaningful label.
    visible_phases = PHASES[:visible_until + 1]
    nodes = []
    for index, phase in enumerate(visible_phases, 1):
        state = states[phase.phase_id]
        if phase.phase_id == active:
            state = "failed" if failed else "active"
        connector = " complete" if states[phase.phase_id] == "complete" else ""
        marker = "✓" if state == "complete" else ""
        label = escape(phase.label)
        nodes.append(
            f'<div class="workflow-phase {state}">'
            f'<div class="workflow-node">{marker}</div>'
            f'<div class="workflow-connector{connector}"></div>'
            f'<div class="workflow-label">{label}</div></div>')
    detail = ""
    if event and type(event.get("total")) is int and event["total"] > 0:
        done, total = int(event.get("completed") or 0), int(event["total"])
        ratio = min(max(done / total, 0), 1) * 100
        detail = (
            '<div class="workflow-item-progress">'
            f'<span style="width:{ratio:.1f}%"></span></div>'
            f'<div class="workflow-item-count">{done} / {total}</div>')
    st.markdown(
        '<div class="workflow-progress">'
        f'<div class="workflow-track">{"".join(nodes)}</div>{detail}</div>',
        unsafe_allow_html=True,
    )
