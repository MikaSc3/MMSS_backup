"""Terminal-first automation concept planner for completed App V3 sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from agent.structured_output import (
    AutomatisierungsGesamtkonzept,
    InitialeAnforderungsklaerung,
    LayoutPlanerErgebnis,
    ProzessprinzipErgebnis,
)


STRATEGIES = ("manuell", "halbautomatisiert", "vollautomatisiert")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "automationplanner.yaml"


@dataclass
class AutomationPlannerArtifacts:
    session_root: Path
    assembly_name: str
    output_dir: Path
    assembly_overview: Dict[str, Any]
    bom: Dict[str, Any]
    enriched_parts: Dict[str, Dict[str, Any]]
    assembly_sequence: Dict[str, Any]
    interaction_analysis: Dict[str, Any]
    ffa_assessment: Dict[str, Any]
    ffa_report: Dict[str, Any]
    additional_context_block: str
    sequence_run_dir: Path


def load_automation_planner_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load automation planner settings from YAML."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    if not path.exists():
        return {}
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError(f"PyYAML is required to read automation planner config: {path}") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    return data if isinstance(data, dict) else {}


def run_automation_planner_on_session(
    session_root: str | Path,
    *,
    user_feedback: str = "",
    max_context_chars: int = 24000,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run all automation-planner modules on an existing completed V3 session."""
    config = dict(config or {})
    llm_model = str(config.get("llm_model") or "5.4")
    max_completion_tokens = int(config.get("max_completion_tokens") or 8000)
    max_context_chars = int(config.get("max_context_chars") or max_context_chars)
    module_tokens = config.get("module_max_completion_tokens")
    if not isinstance(module_tokens, dict):
        module_tokens = {}

    artifacts = load_session_artifacts(session_root)
    artifacts.output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("AUTOMATISIERUNGSPLANER")
    print("=" * 80)
    print(f"Session: {artifacts.session_root}")
    print(f"Assembly: {artifacts.assembly_name}")
    print(f"Sequence run: {artifacts.sequence_run_dir.name}")
    print(f"Output: {artifacts.output_dir}")
    print(f"LLM model: {llm_model}")

    initial_path = artifacts.output_dir / "01_initiale_anforderungsklaerung.json"
    initial = _load_model_if_exists(initial_path, InitialeAnforderungsklaerung)
    if initial is None:
        initial = run_initial_requirements(
            artifacts,
            max_context_chars=max_context_chars,
            llm_model=llm_model,
            max_completion_tokens=_module_token_limit(module_tokens, "initial_requirements", max_completion_tokens),
        )
        _save_model(initial_path, initial)
        print(f"[1/3] Initiale Anforderungsklaerung: {len(initial.montageschritte)} Schritte")
    else:
        print(f"[1/3] Initiale Anforderungsklaerung geladen: {len(initial.montageschritte)} Schritte")

    process_dir = artifacts.output_dir / "02_prozessprinzipien"
    process_dir.mkdir(exist_ok=True)
    process_results: list[ProzessprinzipErgebnis] = []
    for step in initial.montageschritte:
        process_path = process_dir / f"step_{step.montageschritt_nr:03d}_prozessprinzipien.json"
        result = _load_model_if_exists(process_path, ProzessprinzipErgebnis)
        if result is None:
            result = run_process_principles(
                artifacts,
                initial,
                step.montageschritt_nr,
                user_feedback=user_feedback,
                max_context_chars=max_context_chars,
                llm_model=llm_model,
                max_completion_tokens=_module_token_limit(module_tokens, "process_principles", max_completion_tokens),
            )
            _save_model(process_path, result)
            print(f"[2/3] Prozessprinzipien Schritt {step.montageschritt_nr}: {len(result.prozessprinzipien)} Varianten")
        else:
            print(f"[2/3] Prozessprinzipien Schritt {step.montageschritt_nr} geladen: {len(result.prozessprinzipien)} Varianten")
        process_results.append(result)

    variant_dir = artifacts.output_dir / "03_automatisierungsvarianten"
    variant_dir.mkdir(exist_ok=True)

    variants: Dict[str, AutomatisierungsGesamtkonzept] = {}
    for strategy in STRATEGIES:
        variant_path = variant_dir / f"variante_{strategy}.json"
        variant = _load_model_if_exists(variant_path, AutomatisierungsGesamtkonzept)
        if variant is None:
            variant = run_automation_variant(
                artifacts,
                process_results,
                strategy=strategy,
                max_context_chars=max_context_chars,
                llm_model=llm_model,
                max_completion_tokens=_module_token_limit(module_tokens, "automation_variant", max_completion_tokens),
            )
            _save_model(variant_path, variant)
            print(f"[3/3] Gesamtkonzept: {strategy}")
        else:
            print(f"[3/3] Gesamtkonzept geladen: {strategy}")
        variants[strategy] = variant

    layout_dir = artifacts.output_dir / "03a_layoutplanung"
    layout_dir.mkdir(exist_ok=True)
    layouts: Dict[str, LayoutPlanerErgebnis] = {}
    for strategy, variant in variants.items():
        layout_path = layout_dir / f"layout_{strategy}.json"
        layout = _load_model_if_exists(layout_path, LayoutPlanerErgebnis)
        if layout is not None:
            try:
                _validate_layout_plan(variant, layout)
            except ValueError as exc:
                print(f"[RESUME] Existing layout ignored because it is inconsistent: {layout_path} ({exc})")
                layout = None
        if layout is None:
            layout = run_layout_planer(
                variant,
                max_context_chars=max_context_chars,
                llm_model=llm_model,
                max_completion_tokens=_module_token_limit(module_tokens, "layout_planer", max_completion_tokens),
            )
            _validate_layout_plan(variant, layout)
            _save_model(layout_path, layout)
            print(f"[layout_planer] Layoutplanung: {strategy}")
        else:
            print(f"[layout_planer] Layoutplanung geladen: {strategy}")
        layouts[strategy] = layout

    summary_path = artifacts.output_dir / "automation_planner_summary.md"
    summary_path.write_text(
        _build_summary(initial, variants),
        encoding="utf-8",
    )
    print(f"\nSummary: {summary_path}")

    return {
        "artifacts": artifacts,
        "initial_requirements": initial,
        "process_principles": process_results,
        "variants": variants,
        "layouts": layouts,
        "summary_path": summary_path,
    }


def load_session_artifacts(session_root: str | Path) -> AutomationPlannerArtifacts:
    root = Path(session_root).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Session root not found: {root}")

    assembly_name = _infer_assembly_name(root)
    sequence_run_dir = _latest_sequence_run_dir(root)
    output_dir = root / "automation_planner"

    return AutomationPlannerArtifacts(
        session_root=root,
        assembly_name=assembly_name,
        output_dir=output_dir,
        assembly_overview=_read_json(_require_one(root.glob("assembly_*_Overview_Enriched.json"), "assembly overview")),
        bom=_read_json(_require_one(root.glob("*_BOM_enriched.json"), "enriched BOM")),
        enriched_parts=_read_enriched_parts(root / "enriched_parts"),
        assembly_sequence=_read_json(sequence_run_dir / "assembly_sequence.json"),
        interaction_analysis=_read_json(sequence_run_dir / "interaction_analysis.json"),
        ffa_assessment=_read_json(root / "ffa_assessment" / "ffa_assessment.json"),
        ffa_report=_read_json(_require_one((root / "ffa_report").glob("*_ffa_report.json"), "FFA report")),
        additional_context_block=_read_text(root / "Agent_txt_files" / "additional_context_block.md"),
        sequence_run_dir=sequence_run_dir,
    )


def run_initial_requirements(
    artifacts: AutomationPlannerArtifacts,
    *,
    max_context_chars: int,
    llm_model: str,
    max_completion_tokens: int,
) -> InitialeAnforderungsklaerung:
    context = _bounded_json(
        {
            "assembly_name": artifacts.assembly_name,
            "assembly_sequence": artifacts.assembly_sequence,
            "ffa_report": artifacts.ffa_report,
            "ffa_assessment_separation_sources": _step_separation_sources(artifacts),
            "part_provision_hints": _part_provision_hints(artifacts),
            "additional_context_block": artifacts.additional_context_block,
        },
        max_context_chars,
    )
    return _invoke_structured(
        "automation_initial_requirements_system_v1",
        "automation_initial_requirements_human_v1",
        InitialeAnforderungsklaerung,
        context=context,
        llm_model=llm_model,
        max_completion_tokens=max_completion_tokens,
    )


def run_process_principles(
    artifacts: AutomationPlannerArtifacts,
    initial: InitialeAnforderungsklaerung,
    step_nr: int,
    *,
    user_feedback: str,
    max_context_chars: int,
    llm_model: str,
    max_completion_tokens: int,
) -> ProzessprinzipErgebnis:
    sequence_step = _find_step(artifacts.assembly_sequence, step_nr)
    requirement_step = _find_requirement_step(initial, step_nr)
    context = _bounded_json(
        {
            "assembly_name": artifacts.assembly_name,
            "montageschritt": sequence_step,
            "anforderungsklaerung": _model_to_dict(requirement_step),
            "ffa_report_step": _find_report_step(artifacts.ffa_report, step_nr),
            "ffa_assessment_step": _find_assessment_step(artifacts.ffa_assessment, step_nr),
            "interaction_analysis_step": _find_interaction_step(artifacts.interaction_analysis, step_nr),
            "basis_und_fuegeteile": _parts_for_step(artifacts, sequence_step),
            "nutzerfeedback": user_feedback,
        },
        max_context_chars,
    )
    return _invoke_structured(
        "automation_process_principles_system_v1",
        "automation_process_principles_human_v1",
        ProzessprinzipErgebnis,
        context=context,
        llm_model=llm_model,
        max_completion_tokens=max_completion_tokens,
    )


def run_automation_variant(
    artifacts: AutomationPlannerArtifacts,
    process_results: list[ProzessprinzipErgebnis],
    *,
    strategy: str,
    max_context_chars: int,
    llm_model: str,
    max_completion_tokens: int,
) -> AutomatisierungsGesamtkonzept:
    context = _bounded_json(
        {
            "strategy": strategy,
            "assembly_sequence": artifacts.assembly_sequence,
            "process_principles": [
                _select_strategy_principle(result, strategy)
                for result in process_results
            ],
        },
        max_context_chars,
    )
    return _invoke_structured(
        "automation_variant_generator_system_v1",
        "automation_variant_generator_human_v1",
        AutomatisierungsGesamtkonzept,
        context=context,
        strategy=strategy,
        llm_model=llm_model,
        max_completion_tokens=max_completion_tokens,
    )


def run_layout_planer(
    variant: AutomatisierungsGesamtkonzept,
    *,
    max_context_chars: int,
    llm_model: str,
    max_completion_tokens: int,
) -> LayoutPlanerErgebnis:
    """Plan station-local and overall coordinates for one automation variant."""
    context = _complete_bounded_json(
        {
            "varianten_id": variant.varianten_id,
            "strategie": variant.strategie,
            "stationen": [
                {
                    "station_nr": station.station_nr,
                    "zustand_baugruppe_vor_station": station.zustand_baugruppe_vor_station,
                    "ablaufbeschreibung": station.ablaufbeschreibung,
                    "zustand_baugruppe_nach_station": station.zustand_baugruppe_nach_station,
                    "equipment_station": _model_to_dict(station.equipment_station),
                }
                for station in variant.stationen
            ],
            "stationen_transfer": variant.stationen_transfer,
        },
        max_context_chars,
    )
    return _invoke_structured(
        "automation_layout_planer_system_v1",
        "automation_layout_planer_human_v1",
        LayoutPlanerErgebnis,
        context=context,
        llm_model=llm_model,
        max_completion_tokens=max_completion_tokens,
    )


def _invoke_structured(
    system_prompt_id: str,
    human_prompt_id: str,
    schema: Any,
    *,
    llm_model: str,
    max_completion_tokens: int,
    **format_vars: Any,
) -> Any:
    from langchain_core.messages import HumanMessage, SystemMessage
    from agent.tools import _get_img_describer_llm

    system_prompt = _render_prompt(system_prompt_id, **format_vars)
    human_prompt = _render_prompt(human_prompt_id, **format_vars)
    llm = _get_img_describer_llm(
        max_completion_tokens=max_completion_tokens,
        llm_model_override=llm_model,
    )
    structured_llm = llm.with_structured_output(schema)
    return structured_llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])


def _render_prompt(prompt_id: str, **kwargs: Any) -> str:
    from agent.prompt_store import get_prompt_template

    template = get_prompt_template(prompt_id)
    if not template:
        raise ValueError(f"Prompt not found: {prompt_id}")
    try:
        return template.format(**kwargs)
    except Exception as exc:
        raise ValueError(f"Could not render prompt {prompt_id}: {exc}") from exc


def _save_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_model_to_dict(model), indent=2, ensure_ascii=False), encoding="utf-8")


def _load_model_if_exists(path: Path, schema: Any) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = _read_json(path)
        if hasattr(schema, "model_validate"):
            return schema.model_validate(data)
        if hasattr(schema, "parse_obj"):
            return schema.parse_obj(data)
        return data
    except Exception as exc:
        print(f"[RESUME] Existing artifact ignored because it is invalid: {path} ({exc})")
        return None


def _module_token_limit(module_tokens: Dict[str, Any], key: str, fallback: int) -> int:
    try:
        return int(module_tokens.get(key) or fallback)
    except Exception:
        return int(fallback)


def _validate_layout_plan(
    variant: AutomatisierungsGesamtkonzept,
    layout: LayoutPlanerErgebnis,
) -> None:
    """Reject incomplete or renamed layout output before it reaches the renderer."""
    if layout.varianten_id != variant.varianten_id:
        raise ValueError(
            f"layout_planer changed varianten_id: {layout.varianten_id!r} != {variant.varianten_id!r}"
        )
    if layout.strategie != variant.strategie:
        raise ValueError(
            f"layout_planer changed strategie: {layout.strategie!r} != {variant.strategie!r}"
        )

    source_stations = {station.station_nr: station for station in variant.stationen}
    layout_stations = {station.station_nr: station for station in layout.stationen}
    if len(layout_stations) != len(layout.stationen):
        raise ValueError("layout_planer returned duplicate station layout entries")
    if set(layout_stations) != set(source_stations):
        raise ValueError(
            "layout_planer station coverage mismatch: "
            f"expected {sorted(source_stations)}, got {sorted(layout_stations)}"
        )

    station_coordinate_numbers = [item.station_nr for item in layout.station_coordinates]
    if len(set(station_coordinate_numbers)) != len(station_coordinate_numbers):
        raise ValueError("layout_planer returned duplicate station coordinates")
    if set(station_coordinate_numbers) != set(source_stations):
        raise ValueError(
            "layout_planer station coordinate coverage mismatch: "
            f"expected {sorted(source_stations)}, got {sorted(station_coordinate_numbers)}"
        )
    station_coordinate_pairs = [(item.x, item.y) for item in layout.station_coordinates]
    if len(set(station_coordinate_pairs)) != len(station_coordinate_pairs):
        raise ValueError("layout_planer returned duplicate station coordinate pairs")
    station_one = next(
        (item for item in layout.station_coordinates if item.station_nr == 1), None
    )
    if station_one is not None and (station_one.x, station_one.y) != (0, 0):
        raise ValueError("layout_planer must position station 1 at (0, 0)")

    for station_nr, source_station in source_stations.items():
        expected_names = sorted(item.name for item in source_station.equipment_station)
        actual_names = sorted(
            item.equipment_name for item in layout_stations[station_nr].equipment_coordinates
        )
        if actual_names != expected_names:
            missing = sorted(set(expected_names) - set(actual_names))
            extra = sorted(set(actual_names) - set(expected_names))
            raise ValueError(
                f"layout_planer equipment coverage mismatch in station {station_nr}; "
                f"missing={missing}, extra_or_renamed={extra}"
            )
        coordinate_pairs = [
            (item.x, item.y) for item in layout_stations[station_nr].equipment_coordinates
        ]
        if len(set(coordinate_pairs)) != len(coordinate_pairs):
            raise ValueError(
                f"layout_planer returned duplicate equipment coordinates in station {station_nr}"
            )


def _model_to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return {key: _model_to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_model_to_dict(item) for item in value]
    return value


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _require_one(candidates: Iterable[Path], label: str) -> Path:
    matches = sorted([path for path in candidates if path.is_file()], key=lambda path: path.name.lower())
    if not matches:
        raise FileNotFoundError(f"Could not find {label}")
    return matches[0]


def _infer_assembly_name(root: Path) -> str:
    reports = sorted((root / "ffa_report").glob("*_ffa_report.json"))
    if reports:
        return reports[0].name[: -len("_ffa_report.json")]
    step_files = sorted((root / "input").glob("*.STEP"))
    if step_files:
        return step_files[0].stem
    return root.name.split("_", 2)[-1]


def _latest_sequence_run_dir(root: Path) -> Path:
    runs = [path for path in root.glob("assembly_sequence_run*") if path.is_dir()]
    if not runs:
        raise FileNotFoundError(f"No assembly_sequence_run* folder found in {root}")

    def _run_number(path: Path) -> int:
        try:
            return int(path.name.replace("assembly_sequence_run", ""))
        except ValueError:
            return -1

    return sorted(runs, key=_run_number)[-1]


def _read_enriched_parts(parts_dir: Path) -> Dict[str, Dict[str, Any]]:
    parts: Dict[str, Dict[str, Any]] = {}
    for path in sorted(parts_dir.glob("*_Data_enriched*.json")):
        data = _read_json(path)
        part_id = str(data.get("part_id") or path.name.split("_Data_", 1)[0])
        if part_id not in parts or path.name.endswith("_merged.json"):
            parts[part_id] = data
    return parts


def _bounded_json(data: Dict[str, Any], max_chars: int) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[CONTEXT TRUNCATED]"


def _complete_bounded_json(data: Dict[str, Any], max_chars: int) -> str:
    """Serialize contexts that must remain complete for exact output coverage."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        raise ValueError(
            f"Complete layout_planer context has {len(text)} characters, exceeding "
            f"max_context_chars={max_chars}. Increase the configured limit; this context cannot be truncated."
        )
    return text


def _part_provision_hints(artifacts: AutomationPlannerArtifacts) -> Dict[str, Any]:
    hints = {}
    for part_id, data in artifacts.enriched_parts.items():
        hints[part_id] = {
            "part_name_guess": data.get("part_name_guess") or data.get("part_name"),
            "nature_of_provision_guess": _nested_get(data, "monopart_analysis", "nature_of_provision_guess"),
            "handling_implications": _nested_get(data, "monopart_analysis", "handling_implications"),
        }
    return hints


def _step_separation_sources(artifacts: AutomationPlannerArtifacts) -> list[Dict[str, Any]]:
    sources = []
    for step in artifacts.ffa_assessment.get("step_assessments", []):
        assessment = step.get("assessment") or {}
        separation = assessment.get("separation") or {}
        sources.append(
            {
                "step_id": step.get("step_id"),
                "step_description": step.get("step_description"),
                "joining_part_id": step.get("joining_part_id"),
                "nature_of_provision": separation.get("nature_of_provision"),
                "nature_of_provision_reasoning": separation.get("nature_of_provision_reasoning"),
                "separation_overall_ffa": [
                    item
                    for item in (assessment.get("overall_ffa") or [])
                    if str(item.get("subprocess", "")).lower() == "separation"
                ],
            }
        )
    return sources


def _find_step(sequence: Dict[str, Any], step_nr: int) -> Dict[str, Any]:
    for step in sequence.get("steps", []):
        if int(step.get("step_id", -1)) == int(step_nr):
            return step
    raise ValueError(f"Assembly sequence step not found: {step_nr}")


def _find_requirement_step(initial: InitialeAnforderungsklaerung, step_nr: int) -> Any:
    for step in initial.montageschritte:
        if step.montageschritt_nr == step_nr:
            return step
    raise ValueError(f"Initial requirement step not found: {step_nr}")


def _find_report_step(report: Dict[str, Any], step_nr: int) -> Dict[str, Any]:
    for step in report.get("steps", []):
        if int(step.get("step_id", -1)) == int(step_nr):
            return step
    return {}


def _find_assessment_step(assessment: Dict[str, Any], step_nr: int) -> Dict[str, Any]:
    for step in assessment.get("step_assessments", []):
        if int(step.get("step_id", -1)) == int(step_nr):
            return step
    return {}


def _find_interaction_step(interaction: Dict[str, Any], step_nr: int) -> Dict[str, Any]:
    candidates = interaction.get("step_interactions") or interaction.get("steps") or []
    if isinstance(candidates, dict):
        candidates = candidates.values()
    for step in candidates:
        if int(step.get("step_id", -1)) == int(step_nr):
            return step
    return {}


def _parts_for_step(artifacts: AutomationPlannerArtifacts, sequence_step: Dict[str, Any]) -> Dict[str, Any]:
    part_ids: list[str] = []
    for key in ("base_part", "joining_part"):
        value = sequence_step.get(key)
        if isinstance(value, list):
            part_ids.extend(str(item) for item in value)
        elif value:
            part_ids.append(str(value))
    return {part_id: artifacts.enriched_parts.get(part_id, {}) for part_id in sorted(set(part_ids))}


def _select_strategy_principle(result: ProzessprinzipErgebnis, strategy: str) -> Dict[str, Any]:
    for principle in result.prozessprinzipien:
        if principle.strategie == strategy:
            return {
                "montageschritt_nr": result.montageschritt_nr,
                "montageschritt_beschreibung": result.montageschritt_beschreibung,
                "basisteil": result.basisteil,
                "fuegeteil": result.fuegeteil,
                "prozessprinzip": _model_to_dict(principle),
            }
    raise ValueError(f"No {strategy} process principle for step {result.montageschritt_nr}")


def _nested_get(data: Dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _build_summary(
    initial: InitialeAnforderungsklaerung,
    variants: Dict[str, AutomatisierungsGesamtkonzept],
) -> str:
    lines = [
        "# Automatisierungsplaner Summary",
        "",
        f"Baugruppe: {initial.baugruppenname}",
        f"Montageschritte: {len(initial.montageschritte)}",
        "",
        "## Varianten",
    ]
    for strategy, variant in variants.items():
        lines.extend(
            [
                f"### {strategy}",
                f"- Varianten-ID: {variant.varianten_id}",
                f"- Montageschritte: {len(variant.montageablauf)}",
                f"- Stationen: {len(variant.stationen)}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"
