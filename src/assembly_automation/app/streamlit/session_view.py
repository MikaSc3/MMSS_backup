"""Read-only, disk-backed view of one workflow session."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def safe_artifact_path(root: Path, relative: str) -> Path | None:
    """Resolve a manifest artifact and reject paths outside the session."""
    if not relative:
        return None
    supplied = Path(relative)
    target = supplied.resolve() if supplied.is_absolute() else (root / supplied).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


@dataclass(frozen=True)
class ArtifactView:
    artifact_id: str
    relative_path: str
    path: Path
    exists: bool
    data: Any = None


@dataclass(frozen=True)
class SessionSnapshot:
    root: Path
    session_id: str
    workflow_status: str
    checkpoint: str
    active_revision: str | None
    approved_revision: str | None
    stale: Mapping[str, bool]
    messages: tuple[dict[str, str], ...]
    artifacts: Mapping[str, ArtifactView] = field(default_factory=dict)
    stages: Mapping[str, Any] = field(default_factory=dict)
    updated_at: str | None = None

    def artifact(self, artifact_id: str) -> ArtifactView | None:
        return self.artifacts.get(artifact_id)


def _checkpoint(manifest: Mapping[str, Any], state: Mapping[str, Any],
                planning: Mapping[str, Any]) -> str:
    planning_status = planning.get("status")
    if planning_status in {"planning_idea", "awaiting_idea_review", "planning_steps",
                           "awaiting_concept_review", "awaiting_layout_review",
                           "awaiting_cost_review"}:
        return str(planning_status)
    if manifest.get("status") == "draft":
        return "awaiting_upload"
    if manifest.get("status") == "complete":
        return "complete"
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    if any(isinstance(value, dict) and value.get("status") == "failed" for value in stages.values()):
        return "failed"
    approved = state.get("approved_sequence_revision")
    active = state.get("active_sequence_revision") or manifest.get("active_sequence_revision")
    stale = state.get("stale") if isinstance(state.get("stale"), dict) else {}
    if approved:
        return "sequence_approved"
    if active and not stale.get("sequence", False):
        return "awaiting_sequence_approval"
    if "bom_merge" in stages and stages["bom_merge"].get("status") == "complete":
        return "awaiting_sequence_generation"
    if "assembly_analysis" in stages and stages["assembly_analysis"].get("status") == "complete":
        return "awaiting_bom_review"
    if "step_preprocessing" in stages and stages["step_preprocessing"].get("status") == "complete":
        return "awaiting_assembly_review"
    return "preparing"


def load_session_snapshot(session_root: str | Path) -> SessionSnapshot:
    root = Path(session_root).resolve(strict=True)
    manifest = _read_json(root / "manifest.json", {})
    state = _read_json(root / "09_user_agent/state.json", {})
    planning = _read_json(root / "08_planning/planning_manifest.json", {})
    messages = _read_json(root / "09_user_agent/conversation.json", [])
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(state, dict):
        state = {}
    if not isinstance(planning, dict):
        planning = {}
    if not isinstance(messages, list):
        messages = []
    artifact_views: dict[str, ArtifactView] = {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    planning_artifacts = (planning.get("artifacts")
                          if isinstance(planning.get("artifacts"), dict) else {})
    artifacts = {**artifacts, **planning_artifacts}
    for artifact_id, relative in artifacts.items():
        if not isinstance(relative, str):
            continue
        path = safe_artifact_path(root, relative)
        if path is None:
            continue
        data = _read_json(path, None) if path.suffix.lower() == ".json" and path.is_file() else None
        artifact_views[str(artifact_id)] = ArtifactView(str(artifact_id), relative, path,
                                                        path.exists(), data)
    cleaned_messages = tuple(
        {"role": str(item.get("role", "assistant")), "content": str(item.get("content", ""))}
        for item in messages if isinstance(item, dict)
    )
    active = state.get("active_sequence_revision") or manifest.get("active_sequence_revision")
    return SessionSnapshot(
        root=root,
        session_id=str(manifest.get("session_id") or root.name),
        workflow_status=str(manifest.get("status") or "new"),
        checkpoint=_checkpoint(manifest, state, planning),
        active_revision=str(active) if active else None,
        approved_revision=(str(state["approved_sequence_revision"])
                           if state.get("approved_sequence_revision") else None),
        stale={str(k): bool(v) for k, v in (state.get("stale") or {}).items()},
        messages=cleaned_messages,
        artifacts=artifact_views,
        stages=manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {},
        updated_at=manifest.get("updated_at"),
    )
