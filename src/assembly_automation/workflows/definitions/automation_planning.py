"""Post-FFA workflow for a reviewable, station-independent automation concept."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .app_v3 import WorkflowPaths


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class AutomationPlanningNodeRegistry:
    automation_idea: Callable[..., dict[str, Any]]
    step_planner_detailed: Callable[..., dict[str, Any]]
    automation_concept_synthesis: Callable[..., dict[str, Any]]
    layout_planner: Callable[..., dict[str, Any]] | None = None
    cost_planner: Callable[..., dict[str, Any]] | None = None


def default_node_registry() -> AutomationPlanningNodeRegistry:
    from assembly_automation.workflows.nodes.automation_concept import run_automation_concept_synthesis
    from assembly_automation.workflows.nodes.automation_idea import run_automation_idea
    from assembly_automation.workflows.nodes.step_planner_detailed import run_step_planner_detailed
    from assembly_automation.workflows.nodes.layout_planner import run_layout_planner
    from assembly_automation.workflows.nodes.cost_planner import run_cost_planner
    return AutomationPlanningNodeRegistry(run_automation_idea, run_step_planner_detailed,
                                           run_automation_concept_synthesis, run_layout_planner,
                                           run_cost_planner)


class AutomationPlanningWorkflow:
    """Consume published assessment artifacts without modifying their manifest."""

    REQUIRED = ("assembly_overview", "enriched_bom", "assembly_sequence",
                "interaction_analysis", "ffa_assessment", "ffa_scores", "report")

    def __init__(self, *, session_root: str | Path, settings: Mapping[str, Any],
                 output_root: str | Path | None = None,
                 nodes: AutomationPlanningNodeRegistry | None = None):
        self.session_root = Path(session_root).resolve()
        self.output_root = Path(output_root).resolve() if output_root else self.session_root
        self.settings = dict(settings)
        self.node_settings = self.settings.get("nodes")
        self.llm_profiles = (self.settings.get("llms") or {}).get("profiles")
        if not isinstance(self.node_settings, Mapping) or not isinstance(self.llm_profiles, Mapping):
            raise ValueError("Workflow settings require nodes and llms.profiles")
        self.nodes = nodes or default_node_registry()
        self.source_manifest = _read(self.session_root / "manifest.json")
        published = self.source_manifest.get("artifacts")
        if not isinstance(published, dict):
            raise ValueError("Source session manifest has no artifacts mapping")
        missing = [key for key in self.REQUIRED if key not in published]
        if missing:
            raise ValueError(f"Source session is missing required artifacts: {missing}")
        self.artifacts = {key: self.session_root / published[key] for key in self.REQUIRED}
        absent = [key for key, path in self.artifacts.items() if not path.is_file()]
        if absent:
            raise ValueError(f"Published source artifacts do not exist: {absent}")
        self.artifacts["ffa_report"] = self.artifacts["report"]
        self.paths = WorkflowPaths(self.output_root)
        self.planning_root = self.paths.planning_root
        self.manifest_path = self.planning_root / "planning_manifest.json"

    def _manifest(self, *, status: str, **values: Any) -> None:
        current = _read(self.manifest_path) if self.manifest_path.exists() else {
            "workflow": "automation_concept_planning",
            "source_session": str(self.session_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        current.update(values)
        current["status"] = status
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write(self.manifest_path, current)
        registry_path = self.output_root / "artifact_registry.json"
        registry = _read(registry_path) if registry_path.is_file() else {
            "schema_version": 1, "active": {}, "revisions": {}}
        for key, revision_key in (
            ("automation_idea", "active_idea_revision"),
            ("automation_concept", "active_concept_revision"),
            ("layout", "active_layout_revision"),
            ("cost_estimate", "active_cost_revision"),
        ):
            revision = current.get(revision_key)
            if isinstance(revision, str):
                registry.setdefault("active", {})[key] = revision
                revisions = registry.setdefault("revisions", {}).setdefault(key, [])
                if revision not in revisions:
                    revisions.append(revision)
        _write(registry_path, registry)

    def create_idea(self, planning_instruction: str, *, revision_id: str = "idea_r001") -> dict[str, Any]:
        output = self.paths.planning("idea") / revision_id / "planning_brief.json"
        self._manifest(status="planning_idea", active_idea_revision=revision_id)
        response = self.nodes.automation_idea(
            artifacts=self.artifacts, settings=self.node_settings["automation_idea"],
            llm_profiles=self.llm_profiles, context={"planning_instruction": planning_instruction},
            output_path=output)
        self._manifest(status="awaiting_idea_review", active_idea_revision=revision_id,
                       artifacts={"automation_idea": str(output.relative_to(self.output_root))})
        return response

    def build_concept(self, *, idea_path: str | Path,
                      revision_id: str = "concept_r001") -> dict[str, Any]:
        idea = Path(idea_path).resolve()
        sequence = _read(self.artifacts["assembly_sequence"])
        sequence = sequence.get("sequence", sequence)
        steps = sequence.get("steps") if isinstance(sequence, dict) else None
        if not isinstance(steps, list) or not steps:
            raise ValueError("Assembly sequence has no steps")
        step_ids = [step.get("step_id") for step in steps]
        if any(type(step_id) is not int for step_id in step_ids):
            raise ValueError("Every assembly step requires an integer step_id")

        settings = self.node_settings["step_planner_detailed"]
        fanout = settings.get("fanout", {})
        max_workers = int(fanout.get("max_workers", 6))
        step_dir = self.paths.planning("detailed_plan") / revision_id / "steps"
        results: dict[int, dict[str, Any]] = {}

        def run(step_id: int) -> tuple[int, dict[str, Any]]:
            response = self.nodes.step_planner_detailed(
                step_id=step_id, artifacts={**self.artifacts, "automation_idea": idea},
                settings=settings, llm_profiles=self.llm_profiles,
                output_path=step_dir / f"step_{step_id:03d}.json")
            if response.get("status") != "complete":
                raise RuntimeError(f"Process planning failed for step {step_id}")
            return step_id, response["result"]

        self._manifest(status="planning_steps", active_concept_revision=revision_id)
        if fanout.get("parallel", True):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run, step_id) for step_id in step_ids]
                for future in as_completed(futures):
                    step_id, result = future.result()
                    results[step_id] = result
        else:
            for step_id in step_ids:
                key, result = run(step_id)
                results[key] = result

        aggregate = self.paths.planning("detailed_plan") / revision_id / "detailed_step_plans.json"
        _write(aggregate, {"steps": [results[step_id] for step_id in step_ids]})
        concept = self.paths.planning("concept") / revision_id / "concept.json"
        response = self.nodes.automation_concept_synthesis(
            artifacts={**self.artifacts, "automation_idea": idea,
                       "detailed_step_plans": aggregate},
            settings=self.node_settings["automation_concept_synthesis"],
            llm_profiles=self.llm_profiles, output_path=concept)
        self._manifest(status="awaiting_concept_review", active_concept_revision=revision_id,
                       artifacts={"automation_idea": str(idea.relative_to(self.output_root)),
                                  "detailed_step_plans": str(aggregate.relative_to(self.output_root)),
                                  "automation_concept": str(concept.relative_to(self.output_root))})
        return response

    def revise_concept(self, *, feedback: str,
                       revision_id: str = "concept_r002") -> dict[str, Any]:
        """Revise consolidation only, retaining the accepted idea and detailed plans."""
        if not isinstance(feedback, str) or not feedback.strip():
            raise ValueError("Concept revision requires nonempty user feedback")
        manifest = _read(self.manifest_path)
        published = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
        required = ("automation_idea", "detailed_step_plans", "automation_concept")
        missing = [key for key in required if key not in published]
        if missing:
            raise RuntimeError(f"Cannot revise concept; planning artifacts are missing: {missing}")
        resolved = {key: (self.output_root / published[key]).resolve() for key in required}
        concept = self.paths.planning("concept") / revision_id / "concept.json"
        response = self.nodes.automation_concept_synthesis(
            artifacts={**self.artifacts,
                       "automation_idea": resolved["automation_idea"],
                       "detailed_step_plans": resolved["detailed_step_plans"],
                       "previous_automation_concept": resolved["automation_concept"]},
            settings=self.node_settings["automation_concept_synthesis"],
            llm_profiles=self.llm_profiles, context={"concept_feedback": feedback},
            output_path=concept)
        self._manifest(status="awaiting_concept_review", active_concept_revision=revision_id,
                       artifacts={"automation_idea": published["automation_idea"],
                                  "detailed_step_plans": published["detailed_step_plans"],
                                  "automation_concept": str(concept.relative_to(self.output_root))})
        return response

    def create_layout(self, *, concept_path: str | Path, layout_context: str,
                      revision_id: str = "layout_r001") -> dict[str, Any]:
        """Place concept equipment with an LLM, then render it deterministically."""
        concept = Path(concept_path).resolve(strict=True)
        concept.relative_to(self.output_root.resolve())
        if self.nodes.layout_planner is None:
            raise RuntimeError("The layout planner node is not configured")
        output = self.paths.planning("layout") / revision_id / "layout.json"
        response = self.nodes.layout_planner(
            artifacts={**self.artifacts, "automation_concept": concept},
            settings=self.node_settings["layout_planner"], llm_profiles=self.llm_profiles,
            context={"layout_context": layout_context}, output_path=output)
        current = _read(self.manifest_path)
        published = dict(current.get("artifacts") or {})
        published.update({"layout": str(output.relative_to(self.output_root)),
                          "layout_rendering": str(Path(response["rendering"]).relative_to(self.output_root))})
        self._manifest(status="awaiting_layout_review", active_layout_revision=revision_id,
                       artifacts=published)
        return response

    def revise_layout(self, *, layout_path: str | Path, concept_path: str | Path,
                      changes: list[Mapping[str, Any]], revision_id: str) -> dict[str, Any]:
        """Apply bounded coordinate/class/size edits and rerender without another LLM call."""
        paths = getattr(self, "paths", WorkflowPaths(self.output_root))
        from assembly_automation.workflows.nodes.layout_planner.node import _validate_coverage
        from assembly_automation.workflows.nodes.layout_planner.renderer import render_layout
        from assembly_automation.workflows.nodes.layout_planner.structured_output import EquipmentLayout

        current = _read(Path(layout_path).resolve(strict=True))
        rows = current.get("equipment")
        if not isinstance(rows, list):
            raise ValueError("Current layout has no equipment list")
        by_name = {str(row.get("name")): dict(row) for row in rows if isinstance(row, dict)}
        changed_names: set[str] = set()
        for change in changes:
            name = str(change.get("name") or "").strip()
            if name not in by_name:
                raise ValueError(f"Unknown layout equipment name: {name}")
            if name in changed_names:
                raise ValueError(f"Duplicate layout change for equipment: {name}")
            changed_names.add(name)
            fields = set(change) - {"name"}
            if not fields or not fields <= {"class", "x", "y", "size"}:
                raise ValueError("Each layout change must set class, x, y, and/or size only")
            by_name[name].update({key: change[key] for key in fields})
        candidate = EquipmentLayout.model_validate(
            {"equipment": [by_name[str(row["name"])] for row in rows]}).model_dump()
        _validate_coverage(concept_path, candidate)
        output = paths.planning("layout") / revision_id / "layout.json"
        _write(output, candidate)
        rendering = render_layout(candidate, output.with_name("layout.svg"))
        manifest = _read(self.manifest_path)
        published = dict(manifest.get("artifacts") or {})
        published.update({"layout": str(output.relative_to(self.output_root)),
                          "layout_rendering": str(Path(rendering).relative_to(self.output_root))})
        self._manifest(status="awaiting_layout_review", active_layout_revision=revision_id,
                       artifacts=published)
        return {"status": "complete", "artifact": str(output), "rendering": rendering,
                "result": candidate}

    def create_cost_estimate(self, *, concept_path: str | Path, layout_path: str | Path,
                             cost_context: str, revision_id: str = "cost_r001") -> dict[str, Any]:
        if self.nodes.cost_planner is None:
            raise RuntimeError("The cost planner node is not configured")
        output = self.paths.planning("cost") / revision_id / "cost_estimate.json"
        settings = dict(self.node_settings["cost_planner"])
        catalogue = Path(str(settings.get("catalogue_path", "")))
        if not catalogue.is_absolute():
            settings["catalogue_path"] = str((self.session_root.parents[2] / catalogue).resolve())
        response = self.nodes.cost_planner(
            artifacts={**self.artifacts, "automation_concept": Path(concept_path),
                       "layout": Path(layout_path)}, settings=settings,
            llm_profiles=self.llm_profiles, context={"cost_context": cost_context},
            output_path=output)
        manifest = _read(self.manifest_path)
        published = dict(manifest.get("artifacts") or {})
        published.update({"cost_estimate": str(output.relative_to(self.output_root)),
                          "price_matches": str(Path(response["matches_artifact"]).relative_to(self.output_root))})
        self._manifest(status="awaiting_cost_review", active_cost_revision=revision_id,
                       artifacts=published)
        return response

    def run(self, planning_instruction: str, *, idea_revision: str = "idea_r001",
            concept_revision: str = "concept_r001") -> dict[str, Any]:
        idea_response = self.create_idea(planning_instruction, revision_id=idea_revision)
        return self.build_concept(idea_path=idea_response["artifact"], revision_id=concept_revision)
