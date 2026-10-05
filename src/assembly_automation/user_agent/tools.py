"""Stateful, validated workflow tools exposed to the conversational agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from assembly_automation.workflows.definitions import (AssemblyAssessmentWorkflow,
                                                       AutomationPlanningWorkflow)
from assembly_automation.workflows.definitions.final_assessment_graph import run_final_assessment_graph
from assembly_automation.workflows.definitions.automation_concept_graph import run_automation_concept_graph
from assembly_automation.workflows.definitions.assessment_review_graphs import (
    run_assembly_review_graph, run_bom_review_graph, run_sequence_review_graph)
from assembly_automation.workflows.runtime.node import write_run_record

from .artifacts import ArtifactEditor
from .artifact_change import ArtifactChangePlanner, resolve_target
from .documents import DocumentStore
from .feedback import FeedbackStore
from .storage import atomic_write_json
from .state_transitions import invalidate, mark_current
from .session_state import AgentSessionState


# Groups describe product capabilities, not implementation-node categories.
# The agent sees only the state-appropriate subset of these tools.
TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "session_context": ("inspect_session", "ingest_documents"),
    "assessment_review": ("analyse_assembly", "analyse_monoparts", "generate_sequence",
                          "revise_sequence", "ffa_evaluation"),
    "artifact_review": ("read_artifact", "summarize_parts", "change_artifact"),
    "automation_planning": ("automation_concept_idea_generator", "automation_concept_planner",
                            "revise_automation_concept"),
    "layout_and_cost": ("layout_planner", "revise_layout", "cost_planner"),
    "presentation": ("generate_engineering_powerpoint",),
}
INTERNAL_TOOL_NAMES = ("edit_intermediate_artifact", "edit_artifact_fields")


def _agent_tool_message(tool_name: str, result: Mapping[str, Any]) -> str:
    revision = result.get("revision_id")
    messages = {
        "analyse_assembly": "Assembly context has been created. Read it with read_artifact('assembly_context').",
        "analyse_monoparts": "The BOM has been created. Read it with read_artifact('BOM'); inspect_session() lists valid part IDs.",
        "generate_sequence": f"Sequence revision {revision} has been created. Read it with read_artifact('sequence', '{revision}').",
        "revise_sequence": f"Sequence revision {revision} has been created. Read it with read_artifact('sequence', '{revision}').",
        "ffa_evaluation": f"Report for sequence revision {revision} has been created. Read it with read_artifact('report', '{revision}').",
        "automation_concept_idea_generator": f"Automation idea {revision} has been created. Read it with read_artifact('automation_idea', '{revision}').",
        "automation_concept_planner": f"Automation concept {revision} and detailed plans have been created. Read them with read_artifact('automation_concept', '{revision}') or read_artifact('detailed_step_plans', '{revision}').",
        "revise_automation_concept": f"Automation concept {revision} has been created. Read it with read_artifact('automation_concept', '{revision}').",
        "layout_planner": f"Layout revision {revision} has been created. Read it with read_artifact('layout', '{revision}').",
        "revise_layout": f"Layout revision {revision} has been created. Read it with read_artifact('layout', '{revision}').",
        "cost_planner": f"Cost estimate {revision} has been created. Read it with read_artifact('cost_estimate', '{revision}').",
        "generate_engineering_powerpoint": "The engineering PowerPoint was generated and is available as a downloadable session artifact.",
        "read_artifact": "The requested artifact has been read; use its returned data without inspecting the session again.",
        "inspect_session": "The session inventory has been returned, including available part IDs and artifact revisions.",
    }
    return messages.get(tool_name, "The tool completed successfully; continue using its returned data.")


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not available: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    return value


class WorkflowAgentTools:
    """Product control surface over one assembly-assessment session."""

    def __init__(self, *, workflow: AssemblyAssessmentWorkflow,
                 step_file: str | Path | None = None,
                 supporting_files: list[str | Path] | None = None):
        self.workflow = workflow
        self.paths = workflow.paths
        self.step_file = Path(step_file).resolve() if step_file else None
        self.feedback = FeedbackStore(self.paths.root)
        self.artifacts = ArtifactEditor(self.paths.root)
        self.documents = DocumentStore(self.paths.root)
        self.supporting_files = [Path(path).resolve(strict=True) for path in (supporting_files or [])]
        self.state_path = self.paths.user_agent_root / "state.json"
        self.current_user_message: str | None = None
        self.artifact_change_planner: ArtifactChangePlanner | None = None
        self.status_callback: Callable[[str], None] | None = None
        self._automation_workflow: AutomationPlanningWorkflow | None = None
        if not self.state_path.exists():
            self._write_state(self._derive_state())

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """Connect an application status message to a workflow boundary."""
        self.status_callback = callback

    def _announce_status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)

    def _derive_state(self) -> dict[str, Any]:
        manifest_path = self.paths.root / "manifest.json"
        manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.is_file() else {})
        active = manifest.get("active_sequence_revision")
        assembly_revision = self.paths.active_revision("assembly")
        monoparts_revision = self.paths.active_revision("monoparts")
        sequence_exists = bool(active and
                               (self.paths.revision(active) / "assembly_sequence.json").is_file())
        report_exists = bool(active and (self.paths.reports(active) / "report.json").is_file())
        return {"active_sequence_revision": active,
                "active_assembly_revision": assembly_revision,
                "active_monoparts_revision": monoparts_revision,
                "stale": {"assembly": not self.paths.assembly_overview.is_file(),
                          "monoparts": not self.paths.enriched_bom.is_file(),
                          "sequence": not sequence_exists,
                          "renderings": not sequence_exists,
                          "final": not report_exists}}

    def _state(self) -> dict[str, Any]:
        return AgentSessionState.model_validate_json(
            self.state_path.read_text(encoding="utf-8")).model_dump()

    def _write_state(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.state_path, AgentSessionState.model_validate(state).model_dump())

    def _sync_published_edit(self, artifact: str, path: str) -> None:
        """Make edited active artifacts immediately visible to all readers."""
        manifest_key = {
            "assembly_overview": "assembly_overview",
            "bom": "enriched_bom",
            "sequence": "assembly_sequence",
        }.get(artifact)
        if manifest_key is None:
            return
        manifest_path = self.paths.root / "manifest.json"
        if not manifest_path.is_file():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Session manifest must contain a JSON object")
        relative = Path(path).resolve().relative_to(self.paths.root).as_posix()
        manifest.setdefault("artifacts", {})[manifest_key] = relative
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(manifest_path, manifest)

    def _step(self) -> Path:
        if self.step_file is not None:
            return self.step_file.resolve(strict=True)
        matches = sorted(path for path in self.paths.input.glob("*")
                         if path.is_file() and path.suffix.lower() in {".step", ".stp"})
        if len(matches) != 1:
            raise ValueError("Supply one STEP file or keep exactly one STEP/STP file in session/input")
        return matches[0]

    def _context(self, *scopes: str, targets: list[str] | None = None) -> str:
        return self.feedback.compile_context(scopes=scopes, targets=targets or [])

    def _planning(self) -> AutomationPlanningWorkflow:
        if self._automation_workflow is None:
            settings = getattr(self.workflow, "settings", None)
            if not isinstance(settings, Mapping):
                raise RuntimeError("The assembly workflow does not expose planning settings")
            self._automation_workflow = AutomationPlanningWorkflow(
                session_root=self.paths.root, settings=settings)
        return self._automation_workflow

    def _next_planning_revision(self, kind: str) -> str:
        if kind not in {"idea", "concept", "layout", "cost"}:
            raise ValueError("Planning revision kind must be idea, concept, layout, or cost")
        folder = self.paths.planning(kind)
        pattern = re.compile(rf"{kind}_r(\d+)")
        numbers = [int(match.group(1)) for path in folder.glob(f"{kind}_r*") if path.is_dir()
                   if (match := pattern.fullmatch(path.name))]
        return f"{kind}_r{max(numbers, default=0) + 1:03d}"

    def _planning_manifest(self) -> dict[str, Any]:
        path = self.paths.planning_root / "planning_manifest.json"
        return _read_json_object(path, "automation planning manifest")

    def inspect_session(self) -> dict[str, Any]:
        """Inspect session state and available artifact revisions for follow-up reads."""
        state = self._state()
        manifest_path = self.paths.root / "manifest.json"
        manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.is_file() else {})
        active = state.get("active_sequence_revision")
        planning_path = self.paths.planning_root / "planning_manifest.json"
        planning = (_read_json_object(planning_path, "automation planning manifest")
                    if planning_path.is_file() else {})
        available_parts: list[dict[str, Any]] = []
        if self.paths.enriched_bom.is_file():
            bom = _read_json_object(self.paths.enriched_bom, "BOM")
            for part in bom.get("parts", []):
                if not isinstance(part, Mapping) or not isinstance(part.get("part_id"), str):
                    continue
                analysis = part.get("part_analysis")
                analysis = analysis if isinstance(analysis, Mapping) else {}
                available_parts.append({
                    "part_id": part["part_id"],
                    "name": analysis.get("part_name_guess") or part.get("name"),
                    "quantity": part.get("quantity"),
                })

        def revision_inventory(folder: Path, prefix: str, artifact_name: str,
                               active_revision: Any) -> list[dict[str, Any]]:
            if not folder.is_dir():
                return []
            entries = []
            for revision in sorted(folder.iterdir(), key=lambda path: path.name):
                if not revision.is_dir() or not revision.name.startswith(prefix):
                    continue
                artifact_path = revision / artifact_name
                if artifact_path.is_file():
                    entries.append({
                        "revision_id": revision.name,
                        "active": revision.name == active_revision,
                    })
            return entries

        available_revisions = {
            "sequence": revision_inventory(
                self.paths.sequence_root / "revisions", "r", "assembly_sequence.json", active),
            "assembly": revision_inventory(
                self.paths.assembly_root / "revisions", "r",
                "assembly_overview.json", state.get("active_assembly_revision")),
            "monoparts": revision_inventory(
                self.paths.monopart_root / "revisions", "r",
                "bom.json", state.get("active_monoparts_revision")),
            "automation_idea": revision_inventory(
                self.paths.planning("idea"), "idea_r",
                "planning_brief.json", planning.get("active_idea_revision")),
            "detailed_step_plans": revision_inventory(
                self.paths.planning("detailed_plan"), "concept_r",
                "detailed_step_plans.json", planning.get("active_concept_revision")),
            "automation_concept": revision_inventory(
                self.paths.planning("concept"), "concept_r",
                "concept.json", planning.get("active_concept_revision")),
            "layout": revision_inventory(
                self.paths.planning("layout"), "layout_r",
                "layout.json", planning.get("active_layout_revision")),
            "cost_estimate": revision_inventory(
                self.paths.planning("cost"), "cost_r",
                "cost_estimate.json", planning.get("active_cost_revision")),
        }
        result = {"session_root": str(self.paths.root), "workflow_status": manifest.get("status", "created"),
                "active_sequence_revision": active,
                "stale": state["stale"], "feedback_events": self.feedback.count,
                "supporting_files": [path.name for path in self.supporting_files],
                "available_parts": available_parts,
                "available_revisions": available_revisions,
                "artifacts": {"assembly_overview": self.paths.assembly_overview.is_file(),
                              "bom": self.paths.enriched_bom.is_file(),
                              "sequence": bool(active and self.paths.revision(active).joinpath("assembly_sequence.json").is_file()),
                              "interaction_analysis": bool(active and self.paths.revision(active).joinpath("interaction_analysis", "interaction_analysis.json").is_file()),
                              "ffa_assessment": bool(active and self.paths.ffa(active).joinpath("ffa_assessment.json").is_file()),
                              "ffa_scores": bool(active and self.paths.ffa(active).joinpath("ffa_scores.json").is_file()),
                              "report": bool(active and self.paths.reports(active).joinpath("report.json").is_file()),
                              "automation_idea": bool((planning.get("artifacts") or {}).get("automation_idea")),
                              "detailed_step_plans": bool((planning.get("artifacts") or {}).get("detailed_step_plans")),
                              "automation_concept": bool((planning.get("artifacts") or {}).get("automation_concept")),
                              "layout": bool((planning.get("artifacts") or {}).get("layout")),
                              "cost_estimate": bool((planning.get("artifacts") or {}).get("cost_estimate"))},
                "automation_planning_status": planning.get("status"),
                "active_idea_revision": planning.get("active_idea_revision"),
                "active_concept_revision": planning.get("active_concept_revision")}
        result["available_tools"] = sorted(self.allowed_tool_catalog())
        return result

    def allowed_tool_names(self) -> set[str]:
        """Return every public workflow capability from the start of a session.

        Prerequisites are validated by each tool at execution time. Keeping
        the complete surface visible lets the agent choose the correct action
        and explain a missing prerequisite instead of inferring capability
        from the current artifact inventory.
        """
        return self.allowed_tool_catalog()

    @staticmethod
    def allowed_tool_catalog() -> set[str]:
        """Return the complete public workflow tool catalog."""
        return {name for group in TOOL_GROUPS.values() for name in group}

    def ingest_documents(self, file_names: list[str] | None = None) -> dict[str, Any]:
        """Extract text from user-authorized supporting files for context review."""
        selected_names = set(file_names or [])
        if selected_names:
            selected = [path for path in self.supporting_files
                        if path.name in selected_names or str(path) in selected_names]
            missing = sorted(selected_names - {path.name for path in selected}
                             - {str(path) for path in selected})
            if missing:
                raise ValueError(f"Files were not authorized for this session: {missing}")
        else:
            selected = list(self.supporting_files)
        if not selected:
            return {"documents": [], "warnings": ["No supporting files were provided."]}
        return self.documents.ingest(selected)

    def analyse_assembly(self) -> dict[str, Any]:
        """Create or rerun the assembly-context artifact. Use after STEP input or after a material assembly-context change; preprocessing is included. Stops at the assembly HITL checkpoint—present its name, function, and structure for correction/approval."""
        state = self._state()
        existed = self.paths.assembly_overview.exists()
        force = bool(state["stale"]["assembly"] and existed)
        result = run_assembly_review_graph(
            workflow=self.workflow, step_file=self._step(),
            user_context=self._context("global", "assembly"), force=force,
            on_preprocessed=lambda: self._announce_status(
                "STEP preprocessing is complete. Analyzing the assembly."))
        state["active_assembly_revision"] = result.get("revision_id") or self.paths.active_revision("assembly")
        mark_current(state, "assembly")
        if force or not existed:
            invalidate(state, "monoparts")
        self._write_state(state)
        return result

    def generate_engineering_powerpoint(self) -> dict[str, Any]:
        """Export the active assembly and all distinct monoparts as an editable PPTX."""
        from assembly_automation.presentation import build_report
        output = build_report(self.paths.root)
        return {"status": "complete", "artifact": str(output),
                "relative_artifact": str(output.relative_to(self.paths.root))}

    def analyse_monoparts(self, user_context: str,
                          part_ids: list[str] | None = None) -> dict[str, Any]:
        """Create or rerun intrinsic monopart analyses using only the supplied context.

        The agent must provide the context explicitly for every call. Persistent
        feedback is intentionally not loaded or merged here.
        """
        state = self._state()
        if state["stale"]["assembly"]:
            raise RuntimeError("Assembly analysis is missing or stale; analyze it first")
        existed = self.paths.enriched_bom.exists()
        force = bool(state["stale"]["monoparts"] and existed)
        targets = list(part_ids or [])
        result = run_bom_review_graph(
            workflow=self.workflow,
            user_context=user_context,
            part_ids=targets or None, force=force)
        state["active_monoparts_revision"] = result.get("revision_id") or self.paths.active_revision("monoparts")
        mark_current(state, "monoparts")
        if force or not existed:
            invalidate(state, "sequence")
        self._write_state(state)
        return result

    def edit_intermediate_artifact(self, artifact: str, patch_json: str,
                                   reason: str, raw_user_message: str,
                                   revision_id: str = "") -> dict[str, Any]:
        """Apply a JSON Merge Patch to assembly_overview, bom or sequence after validation."""
        if (self.current_user_message is not None
                and raw_user_message.strip() != self.current_user_message.strip()):
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            raise ValueError("patch_json must encode a JSON object")
        result = self.artifacts.edit(artifact, patch, reason=reason,
                                     revision_id=revision_id or None)
        self._sync_published_edit(artifact, result["path"])
        scope = {"assembly_overview": "assembly", "bom": "part", "sequence": "sequence"}[artifact]
        self.feedback.append(scope=scope, raw_user_message=raw_user_message,
                             agent_summary=reason, feedback_type="correction",
                             targets=[revision_id] if artifact == "sequence" and revision_id else [])
        state = self._state()
        if artifact == "assembly_overview":
            mark_current(state, "assembly")
            invalidate(state, "monoparts")
        elif artifact == "bom":
            mark_current(state, "monoparts")
            invalidate(state, "sequence")
        else:
            mark_current(state, "sequence")
        self._write_state(state)
        return {**result, "stale": state["stale"]}

    def edit_artifact_fields(self, artifact: str, entity_id: str, changes_json: str,
                             expected_sha256: str, reason: str, raw_user_message: str,
                             revision_id: str = "") -> dict[str, Any]:
        """Save validated descriptive field edits selected by stable entity ID."""
        if (self.current_user_message is not None
                and raw_user_message.strip() != self.current_user_message.strip()):
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        changes = json.loads(changes_json)
        if not isinstance(changes, dict):
            raise ValueError("changes_json must encode an object")
        result = self.artifacts.edit_fields(
            artifact, entity_id=entity_id, changes=changes,
            expected_sha256=expected_sha256, reason=reason,
            revision_id=revision_id or None)
        self._sync_published_edit(artifact, result["path"])
        scope = {"assembly_overview": "assembly", "bom": "part", "sequence": "sequence"}[artifact]
        self.feedback.append(scope=scope, raw_user_message=raw_user_message,
                             agent_summary=reason, feedback_type="correction",
                             targets=[entity_id])
        state = self._state()
        if artifact == "assembly_overview":
            mark_current(state, "assembly")
            invalidate(state, "monoparts")
        elif artifact == "bom":
            mark_current(state, "monoparts")
            invalidate(state, "sequence")
        else:
            mark_current(state, "sequence")
        self._write_state(state)
        return {**result, "stale": state["stale"]}

    def change_artifact(self, artifact: str, change: str,
                        revision_id: str = "") -> dict[str, Any]:
        """Rewrite one named JSON artifact from a natural-language correction.

        Name the artifact explicitly: assembly_context, BOM, sequence,
        interaction_analysis, ffa_assessment, ffa_scores, report,
        automation_idea, detailed_step_plans, automation_concept, layout, or
        cost_estimate. The rewrite LLM receives the complete artifact and must
        return a complete replacement with every affected location updated.
        The replacement is schema-validated, backed up, and atomically saved.
        Use revision_id only when the user explicitly requests a non-active
        revision. Future planning preferences belong in the dedicated planning
        or revision tool rather than this correction tool.
        """
        if self.artifact_change_planner is None:
            raise RuntimeError("The artifact rewriter is not configured")
        resolved = resolve_target(self.artifacts, artifact, revision_id)
        planned = self.artifact_change_planner.rewrite(resolved, change)
        summary = str(planned["rewrite"].get("summary")
                      or "Applied user-requested artifact correction")
        result = self.artifacts.replace(
            resolved.artifact, planned["artifact"],
            expected_sha256=resolved.expected_sha256, reason=summary,
            revision_id=resolved.revision_id)
        self._sync_published_edit(resolved.artifact, result["path"])
        state = self._state()
        if resolved.artifact == "assembly_overview":
            mark_current(state, "assembly")
            invalidate(state, "monoparts")
        elif resolved.artifact == "bom":
            mark_current(state, "monoparts")
            invalidate(state, "sequence")
        elif resolved.artifact == "sequence":
            mark_current(state, "sequence")
        elif resolved.artifact == "interaction_analysis":
            invalidate(state, "interaction")
        elif resolved.artifact in {"ffa_assessment", "ffa_scores"}:
            invalidate(state, "ffa_report")
        elif resolved.artifact == "report":
            mark_current(state, "final")
        self._write_state(state)

        rendering = None
        if resolved.artifact == "layout":
            from assembly_automation.workflows.nodes.layout_planner.renderer import render_layout
            rendering = render_layout(planned["artifact"], resolved.path.with_name("layout.svg"))
        record = {
            "input": planned["input"],
            "rewrite": planned["rewrite"],
            "execution": planned["execution"],
            "application": {"artifact": resolved.artifact,
                            "sha256": result["sha256"]},
        }
        run_record_path = write_run_record(
            result["path"], "artifact_change", record)
        return {**result, "target": resolved.label,
                "changed_locations": planned["rewrite"]["changed_locations"],
                "summary": summary, "rendering": rendering,
                "stale": state["stale"], "run_record_path": run_record_path}

    def _next_revision(self) -> str:
        root = self.paths.sequence_root / "revisions"
        numbers = [int(match.group(1)) for path in root.glob("r*") if path.is_dir()
                   if (match := re.fullmatch(r"r(\d+)", path.name))]
        return f"r{max(numbers, default=0) + 1:03d}"

    def generate_sequence(self, sequence_constraints: str = "") -> dict[str, Any]:
        """Generate a sequence from the available assembly and BOM artifacts.

        Recorded stale flags are informational and never block a workflow
        action. The concrete input files remain the source of truth.
        """
        state = self._state()
        if not self.paths.assembly_overview.is_file() or not self.paths.enriched_bom.is_file():
            raise RuntimeError("Assembly overview and BOM files are required before sequence generation")
        if state.get("active_sequence_revision") and not state["stale"]["sequence"]:
            raise RuntimeError("A current sequence already exists; approve it or use revise_sequence")
        revision = self._next_revision()
        result = run_sequence_review_graph(
            workflow=self.workflow, revision_id=revision, mode="generate",
            user_context=self._context("global", "assembly", "part", "sequence"),
            sequence_constraints=sequence_constraints)
        state["active_sequence_revision"] = revision
        mark_current(state, "sequence")
        self._write_state(state)
        return result

    def revise_sequence(self, raw_user_message: str, feedback_summary: str) -> dict[str, Any]:
        """Create a replacement sequence from explicit sequence-review feedback. Use for requested sequence changes, not simple approval; raw_user_message must match the current user turn exactly."""
        if (self.current_user_message is not None
                and raw_user_message.strip() != self.current_user_message.strip()):
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        self.feedback.append(scope="sequence", raw_user_message=raw_user_message,
                             agent_summary=feedback_summary, feedback_type="correction")
        state = self._state()
        if not self.paths.assembly_overview.is_file() or not self.paths.enriched_bom.is_file():
            raise RuntimeError("Assembly overview and BOM files are required before sequence revision")
        revisions = sorted(path for path in self.paths.sequence_root.joinpath("revisions").glob("r*")
                           if path.joinpath("assembly_sequence.json").is_file())
        if not revisions:
            raise RuntimeError("Generate an initial sequence before requesting a revision")
        initial = revisions[0] / "assembly_sequence.json"
        revision = self._next_revision()
        result = run_sequence_review_graph(
            workflow=self.workflow, revision_id=revision, mode="revise", initial_sequence=initial,
            user_context=self._context("global", "assembly", "part"),
            user_feedback_summary=self._context("sequence"))
        state["active_sequence_revision"] = revision
        mark_current(state, "sequence")
        self._write_state(state)
        return result

    def _archive_path(self, path: Path, label: str) -> str | None:
        if not path.exists():
            return None
        root = self.paths.history_root / "artifact_edits" / label
        root.mkdir(parents=True, exist_ok=True)
        index = 1
        while root.joinpath(f"run_{index:03d}").exists():
            index += 1
        target = root / f"run_{index:03d}"
        path.replace(target)
        return str(target)

    def ffa_evaluation(self) -> dict[str, Any]:
        """Generate or explicitly rerun the final FfA report after the user has accepted the current sequence. The agent must infer acceptance from dialogue; never use this merely because the user discusses an existing report."""
        state = self._state()
        revision = state.get("active_sequence_revision")
        sequence_path = self.paths.revision(revision) / "assembly_sequence.json" if revision else None
        if not revision or sequence_path is None or not sequence_path.is_file():
            raise RuntimeError("An existing sequence file is required before FfA evaluation")
        archived = []
        if state["stale"]["final"]:
            paths = [self.paths.revision(revision) / "interaction_analysis",
                     self.paths.ffa(revision), self.paths.reports(revision)]
            if state["stale"]["renderings"]:
                paths.insert(0, self.paths.revision(revision) / "renderings")
            for path in paths:
                saved = self._archive_path(path, f"final_{revision}_{path.name}")
                if saved:
                    archived.append(saved)
        result = run_final_assessment_graph(
            workflow=self.workflow,
            revision_id=revision,
            approved_sequence=self.paths.revision(revision) / "assembly_sequence.json",
            user_context=self._context("global", "assembly", "part", "sequence",
                                       "interaction", "ffa_report"))
        mark_current(state, "final")
        self._write_state(state)
        return {**result, "archived": archived}

    def automation_concept_idea_generator(self, raw_user_message: str,
                                          planning_instruction: str,
                                          feedback_summary: str = "") -> dict[str, Any]:
        """Generate or revise the global automation idea from the available assessment evidence.

        Planning premises do not require upstream artifacts to be marked
        ``current``. Existing report and assessment files remain valid evidence
        for planning even when later context has been recorded.
        """
        if self.current_user_message is not None and raw_user_message.strip() != self.current_user_message.strip():
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        state = self._state()
        active = state.get("active_sequence_revision")
        report = self.paths.reports(active).joinpath("report.json") if active else None
        if (report is None or not report.is_file()
                or not self.paths.root.joinpath("manifest.json").is_file()):
            raise RuntimeError(
                "Automation planning requires an existing FfA report for assessment evidence")
        instruction = planning_instruction.strip()
        if not instruction:
            raise ValueError("planning_instruction must not be empty")
        planning_manifest_path = self.paths.planning_root / "planning_manifest.json"
        previous = None
        if planning_manifest_path.is_file():
            manifest = _read_json_object(planning_manifest_path, "automation planning manifest")
            relative = (manifest.get("artifacts") or {}).get("automation_idea")
            if isinstance(relative, str) and (self.paths.root / relative).is_file():
                previous = _read_json_object(self.paths.root / relative, "previous automation idea")
        if feedback_summary.strip():
            instruction += ("\n\nRevise the previous global idea using this mandatory user feedback:\n"
                            + feedback_summary.strip())
            if previous:
                instruction += "\n\nPrevious global idea:\n" + json.dumps(previous, ensure_ascii=False)
        event = self.feedback.append(
            scope="automation_idea", raw_user_message=raw_user_message,
            agent_summary=feedback_summary.strip() or planning_instruction.strip(),
            feedback_type="correction" if previous else "requirement")
        revision = self._next_planning_revision("idea")
        response = self._planning().create_idea(instruction, revision_id=revision)
        return {"status": "awaiting_idea_review", "revision_id": revision,
                "artifact": response["artifact"], "feedback": event}

    def automation_concept_planner(self) -> dict[str, Any]:
        """Plan every assembly step in parallel from the active automation idea and consolidate the equipment requirements. Use when the conversation calls for detailed planning; do not create an approval checkpoint."""
        manifest = self._planning_manifest()
        relative = (manifest.get("artifacts") or {}).get("automation_idea")
        if not isinstance(relative, str):
            raise RuntimeError("Generate an automation idea before detailed concept planning")
        idea_path = self.paths.root / relative
        revision = self._next_planning_revision("concept")
        response = run_automation_concept_graph(
            workflow=self._planning(), idea_path=idea_path, revision_id=revision)
        return {"status": "awaiting_concept_review", "revision_id": revision,
                "artifact": response["artifact"]}

    def revise_automation_concept(self, raw_user_message: str,
                                  feedback_summary: str) -> dict[str, Any]:
        """Apply bounded feedback to the consolidated equipment list only. For global policy, human-role, material-flow, or technology-direction changes, revise the automation idea instead."""
        if self.current_user_message is not None and raw_user_message.strip() != self.current_user_message.strip():
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        if not feedback_summary.strip():
            raise ValueError("feedback_summary must not be empty")
        event = self.feedback.append(scope="automation_concept",
                                     raw_user_message=raw_user_message,
                                     agent_summary=feedback_summary,
                                     feedback_type="correction")
        revision = self._next_planning_revision("concept")
        response = self._planning().revise_concept(
            feedback=feedback_summary, revision_id=revision)
        return {"status": "awaiting_concept_review", "revision_id": revision,
                "artifact": response["artifact"], "feedback": event}

    def layout_planner(self, raw_user_message: str, layout_instruction: str) -> dict[str, Any]:
        """Create a coordinate list and deterministic equipment layout after an automation concept exists. Use for new/global placement preferences; the result stops for layout review."""
        if self.current_user_message is not None and raw_user_message.strip() != self.current_user_message.strip():
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        if not layout_instruction.strip():
            raise ValueError("layout_instruction must not be empty")
        manifest = self._planning_manifest()
        relative = (manifest.get("artifacts") or {}).get("automation_concept")
        if not isinstance(relative, str):
            raise RuntimeError("Generate an automation concept before layout planning")
        event = self.feedback.append(scope="automation_concept", raw_user_message=raw_user_message,
                                     agent_summary=layout_instruction,
                                     feedback_type="requirement")
        revision = self._next_planning_revision("layout")
        response = self._planning().create_layout(
            concept_path=self.paths.root / relative, layout_context=layout_instruction,
            revision_id=revision)
        return {"status": "awaiting_layout_review", "revision_id": revision,
                "artifact": response["artifact"], "rendering": response["rendering"],
                "feedback": event}

    def revise_layout(self, raw_user_message: str, changes_json: str) -> dict[str, Any]:
        """Apply minor existing-equipment class/x/y changes and rerun only deterministic layout rendering. Do not add, remove, or rename equipment with this tool."""
        if self.current_user_message is not None and raw_user_message.strip() != self.current_user_message.strip():
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        changes = json.loads(changes_json)
        if not isinstance(changes, list) or not changes or any(not isinstance(item, dict) for item in changes):
            raise ValueError("changes_json must encode a nonempty list of layout changes")
        manifest = self._planning_manifest()
        artifacts = manifest.get("artifacts") or {}
        layout_relative = artifacts.get("layout")
        concept_relative = artifacts.get("automation_concept")
        if not isinstance(layout_relative, str) or not isinstance(concept_relative, str):
            raise RuntimeError("Generate a layout and automation concept before revising the layout")
        revision = self._next_planning_revision("layout")
        response = self._planning().revise_layout(
            layout_path=self.paths.root / layout_relative,
            concept_path=self.paths.root / concept_relative,
            changes=changes, revision_id=revision)
        event = self.feedback.append(scope="automation_concept", raw_user_message=raw_user_message,
                                     agent_summary=f"Applied minor layout changes: {changes_json}",
                                     feedback_type="correction")
        return {"status": "awaiting_layout_review", "revision_id": revision,
                "artifact": response["artifact"], "rendering": response["rendering"],
                "feedback": event}

    def cost_planner(self, raw_user_message: str, costing_instruction: str = "") -> dict[str, Any]:
        """Create a catalogue-backed investment estimate after both concept and layout exist. Pass commercial assumptions only; deterministic code supplies prices and totals, and unpriced equipment must remain visible."""
        if self.current_user_message is not None and raw_user_message.strip() != self.current_user_message.strip():
            raise ValueError("raw_user_message must reproduce the user's current message exactly")
        manifest = self._planning_manifest()
        artifacts = manifest.get("artifacts") or {}
        concept = artifacts.get("automation_concept")
        layout = artifacts.get("layout")
        if not isinstance(concept, str) or not isinstance(layout, str):
            raise RuntimeError("Generate the automation concept and layout before cost planning")
        revision = self._next_planning_revision("cost")
        response = self._planning().create_cost_estimate(
            concept_path=self.paths.root / concept, layout_path=self.paths.root / layout,
            cost_context=costing_instruction.strip(), revision_id=revision)
        return {"status": "awaiting_cost_review", "revision_id": revision,
                "artifact": response["artifact"], "result": response["result"]}

    def _read_automation_artifact(self, artifact: str, json_path: str = "") -> dict[str, Any]:
        """Read the active automation idea, detailed step plans, or consolidated concept."""
        if artifact not in {"automation_idea", "detailed_step_plans", "automation_concept", "layout", "cost_estimate"}:
            raise ValueError("Unknown automation artifact")
        manifest = self._planning_manifest()
        relative = (manifest.get("artifacts") or {}).get(artifact)
        if not isinstance(relative, str):
            raise FileNotFoundError(f"Automation artifact is not available: {artifact}")
        path = (self.paths.root / relative).resolve()
        path.relative_to(self.paths.root.resolve())
        value: Any = _read_json_object(path, artifact)
        for segment in [item for item in json_path.split(".") if item]:
            if isinstance(value, dict) and segment in value:
                value = value[segment]
            else:
                raise ValueError(f"JSON path does not exist: {json_path}")
        return {"artifact": artifact, "json_path": json_path, "data": value}

    def _planning_revision_path(self, artifact: str, revision_id: str) -> Path:
        folders = {
            "automation_idea": ("idea", "planning_brief.json"),
            "detailed_step_plans": ("detailed_plan", "detailed_step_plans.json"),
            "automation_concept": ("concept", "concept.json"),
            "layout": ("layout", "layout.json"),
            "cost_estimate": ("cost", "cost_estimate.json"),
        }
        if artifact not in folders:
            raise ValueError(f"Unsupported planning artifact: {artifact}")
        folder, filename = folders[artifact]
        path = (self.paths.planning(folder) / revision_id / filename).resolve()
        path.relative_to(self.paths.root.resolve())
        if not path.is_file():
            raise FileNotFoundError(
                f"Unknown {artifact} revision {revision_id!r}; "
                f"use inspect_session to see available revisions")
        return path

    def _available_sequence_revisions(self) -> list[str]:
        return [item["revision_id"] for item in self.inspect_session()["available_revisions"]["sequence"]]

    def _read_revision_artifact(self, artifact: str, revision_id: str = "") -> tuple[Path, Any, str]:
        if artifact in {"sequence", "interaction_analysis", "ffa_assessment",
                        "ffa_scores", "report"}:
            revision = revision_id or str(self._state().get("active_sequence_revision") or "")
            if not revision:
                raise FileNotFoundError(f"No active {artifact} revision is available")
            path = self.artifacts.resolve(artifact, revision_id=revision)
            if not path.is_file():
                available = self._available_sequence_revisions()
                raise FileNotFoundError(
                    f"Unknown {artifact} revision {revision!r}; available revisions: {available}")
            return path, _read_json_object(path, artifact), revision
        revision = revision_id
        if not revision:
            planning = self._planning_manifest()
            revision = str(planning.get({
                "automation_idea": "active_idea_revision",
                "detailed_step_plans": "active_concept_revision",
                "automation_concept": "active_concept_revision",
                "layout": "active_layout_revision",
                "cost_estimate": "active_cost_revision",
            }[artifact]) or "")
        if not revision:
            raise FileNotFoundError(f"No active {artifact} revision is available")
        path = self._planning_revision_path(artifact, revision)
        return path, _read_json_object(path, artifact), revision

    @staticmethod
    def _selector(request: str, identifier: str) -> tuple[str, str, str]:
        parts = [item.strip() for item in identifier.split(":", 1)]
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"{request} requires '<revision>:<item>', for example "
                f"{request} 'r002:step_003'")
        return parts[0], parts[1], identifier

    def read_artifact(self, request: str, identifier: str = "") -> dict[str, Any]:
        """Read a created artifact using a small, path-free request vocabulary.

        Versioned requests accept an optional revision ID. Entity requests use
        ``<revision>:<item>`` selectors: ``sequence_step``, ``detailed_plan``,
        ``layout_item``, and ``report_finding``.
        """
        requested = request.strip()
        normalized = requested.lower()
        if normalized == "assembly_context":
            artifact = "assembly_overview"
            revision_id = identifier.strip() or self.paths.active_revision("assembly")
            path = self.artifacts.resolve(artifact, revision_id=revision_id)
            value = _read_json_object(path, "assembly context")
        elif normalized == "bom":
            artifact = "bom"
            revision_id = identifier.strip() or self.paths.active_revision("monoparts")
            path = self.artifacts.resolve(artifact, revision_id=revision_id)
            value = _read_json_object(path, "BOM")
        elif normalized == "part":
            part_id = identifier.strip()
            if not part_id:
                raise ValueError("A part ID is required, for example read_artifact('part', 'part_001')")
            bom = _read_json_object(
                self.artifacts.resolve("bom", revision_id=self.paths.active_revision("monoparts")),
                "BOM")
            matches = [part for part in bom.get("parts", [])
                       if isinstance(part, Mapping) and part.get("part_id") == part_id]
            if len(matches) != 1:
                available = [str(part.get("part_id")) for part in bom.get("parts", [])
                             if isinstance(part, Mapping) and part.get("part_id")]
                raise ValueError(f"Unknown part ID {part_id!r}; available IDs: {available}")
            return {"request": "part", "identifier": part_id, "data": matches[0]}
        elif normalized in {"sequence", "interaction_analysis", "ffa_assessment",
                            "ffa_scores", "report"}:
            artifact = normalized
            path, value, revision_id = self._read_revision_artifact(
                artifact, identifier.strip())
        elif normalized in {"automation_idea", "detailed_step_plans",
                            "automation_concept", "layout", "cost_estimate"}:
            path, value, revision_id = self._read_revision_artifact(
                normalized, identifier.strip())
        elif normalized == "sequence_step":
            revision, item, selector = self._selector(normalized, identifier)
            path, sequence, _ = self._read_revision_artifact("sequence", revision)
            raw_id = item.removeprefix("step_")
            if not raw_id.isdigit():
                raise ValueError(f"Invalid sequence step selector {item!r}; use step_003")
            step_id = int(raw_id)
            steps = sequence.get("steps") if isinstance(sequence, dict) else None
            matches = [step for step in (steps or [])
                       if isinstance(step, Mapping) and step.get("step_id") == step_id]
            if len(matches) != 1:
                available = [step.get("step_id") for step in (steps or [])
                             if isinstance(step, Mapping)]
                raise ValueError(f"Unknown sequence step {item!r}; available steps: {available}")
            return {"request": normalized, "identifier": selector,
                    "revision_id": revision, "data": matches[0]}
        elif normalized == "detailed_plan":
            revision, item, selector = self._selector(normalized, identifier)
            path, plans, _ = self._read_revision_artifact("detailed_step_plans", revision)
            raw_id = item.removeprefix("step_")
            if not raw_id.isdigit():
                raise ValueError(f"Invalid detailed plan selector {item!r}; use step_003")
            step_id = int(raw_id)
            steps = plans.get("steps") if isinstance(plans, dict) else None
            matches = [step for step in (steps or [])
                       if isinstance(step, Mapping) and step.get("step_id") == step_id]
            if len(matches) != 1:
                available = [step.get("step_id") for step in (steps or [])
                             if isinstance(step, Mapping)]
                raise ValueError(f"Unknown detailed plan {item!r}; available steps: {available}")
            return {"request": normalized, "identifier": selector,
                    "revision_id": revision, "data": matches[0]}
        elif normalized == "layout_item":
            revision, item, selector = self._selector(normalized, identifier)
            path, layout, _ = self._read_revision_artifact("layout", revision)
            equipment = layout.get("equipment") if isinstance(layout, dict) else None
            matches = [entry for entry in (equipment or [])
                       if isinstance(entry, Mapping) and str(entry.get("name")) == item]
            if len(matches) != 1:
                available = [str(entry.get("name")) for entry in (equipment or [])
                             if isinstance(entry, Mapping) and entry.get("name")]
                raise ValueError(f"Unknown layout item {item!r}; available items: {available}")
            return {"request": normalized, "identifier": selector,
                    "revision_id": revision, "data": matches[0]}
        elif normalized == "report_finding":
            revision, item, selector = self._selector(normalized, identifier)
            path, report, _ = self._read_revision_artifact("report", revision)
            findings = report.get("key_findings") if isinstance(report, dict) else None
            matches = [finding for finding in (findings or [])
                       if isinstance(finding, Mapping)
                       and str(finding.get("finding_id") or finding.get("id")) == item]
            if len(matches) != 1:
                available = [str(finding.get("finding_id") or finding.get("id"))
                             for finding in (findings or []) if isinstance(finding, Mapping)]
                raise ValueError(f"Unknown report finding {item!r}; available findings: {available}")
            return {"request": normalized, "identifier": selector,
                    "revision_id": revision, "data": matches[0]}
        else:
            supported = ("assembly_context, BOM, part + exact part ID, sequence, "
                         "interaction_analysis, ffa_assessment, ffa_scores, report, "
                         "sequence_step, detailed_plan, report_finding, automation_idea, "
                         "detailed_step_plans, automation_concept, layout_item, layout, "
                         "cost_estimate")
            raise ValueError(f"Unknown artifact request {request!r}; supported: {supported}")
        return {"request": normalized, "identifier": identifier or None,
                "revision_id": revision_id if normalized not in {"assembly_context", "bom"} else None,
                "data": value, "sha256": self.artifacts.content_hash(path)}

    def summarize_parts(self, part_ids: list[str] | None = None, page: int = 1,
                        page_size: int = 25) -> dict[str, Any]:
        """Read bounded intrinsic summaries for selected or paginated unique parts."""
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("page must be positive and page_size must be between 1 and 100")
        bom = _read_json_object(self.paths.enriched_bom, "enriched BOM")
        requested = set(part_ids or [])
        records = []
        for part in bom.get("parts", []):
            if not isinstance(part, Mapping) or not isinstance(part.get("part_id"), str):
                continue
            if requested and part["part_id"] not in requested:
                continue
            analysis = part.get("part_analysis") if isinstance(part.get("part_analysis"), Mapping) else {}
            records.append({"part_id": part["part_id"],
                            "name": analysis.get("part_name_guess") or part.get("name"),
                            "quantity": part.get("quantity"),
                            "intrinsic_summary": analysis.get("intrinsic_summary")})
        if requested:
            missing = sorted(requested - {item["part_id"] for item in records})
            if missing:
                raise ValueError(f"Unknown part IDs: {missing}")
            selected = records
        else:
            start = (page - 1) * page_size
            selected = records[start:start + page_size]
        return {"total": len(records), "page": page, "page_size": page_size,
                "parts": selected, "has_more": page * page_size < len(records)}

    def read_part(self, part_id: str) -> dict[str, Any]:
        """Read one complete enriched part record by stable part ID."""
        bom = _read_json_object(self.paths.enriched_bom, "enriched BOM")
        matches = [part for part in bom.get("parts", [])
                   if isinstance(part, Mapping) and part.get("part_id") == part_id]
        if len(matches) != 1:
            raise ValueError(f"Expected one part {part_id!r}, found {len(matches)}")
        return {"part": matches[0]}

    def as_langchain_tools(self, names: list[str] | None = None) -> list[Any]:
        """Create LangChain tools from the allowlisted bound methods."""
        from langchain.tools import tool

        public_names = tuple(name for group in TOOL_GROUPS.values() for name in group)
        available = {name: getattr(self, name) for name in (*public_names, *INTERNAL_TOOL_NAMES)}
        selected = list(public_names) if names is None else names
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise ValueError(f"Unknown user-agent tools: {unknown}")

        def wrapped(name: str, function: Any) -> Any:
            @wraps(function)
            def invoke(*args: Any, **kwargs: Any) -> Any:
                result = function(*args, **kwargs)
                if isinstance(result, Mapping):
                    result = dict(result)
                    result["agent_message"] = _agent_tool_message(name, result)
                return result
            return invoke

        return [tool(name)(wrapped(name, available[name])) for name in selected]
