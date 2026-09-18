"""Deterministic box-layout renderer for automation planner variants."""

from __future__ import annotations

import json
import math
import re
import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Iterable


DEFAULT_STRATEGIES = ("manuell", "halbautomatisiert", "vollautomatisiert")


@dataclass(frozen=True)
class LayoutConfig:
    pixels_per_cm: float = 4.0
    padding_cm: float = 25.0
    equipment_width_cm: float = 30.0
    equipment_height_cm: float = 18.0
    grid_step_cm: float = 25.0
    show_grid: bool = True
    show_coordinates: bool = False


@dataclass(frozen=True)
class Box:
    label: str
    x: float
    y: float
    width: float
    height: float
    quantity: int | None = None
    tooltip: str = ""
    station_nr: int | None = None


@dataclass(frozen=True)
class Boundary:
    station_nr: int
    x: float
    y: float
    width: float
    height: float


def generate_layouts_from_directory(
    automation_planner_dir: str | Path,
    *,
    strategies: Iterable[str] = DEFAULT_STRATEGIES,
    config: LayoutConfig | None = None,
) -> dict[str, dict[str, Any]]:
    """Render all requested variants found below an automation_planner directory."""
    planner_dir = Path(automation_planner_dir).resolve()
    variant_dir = planner_dir / "03_automatisierungsvarianten"
    if not variant_dir.is_dir():
        raise FileNotFoundError(f"Variant directory not found: {variant_dir}")

    output_root = planner_dir / "03a_layouts"
    output_root.mkdir(parents=True, exist_ok=True)
    cfg = config or LayoutConfig()
    results: dict[str, dict[str, Any]] = {}

    for strategy in strategies:
        variant_path = variant_dir / f"variante_{strategy}.json"
        if not variant_path.is_file():
            results[strategy] = {"status": "skipped", "reason": f"Missing {variant_path.name}"}
            continue
        try:
            layout_path = planner_dir / "03a_layoutplanung" / f"layout_{strategy}.json"
            results[strategy] = generate_variant_layouts(
                variant_path,
                output_root / strategy,
                layout_path=layout_path if layout_path.is_file() else None,
                config=cfg,
            )
        except Exception as exc:
            results[strategy] = {"status": "error", "reason": str(exc)}
    return results


def generate_variant_layouts(
    variant_path: str | Path,
    output_dir: str | Path,
    *,
    layout_path: str | Path | None = None,
    config: LayoutConfig | None = None,
) -> dict[str, Any]:
    """Render standalone station layouts and an overall layout for one variant."""
    source = Path(variant_path).resolve()
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    cfg = config or LayoutConfig()
    data = json.loads(source.read_text(encoding="utf-8"))
    layout_source: Path | None = None
    if layout_path is not None:
        layout_source = Path(layout_path).resolve()
        layout_data = json.loads(layout_source.read_text(encoding="utf-8"))
        _apply_separate_layout(data, layout_data)
    stations = data.get("stationen")
    if not isinstance(stations, list) or not stations:
        raise ValueError(f"No usable stationen list in {source}")

    station_numbers: set[int] = set()
    station_scenes: dict[int, tuple[list[Box], list[str], tuple[float, float, float, float]]] = {}
    station_images: list[dict[str, Any]] = []
    all_warnings: list[str] = []

    for station in sorted(stations, key=lambda item: int(item.get("station_nr", 0))):
        station_nr = _required_int(station, "station_nr")
        if station_nr in station_numbers:
            raise ValueError(f"Duplicate station_nr: {station_nr}")
        station_numbers.add(station_nr)
        boxes, warnings = _station_boxes(station, cfg)
        bounds = _bounds_for_boxes(boxes, cfg)
        title = f"Station {station_nr} - {data.get('strategie', '')}"
        svg_name = f"station_{station_nr:03d}.svg"
        png_name = f"station_{station_nr:03d}.png"
        _render_svg(target / svg_name, title, boxes, [], bounds, cfg, warnings)
        _render_png(target / png_name, title, boxes, [], bounds, cfg, warnings)
        station_scenes[station_nr] = (boxes, warnings, bounds)
        station_images.append(
            {
                "station_nr": station_nr,
                "svg": svg_name,
                "png": png_name,
                "bounds_cm": _bounds_dict(bounds),
                "warnings": warnings,
            }
        )
        all_warnings.extend(f"Station {station_nr}: {warning}" for warning in warnings)

    overall_boxes, boundaries, overall_warnings = _combined_scene(
        data.get("station_coordinates"), station_scenes, cfg
    )
    overall_bounds = _bounds_for_scene(overall_boxes, boundaries, cfg)
    overall_title = f"Overall layout - {data.get('strategie', '')}"
    _render_svg(
        target / "overall_layout.svg",
        overall_title,
        overall_boxes,
        boundaries,
        overall_bounds,
        cfg,
        overall_warnings,
    )
    _render_png(
        target / "overall_layout.png",
        overall_title,
        overall_boxes,
        boundaries,
        overall_bounds,
        cfg,
        overall_warnings,
    )
    all_warnings.extend(f"Overall: {warning}" for warning in overall_warnings)

    manifest = {
        "schema_version": "1.0",
        "status": "ok",
        "varianten_id": data.get("varianten_id"),
        "strategy": data.get("strategie"),
        "source_file": str(source),
        "layout_source_file": str(layout_source) if layout_source else None,
        "coordinate_unit": "cm",
        "renderer": {
            "version": "1.0-box-mvp",
            "pixels_per_cm": cfg.pixels_per_cm,
            "padding_cm": cfg.padding_cm,
            "equipment_width_cm": cfg.equipment_width_cm,
            "equipment_height_cm": cfg.equipment_height_cm,
        },
        "station_images": station_images,
        "overall_images": {
            "svg": "overall_layout.svg",
            "png": "overall_layout.png",
            "bounds_cm": _bounds_dict(overall_bounds),
        },
        "warnings": all_warnings,
    }
    (target / "layout_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _apply_separate_layout(variant: dict[str, Any], layout: dict[str, Any]) -> None:
    """Overlay a layout_planer artifact onto a module-03 variant in memory."""
    if layout.get("varianten_id") != variant.get("varianten_id"):
        raise ValueError("Layout varianten_id does not match variant source")
    if layout.get("strategie") != variant.get("strategie"):
        raise ValueError("Layout strategie does not match variant source")
    variant_stations = variant.get("stationen")
    layout_stations = layout.get("stationen")
    if not isinstance(variant_stations, list) or not isinstance(layout_stations, list):
        raise ValueError("Variant and layout stationen must be lists")

    by_number: dict[int, dict[str, Any]] = {}
    for item in layout_stations:
        if not isinstance(item, dict):
            raise ValueError("Invalid station entry in separate layout")
        station_nr = _required_int(item, "station_nr")
        if station_nr in by_number:
            raise ValueError(f"Duplicate station {station_nr} in separate layout")
        by_number[station_nr] = item

    for station in variant_stations:
        station_nr = _required_int(station, "station_nr")
        layout_station = by_number.get(station_nr)
        if layout_station is None:
            raise ValueError(f"Separate layout is missing station {station_nr}")
        station["station_layout"] = layout_station.get("station_layout")
        station["equipment_coordinates"] = layout_station.get("equipment_coordinates")
    if set(by_number) != {_required_int(item, "station_nr") for item in variant_stations}:
        raise ValueError("Separate layout contains unknown stations")
    variant["layout_gesamt"] = layout.get("layout_gesamt")
    variant["station_coordinates"] = layout.get("station_coordinates")


def _station_boxes(station: dict[str, Any], cfg: LayoutConfig) -> tuple[list[Box], list[str]]:
    warnings: list[str] = []
    equipment = station.get("equipment_station") or []
    coordinates = station.get("equipment_coordinates") or []
    if not isinstance(equipment, list) or not isinstance(coordinates, list):
        raise ValueError("equipment_station and equipment_coordinates must be lists")

    equipment_by_name: dict[str, dict[str, Any]] = {}
    for item in equipment:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            warnings.append("Ignored equipment row without a valid name")
            continue
        key = _normalize_name(item["name"])
        if key in equipment_by_name:
            warnings.append(f"Duplicate normalized equipment name: {item['name']}")
            continue
        equipment_by_name[key] = item

    boxes: list[Box] = []
    positioned_keys: set[str] = set()
    coordinate_keys: set[str] = set()
    for coordinate in coordinates:
        if not isinstance(coordinate, dict) or not isinstance(coordinate.get("equipment_name"), str):
            warnings.append("Ignored coordinate row without a valid equipment_name")
            continue
        name = coordinate["equipment_name"].strip()
        key = _normalize_name(name)
        if key in coordinate_keys:
            warnings.append(f"Duplicate coordinate for equipment: {name}")
            continue
        coordinate_keys.add(key)
        x = _finite_number(coordinate.get("x"), f"x coordinate for {name}")
        y = _finite_number(coordinate.get("y"), f"y coordinate for {name}")
        detail = equipment_by_name.get(key)
        if detail is None:
            warnings.append(f"Coordinate has no exact equipment match: {name}")
        else:
            positioned_keys.add(key)
        quantity = _optional_positive_int(detail.get("quantity")) if detail else None
        tooltip = name
        if detail:
            tooltip = "\n".join(
                part for part in (name, str(detail.get("function") or ""), str(detail.get("specimen") or "")) if part
            )
        boxes.append(
            Box(
                label=name,
                x=x,
                y=y,
                width=cfg.equipment_width_cm,
                height=cfg.equipment_height_cm,
                quantity=quantity,
                tooltip=tooltip,
                station_nr=_required_int(station, "station_nr"),
            )
        )

    for key, item in equipment_by_name.items():
        if key not in positioned_keys:
            warnings.append(f"Equipment has no coordinate: {item['name']}")
    if not boxes:
        warnings.append("No positioned equipment")
    warnings.extend(_box_overlap_warnings(boxes))
    return sorted(boxes, key=lambda box: (_normalize_name(box.label), box.x, box.y)), warnings


def _combined_scene(
    raw_coordinates: Any,
    station_scenes: dict[int, tuple[list[Box], list[str], tuple[float, float, float, float]]],
    cfg: LayoutConfig,
) -> tuple[list[Box], list[Boundary], list[str]]:
    if not isinstance(raw_coordinates, list):
        raise ValueError("station_coordinates must be a list")
    warnings: list[str] = []
    coordinate_map: dict[int, tuple[float, float]] = {}
    for item in raw_coordinates:
        if not isinstance(item, dict):
            warnings.append("Ignored invalid station coordinate row")
            continue
        station_nr = _required_int(item, "station_nr")
        if station_nr in coordinate_map:
            raise ValueError(f"Duplicate station coordinate for station {station_nr}")
        coordinate_map[station_nr] = (
            _finite_number(item.get("x"), f"station {station_nr} x"),
            _finite_number(item.get("y"), f"station {station_nr} y"),
        )

    boxes: list[Box] = []
    boundaries: list[Boundary] = []
    for station_nr, (local_boxes, _, _) in station_scenes.items():
        global_position = coordinate_map.get(station_nr)
        if global_position is None:
            warnings.append(f"Station {station_nr} has no global coordinate and was omitted")
            continue
        gx, gy = global_position
        if local_boxes:
            content_min_x = min(box.x - box.width / 2 for box in local_boxes)
            content_max_x = max(box.x + box.width / 2 for box in local_boxes)
            content_min_y = min(box.y - box.height / 2 for box in local_boxes)
            content_max_y = max(box.y + box.height / 2 for box in local_boxes)
            boundary_width = content_max_x - content_min_x
            boundary_height = content_max_y - content_min_y
            boundary_x = gx + (content_min_x + content_max_x) / 2
            boundary_y = gy + (content_min_y + content_max_y) / 2
        else:
            boundary_width = cfg.equipment_width_cm
            boundary_height = cfg.equipment_height_cm
            boundary_x = gx
            boundary_y = gy
        boundaries.append(
            Boundary(station_nr, boundary_x, boundary_y, boundary_width, boundary_height)
        )
        boxes.extend(
            Box(
                label=box.label,
                x=gx + box.x,
                y=gy + box.y,
                width=box.width,
                height=box.height,
                quantity=box.quantity,
                tooltip=box.tooltip,
                station_nr=station_nr,
            )
            for box in local_boxes
        )

    for station_nr in sorted(set(coordinate_map) - set(station_scenes)):
        warnings.append(f"Global coordinate has no matching station: {station_nr}")
    if not boundaries:
        warnings.append("No positioned stations")
    warnings.extend(_boundary_overlap_warnings(boundaries))
    return boxes, boundaries, warnings


def _render_png(
    path: Path,
    title: str,
    boxes: list[Box],
    boundaries: list[Boundary],
    bounds: tuple[float, float, float, float],
    cfg: LayoutConfig,
    warnings: list[str],
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for PNG layout rendering") from exc

    min_x, min_y, max_x, max_y = bounds
    scale = cfg.pixels_per_cm
    header_px = 70 + (min(len(warnings), 4) * 18)
    width_px = max(640, int(math.ceil((max_x - min_x) * scale)))
    height_px = max(480, int(math.ceil((max_y - min_y) * scale)) + header_px)
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    font = _load_font(ImageFont, 14)
    small_font = _load_font(ImageFont, 11)
    title_font = _load_font(ImageFont, 20)

    def point(x: float, y: float) -> tuple[float, float]:
        return (x - min_x) * scale, header_px + (max_y - y) * scale

    draw.text((16, 12), title, fill="#111827", font=title_font)
    for index, warning in enumerate(warnings[:4]):
        draw.text((16, 40 + index * 18), f"Warning: {warning}", fill="#b45309", font=small_font)

    if cfg.show_grid:
        _draw_png_grid(draw, point, bounds, cfg, header_px, width_px, height_px, small_font)
    _draw_png_origin(draw, point, small_font)

    for boundary in boundaries:
        left, top = point(boundary.x - boundary.width / 2, boundary.y + boundary.height / 2)
        right, bottom = point(boundary.x + boundary.width / 2, boundary.y - boundary.height / 2)
        draw.rectangle((left, top, right, bottom), outline="#2563eb", width=3)
        draw.text((left + 6, top + 5), f"Station {boundary.station_nr}", fill="#1d4ed8", font=font)

    for box in boxes:
        left, top = point(box.x - box.width / 2, box.y + box.height / 2)
        right, bottom = point(box.x + box.width / 2, box.y - box.height / 2)
        draw.rounded_rectangle((left, top, right, bottom), radius=7, fill="#e5e7eb", outline="#374151", width=2)
        _draw_centered_png_label(draw, box, (left, top, right, bottom), font, small_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _render_svg(
    path: Path,
    title: str,
    boxes: list[Box],
    boundaries: list[Boundary],
    bounds: tuple[float, float, float, float],
    cfg: LayoutConfig,
    warnings: list[str],
) -> None:
    min_x, min_y, max_x, max_y = bounds
    scale = cfg.pixels_per_cm
    header_px = 70 + min(len(warnings), 4) * 18
    width_px = max(640, int(math.ceil((max_x - min_x) * scale)))
    height_px = max(480, int(math.ceil((max_y - min_y) * scale)) + header_px)

    def point(x: float, y: float) -> tuple[float, float]:
        return (x - min_x) * scale, header_px + (max_y - y) * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="16" y="30" font-family="Arial, sans-serif" font-size="20" font-weight="bold" fill="#111827">{escape(title)}</text>',
    ]
    for index, warning in enumerate(warnings[:4]):
        parts.append(
            f'<text x="16" y="{52 + index * 18}" font-family="Arial, sans-serif" font-size="11" fill="#b45309">Warning: {escape(warning)}</text>'
        )
    if cfg.show_grid:
        parts.extend(_svg_grid(point, bounds, cfg, header_px, width_px, height_px))
    ox, oy = point(0, 0)
    parts.extend(
        [
            f'<line x1="{ox - 8:.1f}" y1="{oy:.1f}" x2="{ox + 8:.1f}" y2="{oy:.1f}" stroke="#dc2626"/>',
            f'<line x1="{ox:.1f}" y1="{oy - 8:.1f}" x2="{ox:.1f}" y2="{oy + 8:.1f}" stroke="#dc2626"/>',
            f'<text x="{ox + 5:.1f}" y="{oy - 6:.1f}" font-family="Arial, sans-serif" font-size="10" fill="#dc2626">0,0</text>',
        ]
    )
    for boundary in boundaries:
        left, top = point(boundary.x - boundary.width / 2, boundary.y + boundary.height / 2)
        parts.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{boundary.width * scale:.1f}" height="{boundary.height * scale:.1f}" fill="none" stroke="#2563eb" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{left + 6:.1f}" y="{top + 18:.1f}" font-family="Arial, sans-serif" font-size="14" fill="#1d4ed8">Station {boundary.station_nr}</text>'
        )
    for box in boxes:
        left, top = point(box.x - box.width / 2, box.y + box.height / 2)
        box_width_px = box.width * scale
        box_height_px = box.height * scale
        parts.append("<g>")
        parts.append(f"<title>{escape(box.tooltip or box.label)}</title>")
        parts.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{box_width_px:.1f}" height="{box_height_px:.1f}" rx="7" fill="#e5e7eb" stroke="#374151" stroke-width="2"/>'
        )
        lines = _wrapped_label(box.label, max(10, int(box_width_px / 7.5)), 4)
        if box.quantity and box.quantity > 1:
            lines.append(f"x{box.quantity}")
        line_height = 15
        start_y = top + box_height_px / 2 - (len(lines) - 1) * line_height / 2
        for index, line in enumerate(lines):
            parts.append(
                f'<text x="{left + box_width_px / 2:.1f}" y="{start_y + index * line_height:.1f}" text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif" font-size="12" fill="#111827">{escape(line)}</text>'
            )
        parts.append("</g>")
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _draw_png_grid(draw: Any, point: Any, bounds: tuple[float, float, float, float], cfg: LayoutConfig, header_px: int, width_px: int, height_px: int, font: Any) -> None:
    min_x, min_y, max_x, max_y = bounds
    step = cfg.grid_step_cm
    first_x = math.floor(min_x / step) * step
    first_y = math.floor(min_y / step) * step
    x = first_x
    while x <= max_x:
        px, _ = point(x, 0)
        draw.line((px, header_px, px, height_px), fill="#eef2f7", width=1)
        draw.text((px + 2, height_px - 15), f"{x:g}", fill="#9ca3af", font=font)
        x += step
    y = first_y
    while y <= max_y:
        _, py = point(0, y)
        draw.line((0, py, width_px, py), fill="#eef2f7", width=1)
        draw.text((2, py + 2), f"{y:g}", fill="#9ca3af", font=font)
        y += step


def _svg_grid(point: Any, bounds: tuple[float, float, float, float], cfg: LayoutConfig, header_px: int, width_px: int, height_px: int) -> list[str]:
    min_x, min_y, max_x, max_y = bounds
    result: list[str] = []
    step = cfg.grid_step_cm
    x = math.floor(min_x / step) * step
    while x <= max_x:
        px, _ = point(x, 0)
        result.append(f'<line x1="{px:.1f}" y1="{header_px}" x2="{px:.1f}" y2="{height_px}" stroke="#eef2f7"/>')
        x += step
    y = math.floor(min_y / step) * step
    while y <= max_y:
        _, py = point(0, y)
        result.append(f'<line x1="0" y1="{py:.1f}" x2="{width_px}" y2="{py:.1f}" stroke="#eef2f7"/>')
        y += step
    return result


def _draw_png_origin(draw: Any, point: Any, font: Any) -> None:
    ox, oy = point(0, 0)
    draw.line((ox - 8, oy, ox + 8, oy), fill="#dc2626", width=2)
    draw.line((ox, oy - 8, ox, oy + 8), fill="#dc2626", width=2)
    draw.text((ox + 5, oy - 16), "0,0", fill="#dc2626", font=font)


def _draw_centered_png_label(draw: Any, box: Box, rect: tuple[float, float, float, float], font: Any, small_font: Any) -> None:
    left, top, right, bottom = rect
    width_px = right - left
    lines = _wrapped_label(box.label, max(10, int(width_px / 7.5)), 4)
    if box.quantity and box.quantity > 1:
        lines.append(f"x{box.quantity}")
    text = "\n".join(lines)
    text_box = draw.multiline_textbbox((0, 0), text, font=font, spacing=2, align="center")
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.multiline_text(
        ((left + right - text_width) / 2, (top + bottom - text_height) / 2),
        text,
        fill="#111827",
        font=font,
        spacing=2,
        align="center",
    )


def _wrapped_label(label: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(label, width=max(5, width), break_long_words=True, break_on_hyphens=True) or [label]
    if len(lines) <= max_lines:
        return lines
    result = lines[:max_lines]
    result[-1] = result[-1][:-1] + "…" if result[-1] else "…"
    return result


def _load_font(image_font: Any, size: int) -> Any:
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return image_font.truetype(candidate, size)
        except OSError:
            continue
    return image_font.load_default()


def _bounds_for_boxes(boxes: list[Box], cfg: LayoutConfig) -> tuple[float, float, float, float]:
    if not boxes:
        half_w = cfg.equipment_width_cm / 2
        half_h = cfg.equipment_height_cm / 2
        return (-half_w - cfg.padding_cm, -half_h - cfg.padding_cm, half_w + cfg.padding_cm, half_h + cfg.padding_cm)
    min_x = min(box.x - box.width / 2 for box in boxes) - cfg.padding_cm
    max_x = max(box.x + box.width / 2 for box in boxes) + cfg.padding_cm
    min_y = min(box.y - box.height / 2 for box in boxes) - cfg.padding_cm
    max_y = max(box.y + box.height / 2 for box in boxes) + cfg.padding_cm
    return min_x, min_y, max_x, max_y


def _bounds_for_scene(boxes: list[Box], boundaries: list[Boundary], cfg: LayoutConfig) -> tuple[float, float, float, float]:
    extents: list[tuple[float, float, float, float]] = [
        (box.x - box.width / 2, box.y - box.height / 2, box.x + box.width / 2, box.y + box.height / 2)
        for box in boxes
    ]
    extents.extend(
        (item.x - item.width / 2, item.y - item.height / 2, item.x + item.width / 2, item.y + item.height / 2)
        for item in boundaries
    )
    if not extents:
        return _bounds_for_boxes([], cfg)
    return (
        min(item[0] for item in extents) - cfg.padding_cm,
        min(item[1] for item in extents) - cfg.padding_cm,
        max(item[2] for item in extents) + cfg.padding_cm,
        max(item[3] for item in extents) + cfg.padding_cm,
    )


def _box_overlap_warnings(boxes: list[Box]) -> list[str]:
    warnings: list[str] = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            if _rectangles_overlap(first.x, first.y, first.width, first.height, second.x, second.y, second.width, second.height):
                warnings.append(f"Visual rectangles overlap: {first.label} / {second.label}")
    return warnings


def _boundary_overlap_warnings(boundaries: list[Boundary]) -> list[str]:
    warnings: list[str] = []
    for index, first in enumerate(boundaries):
        for second in boundaries[index + 1 :]:
            if _rectangles_overlap(first.x, first.y, first.width, first.height, second.x, second.y, second.width, second.height):
                warnings.append(f"Station boundaries overlap: {first.station_nr} / {second.station_nr}")
    return warnings


def _rectangles_overlap(x1: float, y1: float, w1: float, h1: float, x2: float, y2: float, w2: float, h2: float) -> bool:
    return abs(x1 - x2) < (w1 + w2) / 2 and abs(y1 - y2) < (h1 + h2) / 2


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _required_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return result


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _bounds_dict(bounds: tuple[float, float, float, float]) -> dict[str, float]:
    return dict(zip(("min_x", "min_y", "max_x", "max_y"), bounds))
