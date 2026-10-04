"""Resolve user-facing semantic targets without giving the LLM filesystem access."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ..artifacts import ArtifactEditor


@dataclass(frozen=True)
class ResolvedTarget:
    requested: str
    artifact: str
    entity_id: str
    revision_id: str | None
    label: str
    current: dict[str, Any]
    editable_fields: tuple[str, ...]
    expected_sha256: str


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _part_id(editor: ArtifactEditor, requested: str) -> str:
    raw = requested.split(":", 1)[1] if requested.casefold().startswith("part:") else requested
    bom = editor.read("bom")
    ids = [part.get("part_id") for part in bom.get("parts", []) if isinstance(part, dict)
           and isinstance(part.get("part_id"), str)]
    exact = [part_id for part_id in ids if part_id.casefold() == raw.casefold()]
    matches = exact or [part_id for part_id in ids if _canonical(part_id) == _canonical(raw)]
    if len(matches) != 1:
        raise ValueError(f"Expected one part matching {requested!r}, found {len(matches)}")
    return matches[0]


def resolve_target(editor: ArtifactEditor, target: str) -> ResolvedTarget:
    requested = target.strip()
    if not requested:
        raise ValueError("change_artifact target cannot be empty")
    normalized = requested.casefold().replace(" ", "_")
    revision_id = None
    if normalized in {"assembly", "assembly_overview"}:
        artifact, entity_id, label = "assembly_overview", "assembly", "assembly overview"
    elif normalized in {"sequence", "assembly_sequence"}:
        artifact, entity_id, label = "sequence", "sequence", "assembly sequence"
    elif (match := re.fullmatch(r"step[:_ ]?0*(\d+)", requested, re.IGNORECASE)):
        step_id = int(match.group(1))
        artifact, entity_id, label = "sequence", f"step:{step_id}", f"sequence step {step_id}"
    else:
        part_id = _part_id(editor, requested)
        artifact, entity_id, label = "bom", part_id, f"part {part_id}"
    path = editor.resolve(artifact, revision_id=revision_id)
    document = editor.read(artifact, revision_id=revision_id)
    current, allowed = editor.field_target(artifact, document, entity_id)
    return ResolvedTarget(
        requested=requested, artifact=artifact, entity_id=entity_id,
        revision_id=revision_id, label=label, current=dict(current),
        editable_fields=tuple(sorted(allowed)), expected_sha256=editor.content_hash(path))
