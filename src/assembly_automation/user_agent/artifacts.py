"""Allowlisted session artifact reading and validated merge-patch editing."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from hashlib import sha256
from pathlib import Path
import shutil
from typing import Any, Mapping

from assembly_automation.workflows.definitions.app_v3 import WorkflowPaths
from assembly_automation.workflows.nodes.assembly_analysis.structured_output import AssemblyAnalysis
from assembly_automation.workflows.nodes.monopart_analysis.structured_output import SinglePartAnalysis
from assembly_automation.workflows.nodes.sequence_generation.structured_output import AssemblySequence
from assembly_automation.workflows.nodes.sequence_generation.validation import validate_sequence

from .storage import atomic_write_json


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Artifact must contain a JSON object: {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(value))


def _merge_patch(document: Any, patch: Any) -> Any:
    if not isinstance(patch, Mapping):
        return patch
    result = dict(document) if isinstance(document, Mapping) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


def validate_bom(document: Mapping[str, Any]) -> None:
    parts, instances = document.get("parts"), document.get("instances")
    if not isinstance(parts, list) or not isinstance(instances, list):
        raise ValueError("BOM requires parts and instances lists")
    part_ids = [item.get("part_id") for item in parts if isinstance(item, Mapping)]
    if len(part_ids) != len(parts) or any(not isinstance(item, str) or not item for item in part_ids):
        raise ValueError("Every BOM part requires a nonempty part_id")
    if len(set(part_ids)) != len(part_ids):
        raise ValueError("BOM part_id values must be unique")
    instance_ids = [item.get("instance_id") for item in instances if isinstance(item, Mapping)]
    if len(instance_ids) != len(instances) or len(set(instance_ids)) != len(instance_ids):
        raise ValueError("Every BOM instance requires a unique instance_id")
    unknown = sorted({item.get("part_id") for item in instances if isinstance(item, Mapping)} - set(part_ids))
    if unknown:
        raise ValueError(f"BOM instances reference unknown parts: {unknown}")


class ArtifactEditor:
    EDITABLE = {"assembly_overview", "bom", "sequence"}

    def __init__(self, session_root: str | Path):
        self.paths = WorkflowPaths(Path(session_root).resolve())
        self.history = self.paths.history_root / "artifact_edits"

    def resolve(self, artifact: str, *, revision_id: str | None = None) -> Path:
        if artifact == "assembly_overview":
            revision_id = revision_id or self.paths.active_revision("assembly")
            return self.paths.assembly(revision_id) / "assembly_overview.json"
        if artifact == "bom":
            revision_id = revision_id or self.paths.active_revision("monoparts")
            return self.paths.monoparts(revision_id) / "bom.json"
        if artifact == "sequence":
            revision_id = revision_id or self._active_revision()
            if not revision_id:
                raise ValueError("No active sequence revision")
            return self.paths.revision(revision_id) / "assembly_sequence.json"
        if artifact == "report":
            revision_id = revision_id or self._active_revision()
            if not revision_id:
                raise ValueError("No active report revision")
            return self.paths.reports(revision_id) / "report.json"
        raise ValueError(f"Unknown artifact {artifact!r}")

    def _active_revision(self) -> str | None:
        manifest = self.paths.root / "manifest.json"
        return _read(manifest).get("active_sequence_revision") if manifest.is_file() else None

    def read(self, artifact: str, *, revision_id: str | None = None,
             json_path: str = "") -> Any:
        value: Any = _read(self.resolve(artifact, revision_id=revision_id))
        for segment in [item for item in json_path.split(".") if item]:
            if isinstance(value, list) and segment.isdigit():
                value = value[int(segment)]
            elif isinstance(value, Mapping) and segment in value:
                value = value[segment]
            else:
                raise ValueError(f"JSON path does not exist: {json_path}")
        return value

    def edit(self, artifact: str, patch: Mapping[str, Any], *, reason: str,
             revision_id: str | None = None) -> dict[str, Any]:
        if artifact not in self.EDITABLE:
            raise ValueError(f"Artifact is read-only: {artifact}")
        if not reason.strip():
            raise ValueError("Artifact edits require a reason")
        path = self.resolve(artifact, revision_id=revision_id)
        after = _merge_patch(_read(path), patch)
        self._validate(artifact, after)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.history / artifact / f"{stamp}_{path.name}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        _write(path, after)
        _write(backup.with_suffix(".audit.json"),
               {"artifact": artifact, "active_path": str(path),
                "backup_path": str(backup), "reason": reason.strip(), "patch": patch})
        return {"artifact": artifact, "path": str(path), "backup": str(backup)}

    @staticmethod
    def content_hash(path: Path) -> str:
        return sha256(path.read_bytes()).hexdigest()

    def edit_fields(self, artifact: str, *, entity_id: str, changes: Mapping[str, Any],
                    expected_sha256: str, reason: str,
                    revision_id: str | None = None) -> dict[str, Any]:
        """Edit allowlisted descriptive leaves selected by stable domain ID."""
        path = self.resolve(artifact, revision_id=revision_id)
        actual_hash = self.content_hash(path)
        if actual_hash != expected_sha256:
            raise RuntimeError("Artifact changed after the editor was opened; reload before saving")
        document = _read(path)
        target, allowed = self.field_target(artifact, document, entity_id)
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise ValueError(f"Fields are read-only or unknown: {unknown}")
        if not changes:
            raise ValueError("No field changes were supplied")
        for field, value in changes.items():
            if isinstance(value, str):
                if not value.strip():
                    raise ValueError(f"{field} must be nonempty text")
                target[field] = value.strip()
            elif isinstance(value, list) and value and all(
                    isinstance(item, str) and item.strip() for item in value):
                target[field] = [item.strip() for item in value]
            else:
                raise ValueError(f"{field} must be nonempty text or list of text")
        self._validate(artifact, document)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.history / artifact / f"{stamp}_{path.name}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        _write(path, document)
        if artifact == "bom":
            parts = document.get("parts", [])
            match = next((part for part in parts
                          if isinstance(part, dict) and part.get("part_id") == entity_id), None)
            analysis = match.get("part_analysis") if isinstance(match, dict) else None
            if isinstance(analysis, dict):
                part_path = path.parent / "parts" / f"{entity_id}.json"
                part_backup = self.history / artifact / f"{stamp}_{part_path.name}"
                if part_path.is_file():
                    shutil.copy2(part_path, part_backup)
                _write(part_path, analysis)
        _write(backup.with_suffix(".audit.json"),
               {"artifact": artifact, "entity_id": entity_id, "active_path": str(path),
                "backup_path": str(backup), "reason": reason.strip(),
                "expected_sha256": expected_sha256, "changes": dict(changes)})
        return {"artifact": artifact, "entity_id": entity_id, "path": str(path),
                "backup": str(backup), "sha256": self.content_hash(path)}

    @staticmethod
    def field_target(artifact: str, document: dict[str, Any],
                     entity_id: str) -> tuple[dict[str, Any], set[str]]:
        if artifact == "assembly_overview":
            return document, {"assembly_description", "partslist", "assembly_name_guess",
                              "primary_function"}
        if artifact == "bom":
            matches = [part for part in document.get("parts", [])
                       if isinstance(part, dict) and part.get("part_id") == entity_id]
            if len(matches) != 1:
                raise ValueError(f"Expected one BOM part {entity_id!r}, found {len(matches)}")
            target = matches[0].get("part_analysis")
            if not isinstance(target, dict):
                raise ValueError(f"Part {entity_id!r} has no part_analysis")
            return target, {"part_identification", "part_name_guess",
                            "material_and_mechanical_behavior", "bulk_behavior",
                            "magazine_behavior", "nature_of_provision_guess",
                            "geometric_characteristics", "gripping_analysis",
                            "handling_implications", "intrinsic_summary"}
        if artifact == "sequence":
            if entity_id.startswith("step:"):
                step_id = int(entity_id.split(":", 1)[1])
                matches = [step for step in document.get("steps", [])
                           if isinstance(step, dict) and step.get("step_id") == step_id]
                if len(matches) != 1:
                    raise ValueError(f"Expected one sequence step {step_id}, found {len(matches)}")
                return matches[0], {"step_description", "belongs_to", "joining_process"}
            return document, {"assembly_name", "assembly_description", "sequence_rationale",
                              "sequence_notation"}
        raise ValueError(f"Artifact does not support field editing: {artifact}")

    def _validate(self, artifact: str, document: Mapping[str, Any]) -> None:
        if artifact == "assembly_overview":
            AssemblyAnalysis.model_validate(document)
        elif artifact == "bom":
            validate_bom(document)
            for part in document.get("parts", []):
                analysis = part.get("part_analysis") if isinstance(part, Mapping) else None
                if analysis is not None:
                    SinglePartAnalysis.model_validate(analysis)
        elif artifact == "sequence":
            AssemblySequence.model_validate(document)
            validate_sequence(document, _read(self.paths.enriched_bom))
