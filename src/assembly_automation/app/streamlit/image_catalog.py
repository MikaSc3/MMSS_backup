"""Bounded image indexing for the visual workspace."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .session_view import SessionSnapshot, safe_artifact_path


@dataclass(frozen=True)
class ImageEntry:
    path: Path
    group: str
    label: str
    category: str
    part_id: str | None = None
    step_id: str | None = None


def _images(paths: Iterable[Path], *, group: str, category: str,
            part_id: str | None = None) -> list[ImageEntry]:
    return [ImageEntry(path, group, path.stem.replace("_", " "), category, part_id)
            for path in sorted(paths) if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}]


def build_image_catalog(snapshot: SessionSnapshot) -> list[ImageEntry]:
    root = snapshot.root
    entries: list[ImageEntry] = []
    layout = snapshot.artifact("layout_rendering")
    if layout is not None and layout.exists and layout.path.suffix.lower() == ".svg":
        entries.append(ImageEntry(layout.path, "Equipment layout", "Equipment layout", "layout"))
    assembly = root / "02_preprocessing/images/assembly"
    if assembly.is_dir():
        entries += _images(assembly.glob("*"), group="Assembly", category="assembly")
    parts = root / "02_preprocessing/images/parts"
    if parts.is_dir():
        for folder in sorted(path for path in parts.iterdir() if path.is_dir()):
            entries += _images(folder.glob("*"), group=f"Part · {folder.name}",
                               category="part", part_id=folder.name)
    active = snapshot.active_revision
    if active:
        rendering_root = root / "05_sequence/revisions" / active / "renderings"
        summary = rendering_root / "rendering_summary.json"
        candidates: list[ImageEntry] = []
        if summary.is_file():
            try:
                payload = json.loads(summary.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            records = []
            if isinstance(payload, dict):
                overview = payload.get("sequence_overview")
                collages = list(payload.get("collages") or [])
                if isinstance(overview, dict):
                    collages = [item for item in collages if item != overview]
                    records = [overview, *collages, *list(payload.get("images") or [])]
                else:
                    records = [*collages, *list(payload.get("images") or [])]
            for record in records:
                if isinstance(record, str):
                    record = {"path": record}
                if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                    continue
                value = record["path"]
                candidate = safe_artifact_path(root, value)
                if candidate is None or not candidate.is_file():
                    local = (rendering_root / value).resolve()
                    try:
                        local.relative_to(root)
                        candidate = local
                    except ValueError:
                        candidate = None
                if candidate and candidate.is_file():
                    step = record.get("step_id")
                    category = str(record.get("category") or "render")
                    # Rendering summaries created before sequence overview support
                    # did not classify their per-step collages. Infer the stable
                    # category from the established filename so resumed sessions
                    # receive the same visual grouping as new runs.
                    if category == "render" and candidate.name.startswith("collage_step_"):
                        category = "step_collage"
                    view = str(record.get("view") or "collage")
                    state = str(record.get("state") or "")
                    label = ("Assembly sequence overview"
                             if category == "sequence_overview" else
                             " · ".join(part for part in
                                        [f"Step {step}" if step is not None else None,
                                         category.replace("_", " ").title(),
                                         view.upper(), state.title() or None] if part))
                    group = (f"Sequence overview · {active}"
                             if category == "sequence_overview" else
                             f"Sequence steps · {active}"
                             if category == "step_collage" else
                             f"Sequence evidence · {active}")
                    candidates.append(ImageEntry(candidate, group, label,
                                                 category, step_id=str(step) if step is not None else None))
        if not candidates and rendering_root.is_dir():
            candidates = _images(rendering_root.glob("*.png"), group=f"Sequence evidence · {active}",
                                 category="sequence")
        seen: set[Path] = set()
        for item in candidates:
            if item.path not in seen:
                entries.append(item)
                seen.add(item.path)
    return entries
