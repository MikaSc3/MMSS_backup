"""Stage-aware visualization selection from real V3 workflow artifacts."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
SEQUENCE_ISO1_PATTERN = re.compile(r"^step_(\d+)_iso1_transp_0_0\.png$", re.IGNORECASE)
MONOPART_CAROUSEL_PATTERN = re.compile(
    r"^(part_(\d+))-iso(1|4)_transp_0_0\.png$",
    re.IGNORECASE,
)

# Strict user-facing whitelist. The visualization never renders complete JSON
# objects or arbitrary keys from generated artifacts.
DISPLAY_KEYS = {
    "assembly": (
        "assembly_name_guess",
        "assembly_description",
        "partslist",
        "primary_function",
        "total_parts",
        "unique_parts",
    ),
    "part": ("part_id", "part_name_guess", "geometric_characteristics", "handling_implications"),
    "sequence": ("step_id", "step_description", "joining_process", "joining_part", "sequence_description"),
    "ffa": (
        "step_id",
        "step_description",
        "separation_risks",
        "handling_risks",
        "positioning_risks",
        "joining_risks",
        "improvements",
    ),
}


@dataclass(frozen=True)
class VisualizationSnapshot:
    title: str
    detail: str
    image_path: Path | None = None
    completed: int | None = None
    total: int | None = None
    progress_step: int | None = None
    facts: tuple[str, ...] = ()
    image_step: int | None = None
    image_step_total: int | None = None
    image_badge: str | None = None

    @property
    def ratio(self) -> float | None:
        if self.completed is None or not self.total:
            return None
        return min(1.0, max(0.0, self.completed / self.total))


def build_snapshot(
    session_root: Path | None,
    *,
    phase: str,
    tools: list[dict[str, Any]],
    awaiting_input: bool,
    workflow_complete: bool,
    workflow_error: str | None,
    sequence_display_step: int = 0,
    phase_started_at: float | None = None,
) -> VisualizationSnapshot:
    if workflow_error:
        return VisualizationSnapshot("Visualization unavailable", "The workflow stopped with an error.")
    if session_root is None or not session_root.exists():
        return VisualizationSnapshot(
            "Follow the instructions of the Agent to start the process",
            "",
            progress_step=0,
        )

    root = session_root
    active_tool = next(
        (item.get("name") for item in reversed(tools) if item.get("status") == "running"),
        None,
    )
    assembly_images = _assembly_images(root)
    assembly_image = (
        _carousel_image(assembly_images, seconds_per_image=2)
        if active_tool
        else None
    ) or _preferred_assembly_image(root)
    sequence_json = _latest_sequence_json(root)
    sequence_image = _latest_sequence_image(root, sequence_json)
    report_plot = _first_existing(root.rglob("*step_ffa_plot.png"))

    report_json = _first_existing(root.rglob("*_ffa_report.json"))
    ffa_json = root / "ffa_assessment" / "ffa_assessment.json"
    interaction_json = _sequence_run_artifact(root, sequence_json, "interaction_analysis.json")
    interaction_partial_json = _sequence_run_artifact(
        root,
        sequence_json,
        "interaction_analysis_partial.json",
    )
    overview_json = _first_existing(root.glob("assembly_*_Overview_Enriched.json"))
    bom_json = _first_existing(root.glob("*_BOM_enriched.json"))
    overview_data = _read_json(overview_json)
    bom_data = _read_json(bom_json)
    sequence_data = _read_json(sequence_json)
    report_data = _read_json(report_json)
    interaction_data = _read_json(interaction_json or interaction_partial_json)
    ffa_data = _read_json(ffa_json)
    stepparser_overview_json = _newest(
        (root / "preprocessing").rglob("*_Overview_Stepparser.json")
    )
    stepparser_overview_data = _read_json(stepparser_overview_json)

    total_parts = _total_parts(root, bom_json)
    unique_parts = _unique_part_count(root, overview_data)
    analysed_parts = _analysed_part_count(root)
    total_steps = _total_steps(sequence_json)
    rendered_steps = _rendered_step_count(root, sequence_json)
    final_phase = (phase or "").upper()

    if workflow_complete:
        return VisualizationSnapshot(
            "Fitness for Automation report complete",
            "Download the report and ask questions to the agent if you like.",
            report_plot or sequence_image or assembly_image,
            progress_step=11,
        )

    if active_tool == "Run_Final_Assessment_Pipeline_tool":
        if final_phase == "FINAL_RENDERING" or (
            final_phase not in {"FINAL_INTERACTIONS", "FINAL_FFA", "FINAL_REPORT"}
            and not _rendering_complete(root, sequence_json, total_steps)
        ):
            rendered_images = _sequence_step_images(root, sequence_json)
            rendered_image = (
                _sequence_image_for_step(rendered_images, sequence_display_step)
                or assembly_image
            )
            rendered_step = _step_number(rendered_image) if rendered_image else 0
            return VisualizationSnapshot(
                "Rendering assembly sequence",
                (
                    f"{rendered_steps} of {total_steps} assembly steps rendered "
                    f"{_working_dots()}"
                    if total_steps
                    else f"Rendering assembly steps {_working_dots()}"
                ),
                rendered_image,
                rendered_steps,
                total_steps or None,
                8,
                _sequence_step_facts(sequence_data, rendered_step),
                image_step=rendered_step or None,
                image_step_total=total_steps or rendered_steps or None,
            )
        if final_phase == "FINAL_INTERACTIONS" or interaction_json is None:
            interaction_images = _sequence_step_images(root, sequence_json)
            interaction_image = _carousel_image(interaction_images, seconds_per_image=3)
            interaction_step = _step_number(interaction_image) if interaction_image else 0
            return VisualizationSnapshot(
                "Analysing assembly interactions in detail",
                _working_dots(),
                interaction_image or sequence_image or assembly_image,
                progress_step=9,
                facts=(
                    _interaction_facts(interaction_data, interaction_step)
                    or _interaction_input_facts(sequence_data, interaction_step)
                ),
                image_step=interaction_step or None,
                image_step_total=total_steps or len(interaction_images) or None,
            )
        if final_phase == "FINAL_FFA" or not ffa_json.exists():
            step_images = _sequence_step_images(root, sequence_json)
            carousel_image = _carousel_image(step_images)
            carousel_step = _step_number(carousel_image) if carousel_image else 0
            assessed_steps = _assessed_step_count(ffa_json)
            return VisualizationSnapshot(
                "Assessing fitness for automation",
                f"Evaluating {total_steps or rendered_steps} assembly steps. {_working_dots()}",
                carousel_image or sequence_image or assembly_image,
                progress_step=9,
                facts=(
                    _ffa_step_facts(ffa_data, carousel_step)
                    or _sequence_step_facts(sequence_data, carousel_step)
                ),
                image_step=carousel_step or None,
                image_step_total=total_steps or len(step_images) or assessed_steps or None,
            )
        return VisualizationSnapshot(
            "Generating the FfA report",
            "Consolidating the completed step assessments into a concise FfA report.",
            report_plot or sequence_image or assembly_image,
            progress_step=10,
            facts=(
                _report_facts(report_data)
                or _ffa_step_facts(
                    ffa_data,
                    _rotating_step_number(ffa_data, "step_assessments"),
                )
            ),
        )

    if report_json:
        return VisualizationSnapshot(
            "Fitness for Automation report complete",
            "Download the report and ask questions to the agent if you like.",
            report_plot or sequence_image or assembly_image,
            progress_step=11,
        )

    if active_tool == "Generate_Or_Revise_Sequence_tool":
        sequence_input_facts = _sequence_generation_input_facts(overview_data, bom_data)
        bom_records = _bom_part_count(bom_data)
        return VisualizationSnapshot(
            "Generating assembly sequence",
            (
                f"Planning from {bom_records} structured BOM part records."
                if bom_records
                else f"Planning with {analysed_parts or total_parts} analysed parts."
            ),
            sequence_image or assembly_image,
            progress_step=6,
            facts=_sequence_overview_facts(sequence_data) or sequence_input_facts,
        )

    if sequence_json:
        review_step = _step_number(sequence_image) if sequence_image else 0
        return VisualizationSnapshot(
            "Assembly sequence ready for review",
            f"{total_steps} assembly steps generated.",
            sequence_image or assembly_image,
            total_steps or None,
            total_steps or None,
            7,
            _sequence_overview_facts(sequence_data),
            image_step=review_step or None,
            image_step_total=total_steps or None,
        )

    if active_tool == "Analyse_Monoparts_And_Merge_tool":
        part_images = _unique_part_images(root)
        carousel_image = _carousel_image(part_images, seconds_per_image=2)
        return VisualizationSnapshot(
            "Analysing individual parts",
            (
                _count_text(analysed_parts, unique_parts, "unique parts analysed")
                + f" {_working_dots()}"
            ),
            carousel_image or _latest_analysed_part_image(root) or assembly_image,
            analysed_parts,
            unique_parts or None,
            5,
            _latest_part_facts(root),
            image_badge=_part_image_badge(carousel_image, part_images),
        )

    if bom_json:
        return VisualizationSnapshot(
            "Individual part analysis complete",
            _count_text(analysed_parts, unique_parts, "unique parts analysed"),
            _latest_analysed_part_image(root) or assembly_image,
            analysed_parts,
            unique_parts or analysed_parts or None,
            5,
            _latest_part_facts(root),
        )

    if active_tool == "Analyse_Assembly_tool":
        return VisualizationSnapshot(
            "Analysing the assembly",
            (
                "Interpreting the assembly structure, function, and components. "
                f"{_working_dots()}"
            ),
            assembly_image,
            progress_step=3,
            facts=(
                _assembly_review_facts(overview_data)
                or _stepparser_overview_facts(stepparser_overview_data)
            ),
        )

    if overview_json or phase == "ASSEMBLY_DIALOGUE":
        return VisualizationSnapshot(
            "Assembly understanding ready for review",
            "The assembly-level analysis has been created.",
            assembly_image,
            progress_step=4,
            facts=_assembly_review_facts(overview_data),
        )

    if active_tool == "Readadditional_Data_tool":
        document_count = _ingested_document_count(root)
        return VisualizationSnapshot(
            "Reading supporting documents",
            f"{document_count} supporting document(s) available.",
            assembly_image,
            progress_step=2,
            facts=(
                _stepparser_overview_facts(stepparser_overview_data)
                + _document_facts(root)
            )[:6],
        )

    if active_tool == "Preprocess_Input_Data_tool":
        preprocessing_parts = _preprocessing_total_parts(root)
        rendered_parts = _rendered_part_count(root)
        part_images = _unique_part_images(root)
        carousel_image = _carousel_image(part_images, seconds_per_image=1)
        return VisualizationSnapshot(
            "Preprocessing CAD data",
            (
                f"Rendering parts {_working_dots()}"
                + (
                    f" {rendered_parts} of {preprocessing_parts} part instances ready."
                    if preprocessing_parts
                    else ""
                )
            ),
            carousel_image or assembly_image or _latest_image(root / "preprocessing"),
            rendered_parts if preprocessing_parts else None,
            preprocessing_parts or None,
            progress_step=1,
            facts=(
                _stepparser_overview_facts(stepparser_overview_data)
                or _preprocessing_facts(root)
            ),
            image_badge=_part_image_badge(carousel_image, part_images),
        )

    if awaiting_input:
        return VisualizationSnapshot(
            "Waiting for your feedback",
            "The current analysis result is ready for discussion.",
            sequence_image or assembly_image,
            facts=_sequence_overview_facts(sequence_data) or _assembly_facts(overview_data),
        )

    return VisualizationSnapshot(
        "Starting workflow",
        "",
        sequence_image or assembly_image,
        facts=(
            _assembly_facts(overview_data)
            or _stepparser_overview_facts(stepparser_overview_data)
        ),
    )


def _preferred_assembly_image(root: Path) -> Path | None:
    return next(
        (path for path in _assembly_images(root) if "iso1_transp_0_0" in path.name.lower()),
        None,
    )


def _assembly_images(root: Path) -> list[Path]:
    preprocessing = root / "preprocessing"
    if not preprocessing.exists():
        return []
    candidates = [
        path
        for path in preprocessing.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and path.parent.name.lower().startswith("assembly_")
        and (
            "iso1_transp_0_0" in path.name.lower()
            or "iso4_transp_0_0" in path.name.lower()
        )
        and "_exp_" not in path.name.lower()
    ]
    newest_by_view = {}
    for path in candidates:
        view = 1 if "iso1_transp_0_0" in path.name.lower() else 4
        current = newest_by_view.get(view)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            newest_by_view[view] = path
    return [newest_by_view[view] for view in (1, 4) if view in newest_by_view]


def _latest_analysed_part_image(root: Path) -> Path | None:
    enriched = sorted(
        (root / "enriched_parts").glob("part_*_Data_enriched.json"),
        key=lambda path: path.stat().st_mtime,
    ) if (root / "enriched_parts").exists() else []
    if not enriched:
        return None
    part_id = enriched[-1].name.split("_Data_enriched", 1)[0].lower()
    candidates = [
        path
        for path in (root / "preprocessing").rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and part_id in path.name.lower()
        and "iso1_transp_0_0" in path.name.lower()
    ]
    return _newest(candidates)


def _unique_part_images(root: Path) -> list[Path]:
    preprocessing = root / "preprocessing"
    if not preprocessing.exists():
        return []
    candidates = [
        path
        for path in preprocessing.rglob("part_*-iso*_transp_0_0.png")
        if path.is_file()
        and MONOPART_CAROUSEL_PATTERN.fullmatch(path.name)
        and "_copy" not in path.parent.name.lower()
        and "_copy" not in path.name.lower()
    ]
    return sorted(candidates, key=lambda path: (_part_number(path), _monopart_view_number(path)))


def _part_image_badge(path: Path | None, paths: list[Path]) -> str | None:
    if path is None:
        return None
    part_ids = list(dict.fromkeys(item.parent.name for item in paths))
    part_id = path.parent.name
    if part_id not in part_ids:
        return None
    position = part_ids.index(part_id) + 1
    view = _monopart_view_number(path)
    return f"{part_id} | ISO{view} | Part {position} / {len(part_ids)}"


def _latest_enriched_part(root: Path) -> Path | None:
    enriched_dir = root / "enriched_parts"
    if not enriched_dir.exists():
        return None
    return _newest(enriched_dir.glob("part_*_Data_enriched.json"))


def _latest_sequence_image(root: Path, sequence_json: Path | None) -> Path | None:
    candidates = _sequence_step_images(root, sequence_json)
    return max(candidates, key=lambda path: (_step_number(path), path.stat().st_mtime), default=None)


def _sequence_step_images(root: Path, sequence_json: Path | None) -> list[Path]:
    renderings_dir = _sequence_renderings_dir(root, sequence_json)
    if renderings_dir is None:
        return []
    candidates = [
        path
        for path in renderings_dir.iterdir()
        if path.is_file() and SEQUENCE_ISO1_PATTERN.fullmatch(path.name)
    ]
    return sorted(candidates, key=lambda path: (_step_number(path), path.stat().st_mtime))


def _sequence_image_for_step(paths: list[Path], step: int) -> Path | None:
    if not paths:
        return None
    if step > 0:
        exact = next((path for path in paths if _step_number(path) == step), None)
        if exact is not None:
            return exact
    return paths[0]


def _sequence_renderings_dir(root: Path, sequence_json: Path | None) -> Path | None:
    if sequence_json is not None:
        candidate = sequence_json.parent / "sequence_renderings"
        if candidate.is_dir():
            return candidate
    candidates = [
        path
        for path in root.glob("assembly_sequence_run*/sequence_renderings")
        if path.is_dir()
    ]
    return _newest(candidates)


def _carousel_image(paths: list[Path], *, seconds_per_image: int = 3) -> Path | None:
    if not paths:
        return None
    index = int(time.time() // seconds_per_image) % len(paths)
    return paths[index]


def _latest_sequence_json(root: Path) -> Path | None:
    candidates = list(root.glob("assembly_sequence_run*/assembly_sequence.json"))
    return _newest(candidates)


def _sequence_run_artifact(
    root: Path,
    sequence_json: Path | None,
    file_name: str,
) -> Path | None:
    if sequence_json is not None:
        candidate = sequence_json.parent / file_name
        return candidate if candidate.exists() else None
    return _first_existing(root.glob(f"assembly_sequence_run*/{file_name}"))


def _total_steps(sequence_json: Path | None) -> int:
    data = _read_json(sequence_json)
    if not isinstance(data, dict):
        return 0
    steps = data.get("steps")
    return len(steps) if isinstance(steps, list) else 0


def _rendered_step_count(root: Path, sequence_json: Path | None) -> int:
    return len({_step_number(path) for path in _sequence_step_images(root, sequence_json)})


def _rendering_complete(root: Path, sequence_json: Path | None, total_steps: int) -> bool:
    search_root = _sequence_renderings_dir(root, sequence_json)
    summary = (
        _first_existing(search_root.glob("rendering_summary.json"))
        if search_root is not None
        else None
    )
    if summary is not None:
        data = _read_json(summary)
        rendered = data.get("rendered_steps") if isinstance(data, dict) else None
        if isinstance(rendered, list) and rendered:
            return not total_steps or len(rendered) >= total_steps
    return bool(total_steps and _rendered_step_count(root, sequence_json) >= total_steps)


def _total_parts(root: Path, bom_json: Path | None) -> int:
    data = _read_json(bom_json)
    if isinstance(data, dict):
        for key in ("total_parts", "total_part_count"):
            value = data.get(key)
            if isinstance(value, int):
                return value
        parts = data.get("parts")
        if isinstance(parts, list):
            return len(parts)
    part_dirs = {
        path.name
        for path in (root / "preprocessing").rglob("part_*")
        if path.is_dir()
    } if (root / "preprocessing").exists() else set()
    return len(part_dirs)


def _preprocessing_total_parts(root: Path) -> int:
    preprocessing = root / "preprocessing"
    if preprocessing.exists():
        overview = _newest(preprocessing.rglob("*_Overview_Stepparser.json"))
        data = _read_json(overview)
        if isinstance(data, dict):
            total_parts = data.get("total_parts")
            if isinstance(total_parts, int) and total_parts > 0:
                return total_parts
    return _total_parts(root, None)


def _working_dots() -> str:
    return "." * (int(time.time()) % 3 + 1)


def _rendered_part_count(root: Path) -> int:
    preprocessing = root / "preprocessing"
    if not preprocessing.exists():
        return 0
    return len({
        path.parent.name
        for path in preprocessing.rglob("part_*-iso1_transp_0_0.png")
        if path.is_file()
    })


def _unique_part_count(root: Path, overview_data: Any) -> int:
    if isinstance(overview_data, dict):
        value = overview_data.get("unique_parts")
        if isinstance(value, int):
            return value
    return len({path.parent.name for path in _unique_part_images(root)})


def _analysed_part_count(root: Path) -> int:
    enriched_dir = root / "enriched_parts"
    if not enriched_dir.exists():
        return 0
    return len({
        path.name.split("_Data_enriched", 1)[0]
        for path in enriched_dir.glob("part_*_Data_enriched.json")
    })


def _ingested_document_count(root: Path) -> int:
    directory = root / "Agent_txt_files" / "ingested_documents"
    if not directory.exists():
        return 0
    return len([
        path for path in directory.glob("*.md")
        if not path.name.startswith("_combined")
    ])


def _assessed_step_count(ffa_json: Path) -> int:
    data = _read_json(ffa_json)
    if not isinstance(data, dict):
        return 0
    value = data.get("assessed_steps")
    if isinstance(value, int):
        return value
    steps = data.get("step_assessments")
    return len(steps) if isinstance(steps, list) else 0


def _interaction_step_count(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    steps = data.get("steps")
    return len(steps) if isinstance(steps, list) else 0


def _assembly_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    facts = []
    name = _clean_fact(data.get("assembly_name_guess"))
    function = _first_statement(data.get("primary_function"))
    total_parts = data.get("total_parts")
    unique_parts = data.get("unique_parts")
    if name:
        facts.append(f"Assembly: {name}")
    if function:
        facts.append(f"Function: {function}")
    if isinstance(total_parts, int):
        part_text = f"{total_parts} parts"
        if isinstance(unique_parts, int):
            part_text += f", {unique_parts} unique"
        facts.append(part_text)
    return tuple(facts[:3])


def _assembly_review_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    facts = []
    description = _first_statement(data.get("assembly_description"))
    part_lines = _statements(data.get("partslist"), limit=2)
    if description:
        facts.append(f"Description: {description}")
    facts.extend(f"Part: {line}" for line in part_lines)
    return tuple(facts[:3])


def _assembly_description_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    description_lines = _statements(data.get("assembly_description"), limit=3)
    return tuple(f"Description: {line}" for line in description_lines)


def _latest_part_facts(root: Path) -> tuple[str, ...]:
    data = _read_json(_latest_enriched_part(root))
    if not isinstance(data, dict):
        return ()
    nested = data.get("metadata_monopart_enriched")
    analysis = nested.get("analysis") if isinstance(nested, dict) else {}
    if not isinstance(analysis, dict):
        analysis = {}
    monopart = analysis.get("monopart_analysis")
    if not isinstance(monopart, dict):
        monopart = {}
    facts = []
    part_id = _clean_fact(data.get("part_id"))
    name = _clean_fact(analysis.get("part_name_guess"))
    geometry = _first_statement(monopart.get("geometric_characteristics"))
    handling = _first_statement(monopart.get("handling_implications"))
    if name or part_id:
        facts.append(f"Part: {name or part_id}")
    if geometry:
        facts.append(f"Geometry: {geometry}")
    if handling:
        facts.append(f"Handling: {handling}")
    return tuple(facts[:3])


def _sequence_overview_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    facts = []
    description = _first_statement(data.get("sequence_description"))
    steps = data.get("steps")
    if description:
        facts.append(description)
    if isinstance(steps, list):
        facts.append(f"{len(steps)} assembly steps")
    return tuple(facts[:2])


def _sequence_generation_input_facts(
    overview_data: Any,
    bom_data: Any,
) -> tuple[str, ...]:
    facts = []
    description = (
        _first_statement(overview_data.get("assembly_description"))
        if isinstance(overview_data, dict)
        else None
    )
    function = (
        _first_statement(overview_data.get("primary_function"))
        if isinstance(overview_data, dict)
        else None
    )
    if description:
        facts.append(f"Assembly context: {description}")
    if function:
        facts.append(f"Primary function: {function}")

    parts = bom_data.get("parts") if isinstance(bom_data, dict) else None
    if isinstance(parts, list):
        valid_parts = [part for part in parts if isinstance(part, dict)]
        if valid_parts:
            index = int(time.time() // 3) % len(valid_parts)
            part = valid_parts[index]
            part_id = _clean_fact(part.get("part_id")) or f"Part {index + 1}"
            part_name = _clean_fact(part.get("part_name_guess"))
            part_label = f"{part_id}: {part_name}" if part_name else part_id
            facts.append(f"BOM record {index + 1}/{len(valid_parts)}: {part_label}")
            touching = part.get("part_is_touching")
            if isinstance(touching, list) and touching:
                facts.append(f"Touching parts: {', '.join(str(item) for item in touching)}")
            else:
                facts.append("Touching parts: none listed")
    return tuple(facts[:4])


def _bom_part_count(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    parts = data.get("parts")
    return len(parts) if isinstance(parts, list) else 0


def _sequence_step_facts(data: Any, step_number: int) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return _sequence_overview_facts(data)
    target = next(
        (
            step for step in steps
            if isinstance(step, dict) and int(step.get("step_id") or 0) == step_number
        ),
        None,
    )
    if target is None:
        target = steps[min(max(step_number - 1, 0), len(steps) - 1)]
    if not isinstance(target, dict):
        return ()
    facts = []
    description = _clean_fact(target.get("step_description"))
    process = _clean_fact(target.get("joining_process"))
    joining_part = target.get("joining_part")
    if description:
        facts.append(f"Step {target.get('step_id', step_number)}: {description}")
    if process:
        facts.append(f"Process: {process}")
    if joining_part:
        if isinstance(joining_part, list):
            joining_part = ", ".join(str(item) for item in joining_part)
        facts.append(f"Joining part: {joining_part}")
    return tuple(facts[:3])


def _interaction_facts(data: Any, step_number: int) -> tuple[str, ...]:
    step = _step_object(data, step_number, "steps")
    if not step:
        return ()
    detail = step.get("InteractionAnalysisDetail")
    if not isinstance(detail, dict):
        return ()
    facts = []
    description = _clean_fact(step.get("step_description"))
    geometric = _first_statement(detail.get("geometric_interaction"))
    positioning = _first_statement(detail.get("positioning_possibilities"))
    stability = _first_statement(detail.get("stability_in_positioned_state"))
    if description:
        facts.append(f"Step {step.get('step_id', step_number)}: {description}")
    if geometric:
        facts.append(f"Interaction: {geometric}")
    if positioning:
        facts.append(f"Positioning: {positioning}")
    if stability:
        facts.append(f"Stability: {stability}")
    return tuple(facts[:4])


def _interaction_input_facts(data: Any, step_number: int) -> tuple[str, ...]:
    step = _step_object(data, step_number, "steps")
    if not step:
        return ()
    facts = []
    description = _clean_fact(step.get("step_description"))
    process = _clean_fact(step.get("joining_process"))
    base_part = _clean_fact(step.get("base_part"))
    joining_part = step.get("joining_part")
    if description:
        facts.append(f"Step {step.get('step_id', step_number)}: {description}")
    if process:
        facts.append(f"Process: {process}")
    if base_part:
        facts.append(f"Base part: {base_part}")
    if joining_part:
        if isinstance(joining_part, list):
            joining_part = ", ".join(str(item) for item in joining_part)
        facts.append(f"Joining part: {joining_part}")
    return tuple(facts[:4])


def _ffa_step_facts(data: Any, step_number: int) -> tuple[str, ...]:
    step = _step_object(data, step_number, "step_assessments")
    if not step:
        return ()
    facts = []
    description = _clean_fact(step.get("step_description"))
    if description:
        facts.append(f"Step {step.get('step_id', step_number)}: {description}")
    assessment = step.get("assessment")
    overall = assessment.get("overall_ffa") if isinstance(assessment, dict) else None
    if isinstance(overall, list):
        for item in overall:
            if not isinstance(item, dict):
                continue
            subprocess = _clean_fact(item.get("subprocess"))
            potential = _first_statement(item.get("automation_potential"))
            risk = _first_statement(item.get("risks"))
            label = subprocess.title() if subprocess else "Assessment"
            if potential:
                facts.append(f"{label}: {potential}")
            if risk and len(facts) < 4:
                facts.append(f"{label} risk: {risk}")
            if len(facts) >= 4:
                break
    return tuple(facts[:4])


def _step_object(data: Any, step_number: int, steps_key: str) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    steps = data.get(steps_key)
    if not isinstance(steps, list) or not steps:
        return None
    if step_number:
        for step in steps:
            if isinstance(step, dict) and int(step.get("step_id") or 0) == step_number:
                return step
    return next((step for step in reversed(steps) if isinstance(step, dict)), None)


def _rotating_step_number(data: Any, steps_key: str) -> int:
    if not isinstance(data, dict):
        return 0
    steps = [step for step in data.get(steps_key, []) if isinstance(step, dict)]
    if not steps:
        return 0
    index = int(time.time() // 3) % len(steps)
    return int(steps[index].get("step_id") or 0)


def _report_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    facts = []
    difficult_step, main_risk = _most_challenging_report_step(data.get("steps"))
    assembly_level = data.get("assembly_level")
    improvement = None
    if isinstance(assembly_level, dict):
        improvement = _first_statement(assembly_level.get("improvements"))
    if difficult_step:
        facts.append(difficult_step)
    if main_risk:
        facts.append(f"Main risk: {main_risk}")
    if improvement:
        facts.append(f"Improvement: {improvement}")
    return tuple(facts[:3])


def _most_challenging_report_step(steps: Any) -> tuple[str | None, str | None]:
    if not isinstance(steps, list):
        return None, None
    best: tuple[int, dict[str, Any]] | None = None
    potential_keys = (
        "separation_potential",
        "handling_potential",
        "positioning_potential",
        "joining_potential",
    )
    for step in steps:
        if not isinstance(step, dict):
            continue
        text = " ".join(_flatten_text(step.get(key)) for key in potential_keys).lower()
        score = text.count("low") * 2 + text.count("moderate")
        if best is None or score > best[0]:
            best = (score, step)
    if best is None:
        return None, None
    step = best[1]
    description = _first_statement(step.get("step_description"))
    step_fact = (
        f"Most challenging: Step {step.get('step_id', '?')} - {description}"
        if description
        else None
    )
    risk = _first_available_statement(
        step,
        ("joining_risks", "positioning_risks", "handling_risks", "separation_risks"),
    )
    return step_fact, risk


def _first_available_statement(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        statement = _first_statement(data.get(key))
        if statement:
            return statement
    return None


def _document_facts(root: Path) -> tuple[str, ...]:
    directory = root / "Agent_txt_files" / "ingested_documents"
    if not directory.exists():
        return ()
    names = [
        path.stem
        for path in sorted(directory.glob("*.md"))
        if not path.name.startswith("_combined")
    ]
    return tuple(f"Document: {name}" for name in names[:3])


def _preprocessing_facts(root: Path) -> tuple[str, ...]:
    part_count = _total_parts(root, None)
    assembly_image = _preferred_assembly_image(root)
    facts = []
    if assembly_image is not None:
        facts.append("Assembly and individual-part views are available")
    if part_count:
        facts.append(f"{part_count} CAD part instances detected")
    return tuple(facts)


def _stepparser_overview_facts(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()

    facts = []
    total_parts = data.get("total_parts")
    unique_parts = data.get("unique_parts")
    direct_children = data.get("direct_children")
    if isinstance(total_parts, int):
        summary = f"CAD structure: {total_parts} part instances"
        if isinstance(unique_parts, int):
            summary += f", {unique_parts} unique parts"
        if isinstance(direct_children, int):
            summary += f", {direct_children} direct children"
        facts.append(summary)

    bounding_box = data.get("bounding_box")
    if isinstance(bounding_box, dict):
        dimensions = [
            _format_number(bounding_box.get(axis))
            for axis in ("x", "y", "z")
        ]
        if all(dimensions):
            facts.append(f"Bounding box: {' x '.join(dimensions)} mm")

    total_volume = data.get("total_volume")
    if isinstance(total_volume, (int, float)):
        facts.append(f"Total volume: {_format_number(total_volume)} mm^3")

    center_of_mass = data.get("COM")
    absolute_com = center_of_mass.get("absolute") if isinstance(center_of_mass, dict) else None
    if isinstance(absolute_com, list) and len(absolute_com) >= 3:
        coordinates = [_format_number(value) for value in absolute_com[:3]]
        if all(coordinates):
            facts.append(f"Center of mass: ({', '.join(coordinates)}) mm")

    return tuple(facts[:4])


def _format_number(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def _first_statement(value: Any) -> str | None:
    statements = _statements(value, limit=1)
    return statements[0] if statements else None


def _statements(value: Any, *, limit: int) -> list[str]:
    text = _flatten_text(value)
    if not text:
        return []
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]
    return [_truncate_fact(line) for line in lines[:limit]]


def _flatten_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


def _clean_fact(value: Any) -> str | None:
    text = _flatten_text(value).strip()
    return _truncate_fact(text) if text else None


def _truncate_fact(text: str, limit: int = 150) -> str:
    text = re.sub(r"\s*\[\]\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _preprocessing_image_count(root: Path) -> int:
    directory = root / "preprocessing"
    if not directory.exists():
        return 0
    return sum(
        1 for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _latest_image(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    return _newest(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _read_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _first_existing(paths: Iterable[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def _newest(paths: Iterable[Path]) -> Path | None:
    return max(paths, key=lambda path: path.stat().st_mtime, default=None)


def _step_number(path: Path) -> int:
    match = re.search(r"step_(\d+)", path.name.lower())
    return int(match.group(1)) if match else 0


def _part_number(path: Path) -> int:
    match = re.search(r"part_(\d+)", path.name.lower())
    return int(match.group(1)) if match else 0


def _monopart_view_number(path: Path) -> int:
    match = re.search(r"-iso(\d+)_", path.name.lower())
    return int(match.group(1)) if match else 0


def _count_text(completed: int, total: int, label: str) -> str:
    if total:
        return f"{completed} of {total} {label}."
    return f"{completed} {label}."
