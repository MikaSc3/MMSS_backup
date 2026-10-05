"""Resolve a named session artifact without exposing filesystem paths to the LLM."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactEditor


@dataclass(frozen=True)
class ResolvedTarget:
    requested: str
    artifact: str
    revision_id: str | None
    label: str
    path: Path
    current: dict[str, Any]
    expected_sha256: str


ALIASES = {
    "assembly": "assembly_overview",
    "assembly_context": "assembly_overview",
    "assembly_overview": "assembly_overview",
    "bom": "bom",
    "parts": "bom",
    "monoparts": "bom",
    "sequence": "sequence",
    "assembly_sequence": "sequence",
    "interaction": "interaction_analysis",
    "interaction_analysis": "interaction_analysis",
    "ffa": "ffa_assessment",
    "ffa_assessment": "ffa_assessment",
    "ffa_scores": "ffa_scores",
    "report": "report",
    "ffa_report": "report",
    "automation_idea": "automation_idea",
    "detailed_step_plans": "detailed_step_plans",
    "automation_concept": "automation_concept",
    "layout": "layout",
    "cost": "cost_estimate",
    "cost_estimate": "cost_estimate",
}


def resolve_target(editor: ArtifactEditor, artifact: str,
                   revision_id: str = "") -> ResolvedTarget:
    """Resolve one complete active (or explicitly versioned) JSON artifact."""
    requested = artifact.strip()
    if not requested:
        raise ValueError("change_artifact artifact cannot be empty")
    normalized = requested.casefold().replace(" ", "_")
    canonical = ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(
            f"Unknown artifact {artifact!r}; supported artifacts: "
            f"{', '.join(sorted(set(ALIASES.values())))}")
    revision = revision_id.strip() or None
    path = editor.resolve(canonical, revision_id=revision)
    document = editor.read(canonical, revision_id=revision)
    return ResolvedTarget(
        requested=requested, artifact=canonical, revision_id=revision,
        label=canonical.replace("_", " "), path=path, current=document,
        expected_sha256=editor.content_hash(path))
