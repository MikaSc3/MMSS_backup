from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping


DEFAULT_STYLES = {
    "robot": (80, 80, "#6aa9ff"), "fixture": (70, 50, "#62c4a6"),
    "feeder": (75, 45, "#f0b45d"), "conveyor": (120, 40, "#9ba7b4"),
    "workstation": (100, 65, "#9b86e8"), "storage": (80, 55, "#d3a35d"),
    "inspection": (65, 45, "#5fc2d6"), "safety": (90, 35, "#ef7d7d"),
    "operator": (55, 55, "#f0d45d"), "tool": (55, 35, "#85b66f"),
    "hmi": (45, 35, "#8ed1c5"),
    "other": (70, 45, "#b1b6bd"),
}


def _footprint(item: Mapping[str, Any]) -> tuple[float, float, str]:
    kind = str(item.get("class", "other"))
    default_width, default_height, color = DEFAULT_STYLES.get(kind, DEFAULT_STYLES["other"])
    size = item.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0:
        return float(size), float(size), color
    return float(default_width), float(default_height), color


def render_layout(layout: Mapping[str, Any], output_path: str | Path) -> str:
    """Render a deterministic, self-contained SVG from center coordinates."""
    items = list(layout.get("equipment") or [])
    if not items:
        raise ValueError("Layout contains no equipment")
    margin = 35
    bounds = []
    for item in items:
        width, height, _ = _footprint(item)
        bounds.append((int(item["x"]) - width / 2, int(item["y"]) - height / 2,
                       int(item["x"]) + width / 2, int(item["y"]) + height / 2))
    min_x = min(value[0] for value in bounds) - margin
    min_y = min(value[1] for value in bounds) - margin
    max_x = max(value[2] for value in bounds) + margin
    max_y = max(value[3] for value in bounds) + margin
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x} {-max_y} {max_x-min_x} {max_y-min_y}">',
           '<rect x="-10000" y="-10000" width="20000" height="20000" fill="#f7f8fa"/>']
    for item in items:
        width, height, color = _footprint(item)
        x, y = int(item["x"]), -int(item["y"])
        label = escape(str(item["name"]))
        svg.append(f'<rect x="{x-width/2}" y="{y-height/2}" width="{width}" height="{height}" rx="5" fill="{color}" stroke="#263238" stroke-width="2"/>')
        svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="10" fill="#172027">{label}</text>')
    svg.append("</svg>")
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text("\n".join(svg), encoding="utf-8")
    temporary.replace(target)
    return str(target)
