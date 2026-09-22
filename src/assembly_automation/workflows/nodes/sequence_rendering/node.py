"""Deterministic sequence-rendering workflow node."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from assembly_automation.stepparser.io.step_loader import load_step
from assembly_automation.stepparser.rendering.color_generator import assign_colors
from assembly_automation.workflows.nodes.sequence_generation.validation import validate_sequence

from .inputs import build_step_states, load_mapping, unwrap_sequence
from .collage import create_step_collages
from .renderer import SequenceRenderer
from .settings import SequenceRenderingSettings


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _valid_color(value) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(channel) is int and 0 <= channel <= 255 for channel in value))


def _apply_bom_colors(loaded, bom: Mapping[str, Any], color_mode: str) -> None:
    definitions = {item.part_id: item for item in loaded.definitions}
    instances = {item.instance_id: item for item in loaded.instances}
    assigned = False
    for part in bom.get("parts", []):
        color = part.get("color") if isinstance(part, Mapping) else None
        if isinstance(part, Mapping) and part.get("part_id") in definitions and _valid_color(color):
            definitions[part["part_id"]].color = list(color)
            assigned = True
    for item in bom.get("instances", []):
        color = item.get("color") if isinstance(item, Mapping) else None
        instance = instances.get(item.get("instance_id")) if isinstance(item, Mapping) else None
        if instance is not None and _valid_color(color):
            instance.color = list(color)
        elif instance is not None and definitions[instance.part_id].color:
            instance.color = list(definitions[instance.part_id].color)
    if not assigned or any(not item.color for item in loaded.instances):
        assign_colors(loaded.definitions, loaded.instances, color_mode)


def run_sequence_rendering(
    *,
    step_file: str | Path,
    sequence: Mapping[str, Any] | str | Path,
    bom: Mapping[str, Any] | str | Path,
    output_dir: str | Path,
    settings: SequenceRenderingSettings | Mapping[str, Any] | None = None,
    progress: Callable[[str, int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Render sequence steps from explicit artifacts and return a manifest."""
    configured = (settings if isinstance(settings, SequenceRenderingSettings)
                  else SequenceRenderingSettings.from_mapping(settings))
    if not configured.enabled:
        return {"status": "disabled", "output_dir": str(Path(output_dir).resolve()),
                "artifact": None, "images": []}
    source = Path(step_file).resolve(strict=True)
    target = Path(output_dir).resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Use an empty sequence-rendering output directory: {target}")
    target.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    sequence_data = unwrap_sequence(sequence)
    bom_data = load_mapping(bom, "BOM")
    validate_sequence(sequence_data, bom_data)
    bom_ids = {item["instance_id"] for item in bom_data["instances"]}
    states = build_step_states(sequence_data, bom_ids)

    loaded = load_step(source)
    loaded_ids = {item.instance_id for item in loaded.instances}
    if loaded_ids != bom_ids:
        raise ValueError(f"STEP/BOM instance IDs differ; missing in STEP: {sorted(bom_ids - loaded_ids)}; "
                         f"missing in BOM: {sorted(loaded_ids - bom_ids)}")
    _apply_bom_colors(loaded, bom_data, configured.color_mode)
    renderer = SequenceRenderer(loaded, configured)
    images = renderer.render(states, target, progress)
    collages = create_step_collages(images, target, configured.collage, progress)
    manifest = {
        "status": "partial" if renderer.section_fallbacks else "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {"step_file": source.name,
                  "step_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "assembly_name": sequence_data.get("assembly_name")},
        "settings": configured.to_dict(),
        "steps": [{"step_id": state["step"]["step_id"],
                   "belongs_to": state["step"].get("belongs_to"),
                   "joining_instance_ids": state["joining"],
                   "before_instance_ids": state["before"],
                   "after_instance_ids": state["after"]} for state in states],
        "images": images,
        "collages": collages,
        "section_cut_cache_entries": renderer.section_cache_entries,
        "section_cut_fallbacks": renderer.section_fallbacks,
        "duration_seconds": time.perf_counter() - started,
    }
    manifest_path = target / "rendering_summary.json"
    _write_json(manifest_path, manifest)
    return {"status": manifest["status"], "output_dir": str(target),
            "artifact": str(manifest_path), "images": images, "collages": collages,
            "rendered_steps": len(states)}
