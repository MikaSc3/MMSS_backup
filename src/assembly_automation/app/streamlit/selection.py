"""Shared selection identity for linked visual and structured panes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OUTPUT_LABELS = {
    "assembly": "Assembly analysis",
    "part": "Monopart analysis",
    "sequence": "Assembly sequence",
    "interaction": "Interaction analysis",
    "ffa": "FfA analysis",
    "automation_idea": "Automation idea",
    "detailed_plans": "Detailed step plans",
    "automation_concept": "Automation concept",
    "layout": "Equipment layout",
    "cost_estimate": "Cost estimate",
}

SCOPE_ARTIFACTS = {
    "assembly": "assembly_overview",
    "part": "enriched_bom",
    "sequence": "assembly_sequence",
    "interaction": "interaction_analysis",
    "ffa": "ffa_assessment",
    "automation_idea": "automation_idea",
    "detailed_plans": "detailed_step_plans",
    "automation_concept": "automation_concept",
    "layout": "layout",
    "cost_estimate": "cost_estimate",
}


@dataclass(frozen=True)
class SelectionContext:
    scope: str
    entity_id: str = ""
    revision_id: str = ""
    step_id: int | None = None
    group: str = ""

    @property
    def key(self) -> str:
        return ":".join((self.scope, self.entity_id, self.revision_id,
                         str(self.step_id or "")))


def available_output_scopes(snapshot: Any) -> list[str]:
    """Return product outputs in their stable workflow order."""
    if snapshot is None:
        return []
    result = []
    for scope, artifact_id in SCOPE_ARTIFACTS.items():
        artifact = snapshot.artifact(artifact_id)
        if artifact is not None and artifact.exists and artifact.data is not None:
            result.append(scope)
    return result


def entity_selections(snapshot: Any, scope: str) -> list[tuple[str, SelectionContext]]:
    """Build the optional part/step level below one product output."""
    revision = snapshot.active_revision or "" if snapshot else ""
    if snapshot is None:
        return []
    if scope == "assembly":
        return [(OUTPUT_LABELS[scope], SelectionContext(scope, group="Assembly"))]
    if scope == "sequence":
        return [(OUTPUT_LABELS[scope], SelectionContext(scope, revision_id=revision))]
    if scope in {"automation_idea", "automation_concept", "layout", "cost_estimate"}:
        return [(OUTPUT_LABELS[scope], SelectionContext(scope, group="Automation planning"))]
    if scope == "detailed_plans":
        artifact = snapshot.artifact("detailed_step_plans")
        steps = artifact.data.get("steps", []) if artifact and isinstance(artifact.data, dict) else []
        result = []
        for item in steps:
            if not isinstance(item, dict) or item.get("montageschritt_nr") is None:
                continue
            step_id = int(item["montageschritt_nr"])
            description = str(item.get("montageschritt_beschreibung") or "").strip()
            short = description if len(description) <= 72 else description[:69].rstrip() + "…"
            label = f"Step {step_id} · {short}" if short else f"Step {step_id}"
            result.append((label, SelectionContext(scope, entity_id=f"step:{step_id}",
                                                    step_id=step_id,
                                                    group="Automation planning")))
        return result
    if scope == "part":
        artifact = snapshot.artifact("enriched_bom")
        parts = artifact.data.get("parts", []) if artifact and isinstance(artifact.data, dict) else []
        result = []
        for part in parts:
            if not isinstance(part, dict) or not part.get("part_id"):
                continue
            part_id = str(part["part_id"])
            analysis = part.get("part_analysis") if isinstance(part.get("part_analysis"), dict) else {}
            name = analysis.get("part_name_guess") or part.get("name")
            label = f"{part_id} · {name}" if name else part_id
            quantity = part.get("quantity")
            quantity_label = f"Qty. {quantity}" if isinstance(quantity, int) else "Qty. —"
            label = " · ".join(item for item in (part_id, str(name) if name else "", quantity_label)
                               if item)
            result.append((label, SelectionContext(scope, entity_id=part_id,
                                                    group=f"Part · {part_id}")))
        return result
    artifact_id = "interaction_analysis" if scope == "interaction" else "ffa_assessment"
    artifact = snapshot.artifact(artifact_id)
    steps = artifact.data.get("steps", []) if artifact and isinstance(artifact.data, dict) else []
    result = []
    for item in steps:
        step = item.get("step") if isinstance(item, dict) else None
        if not isinstance(step, dict) or step.get("step_id") is None:
            continue
        step_id = int(step["step_id"])
        description = str(step.get("step_description") or "").strip()
        short = description if len(description) <= 72 else description[:69].rstrip() + "…"
        label = f"Step {step_id} · {short}" if short else f"Step {step_id}"
        result.append((label, SelectionContext(scope, entity_id=f"step:{step_id}",
                                                revision_id=revision, step_id=step_id)))
    return result
