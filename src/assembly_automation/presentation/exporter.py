"""Deterministic editable PowerPoint export for assembly and monopart artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from assembly_automation.workflows.definitions.app_v3 import WorkflowPaths


@dataclass(frozen=True)
class EngineeringPowerPointContext:
    """Active saved artifacts and their preprocessing image directory."""

    session_root: Path
    assembly: Mapping[str, Any]
    bom: Mapping[str, Any]
    images_root: Path
    assembly_revision: str
    monoparts_revision: str

    @classmethod
    def from_session(cls, session_root: str | Path) -> "EngineeringPowerPointContext":
        paths = WorkflowPaths(Path(session_root).resolve())
        assembly_revision = paths.active_revision("assembly")
        monoparts_revision = paths.active_revision("monoparts")
        assembly = _load_object(paths.assembly(assembly_revision) / "assembly_overview.json",
                                "active assembly overview")
        bom = _load_object(paths.monoparts(monoparts_revision) / "bom.json", "active BOM")
        return cls(Path(session_root).resolve(), assembly, bom,
                   paths.preprocessing / "images", assembly_revision, monoparts_revision)


def build_report(context: EngineeringPowerPointContext | str | Path,
                 sections: Sequence[str] = ("assembly", "monopart"),
                 part_ids: Sequence[str] | None = None) -> Path:
    """Build and save one versioned report from one active artifact snapshot."""
    _require_pptx()
    if not isinstance(context, EngineeringPowerPointContext):
        context = EngineeringPowerPointContext.from_session(context)
    selected_sections = tuple(sections)
    if not selected_sections or any(item not in {"assembly", "monopart"} for item in selected_sections):
        raise ValueError("sections must contain only 'assembly' and/or 'monopart'")
    parts = _parts(context.bom, part_ids)
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    _remove_default_slides(presentation)
    _cover(presentation, context, len(parts))
    if "assembly" in selected_sections:
        _render_assembly(presentation, context)
    if "monopart" in selected_sections:
        for part in parts:
            _render_part(presentation, context, part)
    output_dir = context.session_root / "09_user_agent" / "powerpoint_exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = output_dir / f"engineering_report_{stamp}.pptx"
    presentation.save(output)
    return output


def _render_assembly(presentation: Any, context: EngineeringPowerPointContext) -> None:
    slide = _slide(presentation, "Assembly")
    _title(slide, _display(context.assembly.get("assembly_name_guess"), "Assembly overview"))
    image = _find_image(context.images_root, "assembly", "iso1")
    if image:
        from pptx.util import Inches
        slide.shapes.add_picture(str(image), Inches(8.55), Inches(1.25), width=Inches(4.2))
    else:
        _placeholder(slide, "Assembly iso1 image unavailable")
    selected = {
        "primary_function": context.assembly.get("primary_function"),
        "assembly_description": context.assembly.get("assembly_description"),
    }
    _add_json_text(slide, selected, left=0.65, top=1.25, width=7.5, height=5.65)


def _render_part(presentation: Any, context: EngineeringPowerPointContext,
                 part: Mapping[str, Any]) -> None:
    slide = _slide(presentation, "Monopart")
    analysis = part.get("part_analysis") if isinstance(part.get("part_analysis"), Mapping) else {}
    name = _display(analysis.get("part_name_guess") or part.get("name"), "Unnamed part")
    _title(slide, f"{name} · {part.get('part_id', 'unknown ID')}")
    image = _find_image(context.images_root, str(part.get("part_id", "")), "iso1")
    if image:
        from pptx.util import Inches
        slide.shapes.add_picture(str(image), Inches(8.55), Inches(1.25), width=Inches(4.2))
    else:
        _placeholder(slide, "Part iso1 image unavailable")
    selected = {
        "part_identification": analysis.get("part_identification"),
        "intrinsic_summary": analysis.get("intrinsic_summary"),
    }
    _add_json_text(slide, selected, left=0.65, top=1.25, width=7.5, height=5.65)


def _component_slide(presentation: Any, bom: Mapping[str, Any]) -> None:
    slide = _slide(presentation, "Components")
    _title(slide, "Component overview")
    parts = _parts(bom, None)
    from pptx.util import Inches, Pt
    table = slide.shapes.add_table(max(1, len(parts) + 1), 4, Inches(0.65), Inches(1.35),
                                   Inches(12.0), Inches(5.2)).table
    for index, header in enumerate(("Part ID", "Name", "Quantity", "Source definition")):
        _cell(table.cell(0, index), header, bold=True)
    for row, part in enumerate(parts, 1):
        analysis = part.get("part_analysis") if isinstance(part.get("part_analysis"), Mapping) else {}
        values = (part.get("part_id"), analysis.get("part_name_guess") or part.get("name"),
                  part.get("quantity"), part.get("source_definition"))
        for column, value in enumerate(values):
            _cell(table.cell(row, column), value, bold=False)
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(12)


def _add_json_text(slide: Any, value: Any, *, left: float, top: float,
                   width: float, height: float) -> None:
    from pptx.util import Inches, Pt
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.clear()
    for index, (line, is_bullet) in enumerate(_flatten(value)):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        _add_markdown_paragraph(paragraph, line, is_bullet=is_bullet)
        paragraph.font.size = Pt(14 if index == 0 else 11)
        paragraph.font.name = "Aptos"


def _flatten(value: Any, prefix: str = "", is_bullet: bool = False) -> list[tuple[str, bool]]:
    if isinstance(value, Mapping):
        lines: list[tuple[str, bool]] = []
        for key, item in value.items():
            label = f"{prefix}{str(key).replace('_', ' ')}:"
            if isinstance(item, list):
                lines.append((label, False))
                lines.extend(_flatten(item, is_bullet=True))
            elif isinstance(item, Mapping):
                lines.append((label, False))
                lines.extend(_flatten(item))
            else:
                lines.extend(_flatten(item, f"{label} "))
        return lines
    if isinstance(value, list):
        lines: list[tuple[str, bool]] = []
        for item in value:
            item_lines = str(item).splitlines() or [""]
            for line in item_lines:
                lines.append((f"{prefix}{_strip_list_marker(line.strip())}", True))
        return lines or [(f"{prefix}—", is_bullet)]
    return [(f"{prefix}{_display(value)}", is_bullet)]


def _strip_list_marker(value: str) -> str:
    return re.sub(r"^(?:[-*]|\d+[.)])\s+", "", value)


def _add_markdown_paragraph(paragraph: Any, value: str, *, is_bullet: bool) -> None:
    """Write Markdown inline emphasis as editable runs and list items as bullets."""
    if is_bullet:
        from pptx.oxml.xmlchemy import OxmlElement

        properties = paragraph._p.get_or_add_pPr()
        bullet = OxmlElement("a:buChar")
        bullet.set("char", "•")
        properties.append(bullet)
    paragraph.clear()
    token_pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")
    position = 0
    for match in token_pattern.finditer(value):
        if match.start() > position:
            paragraph.add_run().text = value[position:match.start()]
        token = match.group(0)
        run = paragraph.add_run()
        if token.startswith("**"):
            run.text = token[2:-2]
            run.font.bold = True
        else:
            run.text = token[1:-1]
            run.font.italic = True
        position = match.end()
    if position < len(value):
        paragraph.add_run().text = value[position:]


def _find_image(root: Path, identifier: str, view: str) -> Path | None:
    if not root.is_dir():
        return None
    token = identifier.lower().replace(" ", "_")
    candidates = sorted(path for path in root.rglob("*")
                        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
                        and view.lower() in path.stem.lower())
    exact = [path for path in candidates
             if token and (token in path.stem.lower()
                           or token == path.parent.name.lower())]
    return (exact or candidates)[0] if (exact or candidates) else None


def _parts(bom: Mapping[str, Any], part_ids: Sequence[str] | None) -> list[Mapping[str, Any]]:
    parts = [part for part in bom.get("parts", []) if isinstance(part, Mapping)]
    if part_ids is None:
        return parts
    requested = set(part_ids)
    unknown = requested - {str(part.get("part_id")) for part in parts}
    if unknown:
        raise ValueError(f"Unknown part IDs: {sorted(unknown)}")
    return [part for part in parts if str(part.get("part_id")) in requested]


def _slide(presentation: Any, section: str) -> Any:
    from pptx.dml.color import RGBColor
    from pptx.util import Inches
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor(247, 250, 249)
    footer = slide.shapes.add_textbox(Inches(0.65), Inches(7.08), Inches(12), Inches(0.2))
    footer.text_frame.text = f"Engineering report · {section}"
    return slide


def _title(slide: Any, text: str) -> None:
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    box = slide.shapes.add_textbox(Inches(0.65), Inches(0.45), Inches(12), Inches(0.6))
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = text
    paragraph.font.name = "Aptos Display"
    paragraph.font.size = Pt(27)
    paragraph.font.bold = True
    paragraph.font.color.rgb = RGBColor(24, 75, 68)


def _placeholder(slide: Any, text: str) -> None:
    from pptx.util import Inches, Pt
    box = slide.shapes.add_textbox(Inches(8.55), Inches(3.0), Inches(4.2), Inches(1.0))
    paragraph = box.text_frame.paragraphs[0]
    paragraph.text = text
    paragraph.font.name = "Aptos"
    paragraph.font.size = Pt(16)


def _cover(presentation: Any, context: EngineeringPowerPointContext, count: int) -> None:
    slide = _slide(presentation, "Cover")
    _title(slide, _display(context.assembly.get("assembly_name_guess"), "Engineering report"))
    from pptx.util import Inches, Pt
    box = slide.shapes.add_textbox(Inches(0.75), Inches(2.0), Inches(11), Inches(2.5))
    box.text_frame.text = "Assembly and monopart engineering brief"
    for paragraph in box.text_frame.paragraphs:
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(20)


def _cell(cell: Any, value: Any, *, bold: bool) -> None:
    cell.text = _display(value)
    for paragraph in cell.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.name = "Aptos"
            run.font.bold = bold


def _display(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not available: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _remove_default_slides(presentation: Any) -> None:
    for slide in list(presentation.slides):
        presentation.slides._sldIdLst.remove(slide._element)


def _require_pptx() -> None:
    try:
        import pptx  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("PowerPoint export requires python-pptx") from exc
