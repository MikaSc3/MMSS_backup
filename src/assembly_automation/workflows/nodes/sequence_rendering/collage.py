"""Information-dense collage selection for rendered assembly steps."""

from itertools import combinations
import math
import os
from pathlib import Path
import textwrap
import time
from typing import Any
from uuid import uuid4

from assembly_automation.stepparser.rendering.automaticimageselection import (
    describe_image,
    make_collage,
    pair_metrics,
)

from .settings import SequenceCollageSettings


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _save_atomic(image, target: Path) -> None:
    temporary = target.with_name(f".{target.stem}_{uuid4().hex}.png")
    try:
        image.save(temporary, format="PNG")
        for attempt in range(8):
            try:
                os.replace(temporary, target)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def create_sequence_overview(images: list[dict[str, Any]], sequence: dict[str, Any],
                             output_dir: str | Path,
                             settings: SequenceCollageSettings) -> dict[str, Any] | None:
    """Create one ordered process board from each step's assembled opaque ISO1 image."""
    if not settings.enabled or not settings.overview_enabled:
        return None
    root = Path(output_dir)
    steps = sorted((item for item in sequence.get("steps", []) if isinstance(item, dict)),
                   key=lambda item: item.get("step_id", 0))
    anchors: dict[Any, dict[str, Any]] = {}
    for record in images:
        if (record.get("category") == "assembled" and record.get("view") == "iso1"
                and record.get("transparency") == 0):
            anchors.setdefault(record.get("step_id"), record)
    selected = [(step, anchors.get(step.get("step_id"))) for step in steps]
    selected = [(step, record) for step, record in selected if record is not None
                and (root / record["path"]).is_file()]
    if not selected:
        return None

    from PIL import Image, ImageDraw, ImageOps
    tile_width, tile_height = settings.overview_tile_size
    header, footer, gap, margin = 48, 82, 34, 28
    maximum_columns = min(settings.overview_columns, len(selected))
    if maximum_columns == 1:
        columns = 1
    else:
        columns = min(
            range(2, maximum_columns + 1),
            key=lambda candidate: (
                abs(candidate / math.ceil(len(selected) / candidate) - 1.6)
                + 0.4 * (candidate * math.ceil(len(selected) / candidate) - len(selected))))
    rows = math.ceil(len(selected) / columns)
    card_width, card_height = tile_width, header + tile_height + footer
    width = margin * 2 + columns * card_width + (columns - 1) * gap
    height = margin * 2 + rows * card_height + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), (235, 243, 246))
    draw = ImageDraw.Draw(canvas)
    label_font = _font(17)
    small_font, badge_font = _font(15), _font(22, bold=True)
    paths, step_ids = [], []
    for index, (step, record) in enumerate(selected):
        row, column = divmod(index, columns)
        row_items = min(columns, len(selected) - row * columns)
        row_offset = (columns - row_items) * (card_width + gap) // 2
        x = margin + row_offset + column * (card_width + gap)
        y = margin + row * (card_height + gap)
        draw.rounded_rectangle((x, y, x + card_width, y + card_height), radius=12,
                               fill=(255, 255, 255), outline=(190, 209, 217), width=2)
        draw.rounded_rectangle((x, y, x + card_width, y + header), radius=12,
                               fill=(8, 127, 140))
        draw.rectangle((x, y + header - 12, x + card_width, y + header), fill=(8, 127, 140))
        step_id = int(step["step_id"])
        draw.text((x + 16, y + 10), f"STEP {step_id:02d}", fill="white", font=badge_font)
        process = str(step.get("joining_process") or "Assembly operation")
        process_box = draw.textbbox((0, 0), process, font=small_font)
        draw.text((x + card_width - (process_box[2] - process_box[0]) - 16, y + 15),
                  process, fill=(215, 246, 246), font=small_font)
        with Image.open(root / record["path"]) as source:
            fitted = ImageOps.contain(source.convert("RGB"), (tile_width - 20, tile_height - 20))
            image_x = x + (tile_width - fitted.width) // 2
            image_y = y + header + (tile_height - fitted.height) // 2
            canvas.paste(fitted, (image_x, image_y))
        description = str(step.get("step_description") or "")
        joining = step.get("joining_part")
        joined = ", ".join(joining) if isinstance(joining, list) else str(joining or "")
        lines = textwrap.wrap(description, width=max(28, tile_width // 12))[:2]
        draw.text((x + 16, y + header + tile_height + 10), "\n".join(lines),
                  fill=(25, 50, 65), font=label_font, spacing=3)
        if joined:
            draw.text((x + 16, y + card_height - 24), f"Adds: {joined}",
                      fill=(92, 117, 130), font=small_font)
        if column < row_items - 1:
            arrow_y = y + card_height // 2
            arrow_end = x + card_width + gap - 8
            draw.line((x + card_width + 7, arrow_y, arrow_end, arrow_y),
                      fill=(8, 127, 140), width=4)
            draw.polygon(((arrow_end, arrow_y), (arrow_end - 9, arrow_y - 7),
                          (arrow_end - 9, arrow_y + 7)), fill=(8, 127, 140))
        paths.append(record["path"])
        step_ids.append(step_id)
    target = root / "collage_sequence.png"
    _save_atomic(canvas, target)
    return {"status": "complete", "path": target.name,
            "category": "sequence_overview", "view": "ordered_steps",
            "step_ids": step_ids, "selected_images": paths,
            "method": "ordered_assembled_iso1_cards_v1"}


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
                  "category": "step_collage", "view": "overview",
                  "selected_images": [record["path"] for record in panels],
                  "score": score, "pairwise_metrics": metrics,
                  "candidate_count": len(valid),
                  "method": "iso1_plus_complementary_after_views_plus_highlight_then_exploded_v1"}
        results.append(result)
        if progress:
            progress("sequence_collages", len(results), len(step_ids))
    return results
