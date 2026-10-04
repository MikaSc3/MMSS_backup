"""End-to-end product workflow composed from public node interfaces."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping

from .manifest import SessionManifest

EventCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class NodeRegistry:
    step_preprocessing: Callable[..., dict[str, Any]]
    assembly_analysis: Callable[..., dict[str, Any]]
    monopart_analysis: Callable[..., dict[str, Any]]
    bom_merge: Callable[..., dict[str, Any]]
    sequence_generation: Callable[..., dict[str, Any]]
    sequence_rendering: Callable[..., dict[str, Any]]
    interaction_analysis: Callable[..., dict[str, Any]]
    ffa_assessment: Callable[..., dict[str, Any]]
    ffa_scoring: Callable[..., dict[str, Any]]
    report_synthesis: Callable[..., dict[str, Any]]
    report_rendering: Callable[..., dict[str, Any]]


def default_node_registry() -> NodeRegistry:
    from assembly_automation.workflows.nodes.assembly_analysis import run_assembly_analysis
    from assembly_automation.workflows.nodes.bom_merge import run_bom_merge
    from assembly_automation.workflows.nodes.ffa_assessment import run_ffa_assessment
    from assembly_automation.workflows.nodes.ffa_scoring import run_ffa_scoring
    from assembly_automation.workflows.nodes.interaction_analysis import run_interaction_analysis
    from assembly_automation.workflows.nodes.monopart_analysis import run_monopart_analysis
    from assembly_automation.workflows.nodes.report_rendering import run_report_rendering
    from assembly_automation.workflows.nodes.report_synthesis import run_report_synthesis
    from assembly_automation.workflows.nodes.sequence_generation import run_sequence_generation
    from assembly_automation.workflows.nodes.sequence_rendering import run_sequence_rendering
    from assembly_automation.workflows.nodes.step_preprocessing import run_step_preprocessing
    return NodeRegistry(run_step_preprocessing, run_assembly_analysis, run_monopart_analysis,
                        run_bom_merge, run_sequence_generation, run_sequence_rendering,
                        run_interaction_analysis, run_ffa_assessment, run_ffa_scoring,
                        run_report_synthesis, run_report_rendering)


@dataclass(frozen=True)
class WorkflowPaths:
    root: Path
    FOLDER_ORDER = (
        "01_input", "02_preprocessing", "03_assembly", "04_monoparts",
        "05_sequence", "06_assessment", "07_reports", "08_planning",
        "09_user_agent", "10_runs", "11_history",
    )

    @property
    def input(self): return self.root / "01_input"
    @property
    def preprocessing(self): return self.root / "02_preprocessing"
    @property
    def assembly_root(self): return self.root / "03_assembly"
    @property
    def monopart_root(self): return self.root / "04_monoparts"
    @property
    def sequence_root(self): return self.root / "05_sequence"
    @property
    def assessment_root(self): return self.root / "06_assessment"
    @property
    def reports_root(self): return self.root / "07_reports"
    @property
    def planning_root(self): return self.root / "08_planning"
    @property
    def user_agent_root(self): return self.root / "09_user_agent"
    @property
    def runs_root(self): return self.root / "10_runs"
    @property
    def history_root(self): return self.root / "11_history"

    def planning(self, category: str) -> Path:
        folders = {"idea": "01_ideas", "concept": "02_concepts",
                   "layout": "03_layouts", "cost": "04_costs",
                   "detailed_plan": "05_detailed_plans"}
        return self.planning_root / folders[category]

    def assembly(self, revision_id: str) -> Path:
        return self.assembly_root / "revisions" / revision_id

    def monoparts(self, revision_id: str) -> Path:
        return self.monopart_root / "revisions" / revision_id

    def active_revision(self, kind: str, default: str = "r001") -> str:
        registry = self.root / "artifact_registry.json"
        if registry.is_file():
            try:
                value = json.loads(registry.read_text(encoding="utf-8"))
                active = value.get("active", {}).get(kind)
                if isinstance(active, str) and active:
                    return active
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
        return default

    @property
    def assembly_overview(self):
        return self.assembly(self.active_revision("assembly")) / "assembly_overview.json"

    @property
    def enriched_bom(self):
        return self.monoparts(self.active_revision("monoparts")) / "bom.json"

    def revision(self, revision_id: str) -> Path:
        return self.sequence_root / "revisions" / revision_id

    def ffa(self, revision_id: str) -> Path:
        return self.assessment_root / "revisions" / revision_id

    def reports(self, revision_id: str) -> Path:
        return self.reports_root / "revisions" / revision_id


def _read(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _sequence_steps(path: Path) -> list[dict[str, Any]]:
    document = _read(path)
    sequence = document.get("sequence", document)
    if not isinstance(sequence, dict) or not isinstance(sequence.get("steps"), list):
        raise ValueError(f"Approved sequence has no steps: {path}")
    steps = [dict(item) for item in sequence["steps"] if isinstance(item, dict)]
    ids = [item.get("step_id") for item in steps]
    if any(type(value) is not int for value in ids) or ids != list(range(1, len(ids) + 1)):
        raise ValueError("Approved sequence step IDs must be consecutive from 1")
    return steps


class AssemblyAssessmentWorkflow:
    def __init__(self, *, session_root: str | Path, settings: Mapping[str, Any],
                 nodes: NodeRegistry | None = None, event_callback: EventCallback | None = None):
        self.paths = WorkflowPaths(Path(session_root).resolve())
        self.settings = dict(settings)
        self.node_settings = self.settings.get("nodes")
        self.llm_profiles = (self.settings.get("llms") or {}).get("profiles")
        if not isinstance(self.node_settings, Mapping) or not isinstance(self.llm_profiles, Mapping):
            raise ValueError("Workflow settings require nodes and llms.profiles")
        self.nodes = nodes or default_node_registry()
        self.events = event_callback
        self.manifest = SessionManifest(self.paths.root, "assembly_assessment")

    def _set_active_revision(self, kind: str, revision_id: str) -> None:
        path = self.paths.root / "artifact_registry.json"
        value: dict[str, Any] = {"schema_version": 1, "active": {}, "revisions": {}}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                value.update(loaded)
        value.setdefault("active", {})[kind] = revision_id
        value.setdefault("revisions", {}).setdefault(kind, [])
        if revision_id not in value["revisions"][kind]:
            value["revisions"][kind].append(revision_id)
        _write(path, value)

    def _next_revision(self, kind: str) -> str:
        root = {"assembly": self.paths.assembly_root,
                "monoparts": self.paths.monopart_root}[kind] / "revisions"
        numbers = []
        for path in root.glob("r*"):
            if path.is_dir() and path.name[1:].isdigit():
                numbers.append(int(path.name[1:]))
        return f"r{max(numbers, default=0) + 1:03d}"

    def _emit(self, event_type: str, **values: Any) -> None:
        if self.events:
            self.events({"type": event_type, "session_id": self.paths.root.name, **values})

    def _stage(self, name: str, call: Callable[[], tuple[dict[str, Any], dict[str, Path], dict[str, int] | None]]):
        self.manifest.stage(name, "running")
        self._emit("stage_started", stage=name)
        try:
            response, artifacts, counts = call()
            status = response.get("status")
            if status not in {"complete", "partial"}:
                raise RuntimeError(f"Stage {name} returned status {status!r}")
            self.manifest.stage(name, status, artifacts=artifacts, counts=counts)
            for key, path in artifacts.items():
                self.manifest.publish(key, path)
            self._emit("stage_completed", stage=name, status=status, counts=counts or {},
                       artifacts={key: self.manifest.relative(path)
                                  for key, path in artifacts.items()})
            return response
        except Exception as exc:
            self.manifest.stage(name, "failed", error=f"{type(exc).__name__}: {exc}")
            self.manifest.status("failed")
            self._emit("stage_failed", stage=name, error=f"{type(exc).__name__}: {exc}")
            raise

    def _copy_input(self, source: Path) -> Path:
        self.paths.input.mkdir(parents=True, exist_ok=True)
        target = self.paths.input / source.name
        source_hash = sha256(source.read_bytes()).hexdigest()
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != source_hash:
                raise ValueError(f"Session input differs from supplied STEP file: {target}")
        else:
            shutil.copy2(source, target)
        self.manifest.data["input"] = {"step_file": target.relative_to(self.paths.root).as_posix(),
                                       "sha256": source_hash}
        self.manifest.write()
        return target

    def _session_step_file(self) -> Path:
        matches = sorted(path for path in self.paths.input.iterdir()
                         if path.is_file() and path.suffix.lower() in {".step", ".stp"})
        if len(matches) != 1:
            raise ValueError(f"Session input requires exactly one STEP file, found {len(matches)}")
        return matches[0]

    def _fanout(self, *, stage: str, items: list[Any], settings: Mapping[str, Any],
                worker: Callable[[Any], dict[str, Any]], partial_path: Path,
                final_path: Path, item_label: str,
                existing_paths: Mapping[Any, Path] | None = None) -> list[dict[str, Any]]:
        fanout = settings.get("fanout", {}) if isinstance(settings, Mapping) else {}
        parallel = fanout.get("parallel", True)
        max_workers = fanout.get("max_workers", 4)
        if type(parallel) is not bool or type(max_workers) is not int or max_workers < 1:
            raise ValueError(f"Invalid fanout settings for {stage}")
        existing_paths = dict(existing_paths or {})
        results: dict[Any, dict[str, Any]] = {
            item: _read(existing_paths[item]) for item in items
            if item in existing_paths and existing_paths[item].is_file()
        }
        pending = [item for item in items if item not in results]

        def accept(item, response):
            if response.get("status") != "complete" or not isinstance(response.get("result"), dict):
                raise RuntimeError(f"{stage} item {item!r} did not complete")
            results[item] = response["result"]
            ordered = [results[key] for key in items if key in results]
            _write(partial_path, {"status": "partial", "completed": len(ordered),
                                  "total": len(items), item_label: ordered})
            self._emit("stage_progress", stage=stage, completed=len(ordered), total=len(items), item=item)
            self._emit("artifact_updated", stage=stage,
                       artifact=self.manifest.relative(partial_path),
                       item=item, completed=len(ordered), total=len(items), status="partial")

        if results:
            self._emit("stage_progress", stage=stage, completed=len(results), total=len(items),
                       item="reused_existing_artifacts")
        if parallel and len(pending) > 1:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(pending)),
                                    thread_name_prefix=stage) as executor:
                futures = {executor.submit(worker, item): item for item in pending}
                for future in as_completed(futures):
                    accept(futures[future], future.result())
        else:
            for item in pending:
                accept(item, worker(item))
        ordered = [results[item] for item in items]
        _write(final_path, {"status": "complete", "total": len(items), item_label: ordered})
        if partial_path.exists():
            partial_path.unlink()
        return ordered

    @staticmethod
    def _preserve_incomplete(directory: Path) -> None:
        if not directory.exists() or not any(directory.iterdir()):
            return
        index = 1
        while True:
            candidate = directory.with_name(f"{directory.name}.failed_{index:02d}")
            if not candidate.exists():
                directory.replace(candidate)
                return
            index += 1

    @staticmethod
    def _archive_artifact(path: Path) -> Path | None:
        """Move one superseded artifact into an adjacent numbered history folder."""
        if not path.exists():
            return None
        history = path.parent / "history"
        history.mkdir(parents=True, exist_ok=True)
        index = 1
        while True:
            candidate = history / f"{path.stem}_v{index:03d}{path.suffix}"
            if not candidate.exists():
                path.replace(candidate)
                return candidate
            index += 1

    def _preprocessing_artifacts(self) -> dict[str, Path]:
        root = self.paths.preprocessing
        return {"assembly": root / "assembly.json", "bom": root / "bom.json",
                "spatial_relations": root / "spatial_relations.json",
                "interlocking": root / "interlocking.json", "images": root / "images"}

    def preprocess(self, *, step_file: str | Path | None = None) -> dict[str, Any]:
        """Ensure the deterministic STEP artifacts exist and stop before LLM analysis."""
        if step_file is not None:
            session_step = self._copy_input(Path(step_file).resolve(strict=True))
        else:
            session_step = self._session_step_file()
        artifacts = self._preprocessing_artifacts()
        if not all(path.exists() for path in artifacts.values()):
            self._preserve_incomplete(self.paths.preprocessing)
            self._stage("step_preprocessing", lambda: (
                self.nodes.step_preprocessing(session_step, self.paths.preprocessing,
                    self.node_settings["step_preprocessing"],
                    progress=lambda label, completed, total: self._emit(
                        "stage_progress", stage="step_preprocessing", item=label,
                        completed=completed, total=total)),
                artifacts, None))
        return {"status": "complete", "session_root": str(self.paths.root),
                "artifacts": {key: str(path) for key, path in artifacts.items()},
                "manifest": str(self.manifest.path)}

    def analyze_assembly(self, *, user_context: str = "", force: bool = False,
                         revision_id: str | None = None) -> dict[str, Any]:
        """Run the assembly interpretation phase, optionally retaining and replacing it."""
        artifacts = self._preprocessing_artifacts()
        if not all(path.exists() for path in artifacts.values()):
            raise RuntimeError("STEP preprocessing must complete before assembly analysis")
        current = self.paths.assembly_overview
        revision = revision_id or (self._next_revision("assembly") if force and current.exists()
                                   else self.paths.active_revision("assembly"))
        output = self.paths.assembly(revision) / "assembly_overview.json"
        if not output.exists():
            self._stage("assembly_analysis", lambda: (
                self.nodes.assembly_analysis(artifacts=artifacts,
                    settings=self.node_settings["assembly_analysis"], llm_profiles=self.llm_profiles,
                    context={"user_context": user_context}, output_path=output),
                {"assembly_overview": output}, None))
        self._set_active_revision("assembly", revision)
        self.manifest.status("awaiting_assembly_review")
        self._emit("checkpoint", checkpoint="assembly_review",
                   artifact=self.manifest.relative(output))
        return {"status": "awaiting_assembly_review",
                "assembly_overview": str(output), "revision_id": revision,
                "archived": None,
                "manifest": str(self.manifest.path)}

    def analyze_monoparts(self, *, user_context: str = "",
                          part_ids: list[str] | None = None,
                          force: bool = False) -> dict[str, Any]:
        """Run selected or all unique-part analyses and rebuild the enriched BOM."""
        artifacts = self._preprocessing_artifacts()
        if not self.paths.assembly_overview.exists():
            raise RuntimeError("Assembly analysis must complete before monopart analysis")
        bom = _read(artifacts["bom"])
        all_part_ids = sorted(item["part_id"] for item in bom.get("parts", [])
                              if isinstance(item, dict) and isinstance(item.get("part_id"), str))
        if not all_part_ids:
            raise ValueError("STEP BOM contains no unique parts")
        selected = all_part_ids if part_ids is None else list(dict.fromkeys(part_ids))
        unknown = sorted(set(selected) - set(all_part_ids))
        if unknown:
            raise ValueError(f"Unknown part IDs: {unknown}")
        previous_revision = self.paths.active_revision("monoparts")
        revision = self._next_revision("monoparts") if force and self.paths.enriched_bom.exists() \
            else previous_revision
        monopart_root = self.paths.monoparts(revision)
        if force and revision != previous_revision:
            previous_root = self.paths.monoparts(previous_revision)
            if previous_root.is_dir():
                shutil.copytree(previous_root, monopart_root, dirs_exist_ok=True)
        part_dir = monopart_root / "parts"
        part_paths = {part_id: part_dir / f"{part_id}.json" for part_id in all_part_ids}
        analyses_index = monopart_root / "analyses.json"
        archived: list[str] = []
        if force:
            for part_id in selected:
                previous = self._archive_artifact(part_paths[part_id])
                if previous:
                    archived.append(str(previous))
                elif revision != previous_revision:
                    part_paths[part_id].unlink(missing_ok=True)
            for aggregate in (analyses_index, monopart_root / "bom.json"):
                previous = self._archive_artifact(aggregate)
                if previous:
                    archived.append(str(previous))
        if (not analyses_index.exists()
                or any(not path.exists() for path in part_paths.values())):
            partial = monopart_root / "analyses.partial.json"

            def analyze_part(part_id):
                return self.nodes.monopart_analysis(part_id=part_id,
                    artifacts={"bom": artifacts["bom"],
                               "assembly_overview": self.paths.assembly_overview,
                               "images": artifacts["images"]},
                    settings=self.node_settings["monopart_analysis"], llm_profiles=self.llm_profiles,
                    context={"user_context": user_context}, output_path=part_paths[part_id])

            self._stage("monopart_analysis", lambda: (
                {"status": "complete", "result": self._fanout(
                    stage="monopart_analysis",
                    items=all_part_ids,
                    settings=self.node_settings["monopart_analysis"], worker=analyze_part,
                    partial_path=partial, final_path=analyses_index, item_label="parts",
                    existing_paths=part_paths)},
                {"monopart_analyses": analyses_index}, {"total": len(all_part_ids)}))
        enriched_bom = monopart_root / "bom.json"
        if not enriched_bom.exists():
            self._stage("bom_merge", lambda: (
                self.nodes.bom_merge(bom=artifacts["bom"], part_analyses=part_paths,
                    output_path=enriched_bom, settings=self.node_settings["bom_merge"]),
                {"enriched_bom": enriched_bom}, {"parts": len(all_part_ids)}))
        self._set_active_revision("monoparts", revision)
        self.manifest.status("awaiting_bom_review")
        self._emit("checkpoint", checkpoint="bom_review",
                   artifact=self.manifest.relative(enriched_bom))
        return {"status": "awaiting_bom_review", "bom": str(enriched_bom),
                "revision_id": revision,
                "part_analyses": {key: str(value) for key, value in part_paths.items()},
                "archived": archived, "manifest": str(self.manifest.path)}

    def generate_sequence(self, *, revision_id: str = "r001", mode: str = "generate",
                          initial_sequence: Any = None, user_context: str = "",
                          sequence_constraints: str = "",
                          user_feedback_summary: str = "") -> dict[str, Any]:
        """Generate one immutable sequence revision and stop for user approval."""
        artifacts = self._preprocessing_artifacts()
        if not self.paths.assembly_overview.exists() or not self.paths.enriched_bom.exists():
            raise RuntimeError("Assembly and monopart analysis must complete before sequence generation")
        revision = self.paths.revision(revision_id)
        sequence_path = revision / "assembly_sequence.json"
        if not sequence_path.exists():
            sequence_artifacts = {**artifacts, "assembly_overview": self.paths.assembly_overview,
                                  "bom_enriched": self.paths.enriched_bom}
            if mode == "revise":
                sequence_artifacts["initial_sequence"] = initial_sequence
            context = {"user_context": user_context, "sequence_constraints": sequence_constraints,
                       "user_feedback_summary": user_feedback_summary}
            self._stage(f"sequence_generation:{revision_id}", lambda: (
                self.nodes.sequence_generation(mode=mode, artifacts=sequence_artifacts,
                    settings=self.node_settings["sequence_generation"], llm_profiles=self.llm_profiles,
                    context=context, output_path=sequence_path),
                {"assembly_sequence": sequence_path}, {"steps": len(_sequence_steps(sequence_path))}))
        self.manifest.status("awaiting_sequence_approval", active_sequence_revision=revision_id)
        self._emit("checkpoint", checkpoint="sequence_approval", revision_id=revision_id,
                   artifact=self.manifest.relative(sequence_path))
        return {"status": "awaiting_sequence_approval", "session_root": str(self.paths.root),
                "revision_id": revision_id, "sequence": str(sequence_path),
                "manifest": str(self.manifest.path)}

    def prepare_through_sequence(self, *, step_file: str | Path, revision_id: str = "r001",
                                 sequence_mode: str = "generate", initial_sequence: Any = None,
                                 user_context: str = "", sequence_constraints: str = "",
                                 user_feedback_summary: str = "") -> dict[str, Any]:
        self.preprocess(step_file=step_file)
        self.analyze_assembly(user_context=user_context)
        self.analyze_monoparts(user_context=user_context)
        return self.generate_sequence(
            revision_id=revision_id, mode=sequence_mode, initial_sequence=initial_sequence,
            user_context=user_context, sequence_constraints=sequence_constraints,
            user_feedback_summary=user_feedback_summary)

    def complete_from_sequence(self, *, revision_id: str, approved_sequence: str | Path,
                               user_context: str = "") -> dict[str, Any]:
        sequence_path = Path(approved_sequence).resolve(strict=True)
        _sequence_steps(sequence_path)
        revision = self.paths.revision(revision_id)
        preprocessing = self.paths.preprocessing
        artifacts = {"assembly": preprocessing / "assembly.json", "bom": preprocessing / "bom.json",
                     "spatial_relations": preprocessing / "spatial_relations.json",
                     "interlocking": preprocessing / "interlocking.json", "images": preprocessing / "images",
                     "assembly_overview": self.paths.assembly_overview,
                     "bom_enriched": self.paths.enriched_bom, "sequence": sequence_path}
        renderings = revision / "renderings"
        rendering_summary = renderings / "rendering_summary.json"
        if not rendering_summary.exists():
            self._preserve_incomplete(renderings)
            self._stage(f"sequence_rendering:{revision_id}", lambda: (
                self.nodes.sequence_rendering(step_file=self._session_step_file(), sequence=sequence_path,
                    bom=self.paths.enriched_bom, output_dir=renderings,
                    settings=self.node_settings["sequence_rendering"],
                    progress=lambda label, completed, total: self._emit(
                        "stage_progress", stage="sequence_rendering", item=label,
                        completed=completed, total=total)),
                {"sequence_renderings": rendering_summary}, None))
        artifacts["sequence_renderings"] = renderings
        steps = _sequence_steps(sequence_path)
        step_ids = [item["step_id"] for item in steps]

        interaction_root = revision / "interaction_analysis"
        interaction_final = interaction_root / "interaction_analysis.json"
        interaction_paths = {step_id: interaction_root / "steps" / f"step_{step_id:03d}.json"
                             for step_id in step_ids}
        if not interaction_final.exists():
            def analyze_interaction(step_id):
                return self.nodes.interaction_analysis(step_id=step_id, artifacts=artifacts,
                    settings=self.node_settings["interaction_analysis"], llm_profiles=self.llm_profiles,
                    context={"user_context": user_context}, output_path=interaction_paths[step_id])
            self._stage(f"interaction_analysis:{revision_id}", lambda: (
                {"status": "complete", "result": self._fanout(
                    stage="interaction_analysis", items=step_ids,
                    settings=self.node_settings["interaction_analysis"], worker=analyze_interaction,
                    partial_path=interaction_root / "interaction_analysis.partial.json",
                    final_path=interaction_final, item_label="steps",
                    existing_paths=interaction_paths)},
                {"interaction_analysis": interaction_final}, {"steps": len(step_ids)}))

        ffa_root = self.paths.ffa(revision_id)
        ffa_final = ffa_root / "ffa_assessment.json"
        ffa_paths = {step_id: ffa_root / "steps" / f"step_{step_id:03d}.json" for step_id in step_ids}
        if not ffa_final.exists():
            def assess_ffa(step_id):
                return self.nodes.ffa_assessment(step_id=step_id,
                    artifacts={**artifacts, "interaction_step": interaction_paths[step_id]},
                    settings=self.node_settings["ffa_assessment"], llm_profiles=self.llm_profiles,
                    context={"user_context": user_context}, output_path=ffa_paths[step_id])
            self._stage(f"ffa_assessment:{revision_id}", lambda: (
                {"status": "complete", "result": self._fanout(
                    stage="ffa_assessment", items=step_ids,
                    settings=self.node_settings["ffa_assessment"], worker=assess_ffa,
                    partial_path=ffa_root / "ffa_assessment.partial.json",
                    final_path=ffa_final, item_label="steps", existing_paths=ffa_paths)},
                {"ffa_assessment": ffa_final}, {"steps": len(step_ids)}))

        scores = ffa_root / "ffa_scores.json"
        if not scores.exists():
            self._stage(f"ffa_scoring:{revision_id}", lambda: (
                self.nodes.ffa_scoring(assessments=list(ffa_paths.values()),
                    settings=self.node_settings["ffa_scoring"], output_path=scores),
                {"ffa_scores": scores}, {"steps": len(step_ids)}))
        reports = self.paths.reports(revision_id)
        report_json = reports / "report.json"
        if not report_json.exists():
            self._stage(f"report_synthesis:{revision_id}", lambda: (
                self.nodes.report_synthesis(artifacts={
                    "assembly_overview": self.paths.assembly_overview,
                    "bom_enriched": self.paths.enriched_bom, "sequence": sequence_path,
                    "ffa_assessments": list(ffa_paths.values()), "ffa_scores": scores},
                    settings=self.node_settings["report_synthesis"], llm_profiles=self.llm_profiles,
                    context={"user_context": user_context}, output_path=report_json),
                {"report": report_json}, None))
        rendered = reports / "rendered"
        render_manifest = rendered / "rendering_manifest.json"
        if not render_manifest.exists():
            self._stage(f"report_rendering:{revision_id}", lambda: (
                self.nodes.report_rendering(report=report_json, output_dir=rendered,
                    settings=self.node_settings["report_rendering"],
                    image_roots={"preprocessing_images": preprocessing / "images",
                                 "sequence_renderings": renderings}),
                {"rendered_reports": render_manifest}, None))
        self.manifest.status("complete", active_sequence_revision=revision_id)
        self._emit("workflow_completed", revision_id=revision_id)
        return {"status": "complete", "session_root": str(self.paths.root),
                "revision_id": revision_id, "sequence": str(sequence_path),
                "report": str(report_json), "rendering_manifest": str(render_manifest),
                "manifest": str(self.manifest.path)}

    def run(self, *, step_file: str | Path, revision_id: str = "r001",
            approve_sequence: bool = False, sequence_mode: str = "generate",
            initial_sequence: Any = None, user_feedback_summary: str = "",
            user_context: str = "", sequence_constraints: str = "") -> dict[str, Any]:
        prepared = self.prepare_through_sequence(
            step_file=step_file, revision_id=revision_id, sequence_mode=sequence_mode,
            initial_sequence=initial_sequence, user_feedback_summary=user_feedback_summary,
            user_context=user_context, sequence_constraints=sequence_constraints)
        if not approve_sequence:
            return prepared
        return self.complete_from_sequence(revision_id=revision_id,
                                           approved_sequence=prepared["sequence"],
                                           user_context=user_context)


def run_app_v3_workflow(*, session_root: str | Path, settings: Mapping[str, Any],
                        step_file: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Convenience entry point used by CLI/UI adapters."""
    return AssemblyAssessmentWorkflow(session_root=session_root, settings=settings).run(
        step_file=step_file, **kwargs)
