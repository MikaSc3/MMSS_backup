"""Small, typed projections used by the structured-results pane."""

from __future__ import annotations

from typing import Any, Mapping

from .session_view import SessionSnapshot


LABELS = {
    "assembly_overview": "Assembly analysis",
    "enriched_bom": "Bill of materials",
    "bom": "Raw BOM",
    "assembly_sequence": "Assembly sequence",
    "interaction_analysis": "Interaction analysis",
    "ffa_assessment": "FfA assessment",
    "ffa_scores": "FfA scores",
    "report": "Final report",
    "spatial_relations": "Spatial relations",
    "interlocking": "Interlocking",
    "automation_idea": "Automation idea",
    "detailed_step_plans": "Detailed step plans",
    "automation_concept": "Automation concept",
    "layout": "Equipment layout",
    "cost_estimate": "Cost estimate",
}


def json_artifacts(snapshot: SessionSnapshot) -> list[tuple[str, str, Any]]:
    result = []
    for key, artifact in snapshot.artifacts.items():
        if artifact.exists and artifact.data is not None:
            result.append((key, LABELS.get(key, key.replace("_", " ").title()), artifact.data))
    return result


def artifact_metrics(artifact_id: str, data: Any) -> dict[str, str | int | float]:
    if not isinstance(data, Mapping):
        return {}
    metrics: dict[str, str | int | float] = {}
    if artifact_id in {"bom", "enriched_bom"}:
        metrics["Parts"] = len(data.get("parts") or [])
        metrics["Instances"] = len(data.get("instances") or [])
    elif artifact_id == "assembly_sequence":
        metrics["Steps"] = len(data.get("steps") or data.get("assembly_steps") or [])
    elif artifact_id in {"interaction_analysis", "ffa_assessment", "ffa_scores"}:
        metrics["Steps"] = len(data.get("steps") or data.get("step_assessments") or [])
    elif artifact_id == "detailed_step_plans":
        metrics["Steps"] = len(data.get("steps") or [])
    elif artifact_id == "automation_concept":
        if isinstance(data.get("equipment"), list):
            metrics["Equipment"] = len(data["equipment"])
        else:
            metrics["Stations"] = len(data.get("stationen") or [])
    elif artifact_id == "layout":
        metrics["Equipment"] = len(data.get("equipment") or [])
    elif artifact_id == "cost_estimate":
        metrics["Priced subtotal"] = data.get("priced_subtotal", 0)
        metrics["Unpriced"] = len(data.get("unpriced_equipment") or [])
    return metrics

