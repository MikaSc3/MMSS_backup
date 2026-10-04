"""Deterministically enrich a STEP BOM with one analysis per unique part."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _read_json(value: str | Path | Mapping[str, Any], label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        data = dict(value)
    else:
        data = json.loads(Path(value).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return data


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_bom_merge(
    *,
    bom: str | Path | Mapping[str, Any],
    part_analyses: Mapping[str, str | Path | Mapping[str, Any]],
    output_path: str | Path | None = None,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach node results to BOM definitions while leaving instances intact."""
    settings = dict(settings or {})
    unknown_settings = set(settings) - {"enabled", "require_all_parts"}
    if unknown_settings:
        raise ValueError(f"Unknown bom_merge settings: {sorted(unknown_settings)}")
    if settings.get("enabled", True) is not True:
        return {"status": "disabled", "artifact": None}
    require_all = settings.get("require_all_parts", True)
    if type(require_all) is not bool:
        raise ValueError("bom_merge.require_all_parts must be boolean")

    base = _read_json(bom, "bom")
    parts = base.get("parts")
    instances = base.get("instances")
    if not isinstance(parts, list) or not isinstance(instances, list):
        raise ValueError("BOM requires parts and instances lists")
    part_ids = [part.get("part_id") for part in parts if isinstance(part, dict)]
    if len(part_ids) != len(parts) or any(not isinstance(part_id, str) or not part_id for part_id in part_ids):
        raise ValueError("Every BOM part requires a nonempty part_id")
    if len(set(part_ids)) != len(part_ids):
        raise ValueError("BOM part_id values must be unique")
    unknown = sorted(set(part_analyses) - set(part_ids))
    missing = sorted(set(part_ids) - set(part_analyses))
    if unknown:
        raise ValueError(f"Analyses reference unknown BOM parts: {unknown}")
    if require_all and missing:
        raise ValueError(f"Missing monopart analyses: {missing}")

    parsed: dict[str, dict[str, Any]] = {}
    for part_id, source in part_analyses.items():
        document = _read_json(source, f"analysis for {part_id}")
        if not isinstance(document.get("part_identification"), str):
            raise ValueError(f"Analysis for {part_id} requires a flat monopart product object")
        parsed[part_id] = document

    enriched_parts = []
    for part in parts:
        enriched = dict(part)
        if part["part_id"] in parsed:
            enriched["part_analysis"] = parsed[part["part_id"]]
        enriched_parts.append(enriched)
    enriched_bom = {**base, "parts": enriched_parts}

    artifact = Path(output_path).resolve() if output_path is not None else None
    if artifact is not None:
        _write_json(artifact, enriched_bom)
    return {"status": "complete" if not missing else "partial",
            "artifact": str(artifact) if artifact else None,
            "merged_part_ids": sorted(parsed), "missing_part_ids": missing,
            "result": enriched_bom}
