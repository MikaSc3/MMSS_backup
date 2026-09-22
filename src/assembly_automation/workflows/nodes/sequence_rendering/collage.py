"""Information-dense collage selection for rendered assembly steps."""

from itertools import combinations
from pathlib import Path
from typing import Any

from assembly_automation.stepparser.rendering.automaticimageselection import (
    describe_image,
    make_collage,
    pair_metrics,
)

from .settings import SequenceCollageSettings


def _best_complementary(anchor, candidates, count: int, entropy_weight: float):
    if count <= 0 or not candidates:
        return [], 0.0, []
    count = min(count, len(candidates))
    ranked = []
    for selection in combinations(candidates, count):
        items = [anchor, *selection]
        metrics = [pair_metrics(left[1], right[1], True)
                   for left, right in combinations(items, 2)]
        differences = [item["diversity"] for item in metrics]
        diversity = 0.5 * (sum(differences) / len(differences)) + 0.5 * min(differences)
        entropy = sum(item[1]["entropy"] for item in selection) / len(selection)
        score = (1 - entropy_weight) * diversity + entropy_weight * entropy
        ranked.append((score, selection, metrics))
    score, selection, metrics = max(ranked, key=lambda item: item[0])
    return [item[0] for item in selection], score, metrics


def create_step_collages(images: list[dict[str, Any]], output_dir: str | Path,
                         settings: SequenceCollageSettings, progress=None) -> list[dict[str, Any]]:
    """Create one collage per step from opaque, nonduplicate after-state views."""
    if not settings.enabled:
        return []
    root = Path(output_dir)
    step_ids = sorted({record["step_id"] for record in images if "step_id" in record})
    results = []
    for step_id in step_ids:
        records = [record for record in images if record.get("step_id") == step_id]
        anchor = next((record for record in records
                       if record.get("category") == "assembled" and record.get("view") == "iso1"
                       and record.get("transparency") == 0), None)
        if anchor is None:
            results.append({"step_id": step_id, "status": "skipped", "reason": "missing_opaque_iso1"})
            continue
        highlight = next((record for record in records
                          if record.get("category") == "joining_highlight"), None)
        exploded = next((record for record in records
                         if record.get("category") == "exploded" and record.get("view") == "iso1"), None)
        candidates = [record for record in records
                      if record is not anchor and record.get("transparency") == 0
                      and (record.get("category") == "assembled"
                           or (record.get("category") == "section" and record.get("state") == "after"))]

        def describe(record):
            return describe_image(root / record["path"], settings.analysis_size)

        anchor_descriptor = describe(anchor)
        valid = [(record, descriptor) for record in candidates
                 if (descriptor := describe(record)) is not None]
        if anchor_descriptor is None:
            results.append({"step_id": step_id, "status": "skipped", "reason": "blank_iso1"})
            continue
        selected, score, metrics = _best_complementary(
            (anchor, anchor_descriptor), valid, settings.additional_views, settings.entropy_weight)
        panels = [anchor, *selected]
        if settings.include_highlight and highlight is not None and describe(highlight) is not None:
            panels.append(highlight)
        if settings.include_exploded and exploded is not None and describe(exploded) is not None:
            panels.append(exploded)
        target = root / f"collage_step_{step_id:02d}.png"
        make_collage([root / record["path"] for record in panels],
                     [Path(record["path"]).stem for record in panels], target, settings.tile_size,
                     crop_whitespace=settings.crop_whitespace,
                     crop_padding_px=settings.crop_padding_px)
        result = {"step_id": step_id, "status": "complete", "path": target.name,
                  "selected_images": [record["path"] for record in panels],
                  "score": score, "pairwise_metrics": metrics,
                  "candidate_count": len(valid),
                  "method": "iso1_plus_complementary_after_views_plus_highlight_then_exploded_v1"}
        results.append(result)
        if progress:
            progress("sequence_collages", len(results), len(step_ids))
    return results
