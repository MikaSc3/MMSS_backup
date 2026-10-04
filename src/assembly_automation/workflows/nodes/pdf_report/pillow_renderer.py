"""Dependency-light raster PDF renderer using Pillow's multipage PDF support."""

from __future__ import annotations

from pathlib import Path
import textwrap
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont, ImageOps


SIZE = (1754, 1240)  # A4 landscape at 150 dpi
MARGIN = 55
COLORS = {"primary": "#12333A", "accent": "#14866D", "risk": "#B33A3A",
          "muted": "#607177", "line": "#D6DFDD", "soft": "#F1F5F4"}


def _font(size: int, bold: bool = False):
    names = ([r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"] if bold
             else [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"])
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def _plain(value: Any) -> str:
    if value in (None, ""):
        return "Not available"
    if isinstance(value, list):
        return "; ".join(_plain(item) for item in value)
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_plain(item)}" for key, item in value.items())
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _page(title: str, subtitle: str):
    page = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(page)
    draw.text((MARGIN, 42), title, font=_font(30, True), fill=COLORS["primary"])
    draw.text((MARGIN, 86), subtitle, font=_font(16), fill=COLORS["muted"])
    draw.line((MARGIN, 118, SIZE[0] - MARGIN, 118), fill=COLORS["line"], width=2)
    return page, draw


def _wrap(draw, text: Any, font, width: int) -> list[str]:
    words = _plain(text).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current); current = word
    if current:
        lines.append(current)
    return lines or ["Not available"]


def _box(draw, rect, title: str, items: list[Any], *, color=None, max_lines=15):
    x1, y1, x2, y2 = rect
    draw.rectangle(rect, outline=COLORS["line"], width=2)
    draw.text((x1 + 18, y1 + 14), title.upper(), font=_font(17, True),
              fill=color or COLORS["primary"])
    font = _font(14); y = y1 + 50; lines_used = 0
    for item in items or ["None recorded"]:
        lines = _wrap(draw, item, font, x2 - x1 - 52)
        for index, line in enumerate(lines):
            if lines_used >= max_lines or y + 20 > y2:
                return
            draw.text((x1 + 20, y), ("• " if index == 0 else "  ") + line,
                      font=font, fill="#26363B")
            y += 21; lines_used += 1
        y += 5


def _image(page, rect, path: Path | None, label: str):
    draw = ImageDraw.Draw(page); draw.rectangle(rect, outline=COLORS["line"], width=2)
    x1, y1, x2, y2 = rect
    if path and path.is_file():
        with Image.open(path) as source:
            image = ImageOps.contain(source.convert("RGB"), (x2 - x1 - 8, y2 - y1 - 8))
        page.paste(image, (x1 + (x2 - x1 - image.width) // 2,
                           y1 + (y2 - y1 - image.height) // 2))
    else:
        draw.text((x1 + 20, (y1 + y2) // 2), f"{label} unavailable",
                  font=_font(17), fill=COLORS["muted"])


def _score_rows(draw, rect, values: Mapping[str, Any], total: Any = None):
    x1, y1, x2, _ = rect
    if total is not None:
        draw.text((x1, y1), "FINAL FFA SCORE", font=_font(18, True), fill=COLORS["primary"])
        draw.text((x1, y1 + 28), f"{float(total):.2f}" if isinstance(total, (int, float)) else "n/a",
                  font=_font(48, True), fill=COLORS["accent"])
        y1 += 105
    for name in ("separation", "handling", "positioning", "joining"):
        value = values.get(name)
        numeric = float(value) if isinstance(value, (int, float)) else 0
        draw.text((x1, y1), name.title(), font=_font(15), fill=COLORS["primary"])
        bx1, bx2 = x1 + 150, x2 - 55
        draw.rectangle((bx1, y1 + 2, bx2, y1 + 19), fill=COLORS["soft"])
        draw.rectangle((bx1, y1 + 2, bx1 + int((bx2 - bx1) * max(0, min(1, numeric))), y1 + 19),
                       fill=COLORS["accent"])
        draw.text((x2 - 45, y1), f"{numeric:.2f}" if isinstance(value, (int, float)) else "n/a",
                  font=_font(14, True), fill=COLORS["primary"])
        y1 += 43


def render_pdf(model: Mapping[str, Any], images, sequence_root: Path | None, output: Path) -> int:
    pages = []
    overview, aggregate = model["assembly_overview"], model["scorecard"].get("aggregate", {})
    assembly_name = overview.get("assembly_name_guess") or overview.get("assembly_name") or "Assembly"
    findings = [item for item in model["key_findings"] if item.get("scope") == "assembly"] or model["key_findings"]
    finding_ids = {item.get("finding_id") for item in findings}
    recommendations = [item for item in model["recommendations"]
                       if finding_ids.intersection(item.get("addresses_findings", []))]
    page, draw = _page(str(assembly_name), "Assembly overview")
    _image(page, (55, 150, 560, 590), images.assembly(), "Assembly image")
    scores = {name: aggregate.get(f"mean_{name}_score")
              for name in ("separation", "handling", "positioning", "joining")}
    _score_rows(draw, (610, 170, 1010, 590), scores, aggregate.get("mean_total_ffa"))
    _box(draw, (1060, 150, 1699, 590), "Executive summary",
         [item.get("statement") for item in model["executive_summary"]], max_lines=17)
    _box(draw, (55, 640, 850, 1165), "Design drawbacks",
         [item.get("statement") for item in findings[:5]], color=COLORS["risk"], max_lines=21)
    _box(draw, (900, 640, 1699, 1165), "Top improvements",
         [f"{item.get('action')} Expected effect: {item.get('expected_effect')}"
          for item in recommendations[:5]], color=COLORS["accent"], max_lines=21)
    pages.append(page)

    page, draw = _page("Assembly sequence", "Approved sequence and evaluated step order")
    collage = sequence_root / "collage_sequence.png" if sequence_root else None
    _image(page, (55, 145, 1699, 720), collage, "Sequence overview")
    _box(draw, (55, 760, 1699, 1165), "Sequence steps",
         [f"{step.get('step_id')}. {step.get('step_description')} "
          f"[{step.get('joining_process')}; FFA {_plain(step.get('total_ffa'))}]"
          for step in model["steps"]], max_lines=15)
    pages.append(page)

    findings_by_id = {item["finding_id"]: item for item in model["key_findings"]}
    recs_by_id = {item["recommendation_id"]: item for item in model["recommendations"]}
    for part in model["parts"]:
        page, draw = _page(f"{part.get('part_id')} · {_plain(part.get('name'))}", "Monopart assessment")
        _image(page, (55, 145, 580, 625), images.part(str(part.get("part_id"))), "Part image")
        _box(draw, (625, 145, 1699, 625), "Part profile", [
            f"Quantity: {_plain(part.get('quantity'))}", f"Size: {_plain(part.get('size'))}",
            f"Identification: {_plain(part.get('part_identification'))}",
            f"Summary: {_plain(part.get('intrinsic_summary'))}"], max_lines=18)
        part_findings = [findings_by_id[item] for item in part.get("finding_ids", []) if item in findings_by_id]
        part_recs = [recs_by_id[item] for item in part.get("recommendation_ids", []) if item in recs_by_id]
        _box(draw, (55, 675, 850, 1165), "Design drawbacks",
             [item.get("statement") for item in part_findings], color=COLORS["risk"], max_lines=19)
        _box(draw, (900, 675, 1699, 1165), "Top improvements",
             [f"{item.get('action')} Expected effect: {item.get('expected_effect')}" for item in part_recs],
             color=COLORS["accent"], max_lines=19)
        pages.append(page)

    for step in model["steps"]:
        page, draw = _page(f"Step {step.get('step_id')} · {_plain(step.get('step_description'))}",
                           f"{_plain(step.get('joining_process'))} · Step FFA {_plain(step.get('total_ffa'))}")
        _image(page, (55, 145, 730, 620), images.step(int(step["step_id"]), step.get("image_refs")), "Step image")
        values = {name: step["subprocesses"][name].get("score")
                  for name in ("separation", "handling", "positioning", "joining")}
        _score_rows(draw, (800, 180, 1650, 590), values, step.get("total_ffa"))
        for index, name in enumerate(("separation", "handling", "positioning", "joining")):
            col, row = index % 2, index // 2
            value = step["subprocesses"][name]
            x1, y1 = 55 + col * 845, 675 + row * 250
            _box(draw, (x1, y1, x1 + 795, y1 + 205), name, [
                f"Automation potential: {_plain(value.get('automation_potential'))}",
                f"Risks: {_plain(value.get('risks'))}"], max_lines=7)
        pages.append(page)

    output.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(output, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return len(pages)
