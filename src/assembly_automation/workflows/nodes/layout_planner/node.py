from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_layout_prompt
from .renderer import render_layout
from .structured_output import get_schema


def _validate_coverage(concept_path: str | Path, layout: Mapping[str, Any]) -> None:
    import json
    concept = json.loads(Path(concept_path).read_text(encoding="utf-8"))
    # Current synthesis emits one root-level consolidated equipment list.
    # Retain legacy extraction so layouts can still be regenerated for existing sessions.
    equipment = concept.get("equipment")
    if isinstance(equipment, list):
        expected = [item.get("name") for item in equipment if isinstance(item, dict)]
    else:
        expected = [item.get("name") for station in concept.get("stationen", [])
                    for item in station.get("equipment_station", []) if isinstance(item, dict)]
        expected += [item.get("name") for item in
                     (concept.get("parallelisierungskonzept", {}).get("parellization_equipment", []) or [])
                     if isinstance(item, dict)]
    expected_set = {str(name) for name in expected if name}
    rows = list(layout.get("equipment") or [])
    actual = [str(item.get("name")) for item in rows]
    if len(actual) != len(set(actual)):
        raise ValueError("Layout contains duplicate equipment names")
    if set(actual) != expected_set:
        raise ValueError(f"Layout equipment coverage mismatch; missing={sorted(expected_set-set(actual))}, extra={sorted(set(actual)-expected_set)}")
    # Coordinate collisions are a layout-quality issue, not an artifact-integrity
    # failure. Keep every item and let the deterministic renderer visualize the
    # overlap so the user can review or revise it.


def run_layout_planner(*, artifacts: Mapping[str, Any], settings: Mapping[str, Any],
                       llm_profiles: Mapping[str, Any], context: Mapping[str, Any] | None = None,
                       output_path: str | Path | None = None, llm: Any = None) -> dict[str, Any]:
    response = run_llm_node(
        node_id="layout_planner", artifacts=artifacts, settings=settings,
        llm_profiles=llm_profiles, build_payload=build_layout_prompt,
        get_schema=get_schema, context=context, output_path=output_path, llm=llm)
    if output_path is not None and response.get("status") == "complete":
        _validate_coverage(artifacts["automation_concept"], response["result"])
        svg = Path(output_path).with_name("layout.svg")
        response["rendering"] = render_layout(response["result"], svg)
    return response
