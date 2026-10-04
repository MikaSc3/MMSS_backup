"""Render the synthesized FFA report as a review-oriented PDF package."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import textwrap
from typing import Any, Mapping

from assembly_automation.workflows.nodes.report_rendering.model import ImageResolver, load_report


PAGE_SIZE = (11.69, 8.27)  # A4 landscape
COLORS = {"primary": "#12333A", "accent": "#14866D", "risk": "#B33A3A",
          "muted": "#607177", "line": "#D6DFDD", "soft": "#F1F5F4"}


def _slug(value: Any) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "assembly")).strip("._")
    return result or "assembly"


def _plain(value: Any) -> str:
    if value in (None, ""):
        return "Not available"
    if isinstance(value, list):
        return "; ".join(_plain(item) for item in value)
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_plain(item)}" for key, item in value.items())
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _wrapped(value: Any, width: int = 70, max_lines: int = 8) -> list[str]:
    lines = textwrap.wrap(_plain(value), width=width, break_long_words=False,
                          break_on_hyphens=False)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + " …"
    return lines or ["Not available"]


def _header(fig, title: str, subtitle: str = "Fitness for Automation Report") -> None:
    axis = fig.add_axes([0.035, 0.875, 0.93, 0.095])
    axis.axis("off")
    axis.text(0, 0.68, title, fontsize=20, fontweight="bold", color=COLORS["primary"], va="center")
    axis.text(0, 0.18, subtitle, fontsize=9.5, color=COLORS["muted"], va="center")
    axis.plot([0, 1], [0, 0], color=COLORS["line"], linewidth=1, transform=axis.transAxes)


def _box(fig, bounds, title: str, items: list[str], *, color: str | None = None,
         width: int = 66, max_lines: int = 12, font_size: float = 8.5) -> None:
    axis = fig.add_axes(bounds)
    axis.set_facecolor("white")
    axis.set_xticks([]); axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color(COLORS["line"])
    axis.text(0.035, 0.94, title.upper(), transform=axis.transAxes, fontsize=10,
              fontweight="bold", color=color or COLORS["primary"], va="top")
    lines: list[str] = []
    for item in items:
        wrapped = _wrapped(item, width, max_lines=max_lines)
        lines.extend([f"• {wrapped[0]}", *[f"  {line}" for line in wrapped[1:]]])
    if not lines:
        lines = ["• None recorded"]
    lines = lines[:max_lines]
    axis.text(0.04, 0.84, "\n".join(lines), transform=axis.transAxes,
              fontsize=font_size, color="#26363B", va="top", linespacing=1.35)


def _image(fig, bounds, path: Path | None, label: str) -> None:
    import matplotlib.image as mpimg
    axis = fig.add_axes(bounds)
    axis.set_xticks([]); axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color(COLORS["line"])
    if path and path.is_file():
        axis.imshow(mpimg.imread(path))
        axis.set_aspect("auto")
    else:
        axis.text(0.5, 0.5, f"{label}\nunavailable", ha="center", va="center",
                  color=COLORS["muted"])


def _score(axis, label: str, value: Any, y: float) -> None:
    from matplotlib.patches import Rectangle
    numeric = float(value) if isinstance(value, (int, float)) else 0.0
    axis.text(0.02, y, label.title(), fontsize=8.5, color=COLORS["primary"], va="center")
    axis.add_patch(Rectangle(
        (0.30, y - 0.025), 0.54, 0.05, color=COLORS["soft"], transform=axis.transAxes))
    axis.add_patch(Rectangle(
        (0.30, y - 0.025), 0.54 * max(0, min(1, numeric)), 0.05,
        color=COLORS["accent"], transform=axis.transAxes))
    axis.text(0.88, y, f"{numeric:.2f}" if isinstance(value, (int, float)) else "n/a",
              fontsize=8.5, fontweight="bold", va="center")


def _linked(report: Mapping[str, Any], ids: list[str], source: str) -> list[dict[str, Any]]:
    wanted = set(ids)
    return [item for item in report[source]
            if item.get("finding_id" if source == "key_findings" else "recommendation_id") in wanted]


def _save_overview(pdf, report, images) -> None:
    import matplotlib.pyplot as plt
    overview, aggregate = report["assembly_overview"], report["scorecard"].get("aggregate", {})
    title = overview.get("assembly_name_guess") or overview.get("assembly_name") or "Assembly"
    findings = [item for item in report["key_findings"] if item.get("scope") == "assembly"]
    if not findings:
        findings = report["key_findings"]
    finding_ids = {item.get("finding_id") for item in findings}
    recommendations = [item for item in report["recommendations"]
                       if finding_ids.intersection(item.get("addresses_findings", []))]
    fig = plt.figure(figsize=PAGE_SIZE, facecolor="white")
    _header(fig, str(title), "Assembly overview")
    _image(fig, [0.04, 0.50, 0.29, 0.33], images.assembly(), "Assembly image")
    score_axis = fig.add_axes([0.36, 0.50, 0.25, 0.33]); score_axis.axis("off")
    total = aggregate.get("mean_total_ffa")
    score_axis.text(0.5, 0.88, "FINAL FFA SCORE", ha="center", fontsize=11,
                    fontweight="bold", color=COLORS["primary"])
    score_axis.text(0.5, 0.62, f"{total:.2f}" if isinstance(total, (int, float)) else "n/a",
                    ha="center", fontsize=38, fontweight="bold", color=COLORS["accent"])
    for index, name in enumerate(("separation", "handling", "positioning", "joining")):
        _score(score_axis, name, aggregate.get(f"mean_{name}_score"), 0.38 - index * 0.095)
    summary = [item.get("statement") for item in report["executive_summary"]]
    _box(fig, [0.64, 0.50, 0.32, 0.33], "Executive summary", summary,
         width=62, max_lines=12, font_size=7.8)
    _box(fig, [0.04, 0.08, 0.44, 0.36], "Design drawbacks",
         [item.get("statement") for item in findings[:5]], color=COLORS["risk"], max_lines=14)
    _box(fig, [0.52, 0.08, 0.44, 0.36], "Top improvements",
         [f"{item.get('action')} Expected effect: {item.get('expected_effect')}"
          for item in recommendations[:5]], color=COLORS["accent"], max_lines=14)
    pdf.savefig(fig); plt.close(fig)


def _save_sequence(pdf, report, sequence_renderings: Path | None) -> None:
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=PAGE_SIZE, facecolor="white")
    _header(fig, "Assembly sequence", "Approved sequence and evaluated step order")
    collage = sequence_renderings / "collage_sequence.png" if sequence_renderings else None
    _image(fig, [0.04, 0.43, 0.92, 0.40], collage, "Sequence overview")
    steps = [f"{item.get('step_id')}. {item.get('step_description')} "
             f"[{item.get('joining_process')}; FFA {_plain(item.get('total_ffa'))}]"
             for item in report["steps"]]
    _box(fig, [0.04, 0.07, 0.92, 0.31], "Sequence steps", steps,
         width=145, max_lines=14, font_size=8.2)
    pdf.savefig(fig); plt.close(fig)


def _save_part(pdf, report, part, images) -> None:
    import matplotlib.pyplot as plt
    findings = _linked(report, part.get("finding_ids", []), "key_findings")
    recommendations = _linked(report, part.get("recommendation_ids", []), "recommendations")
    fig = plt.figure(figsize=PAGE_SIZE, facecolor="white")
    _header(fig, f"{part.get('part_id')} · {_plain(part.get('name'))}", "Monopart assessment")
    _image(fig, [0.04, 0.48, 0.31, 0.35], images.part(str(part.get("part_id"))), "Part image")
    facts = [f"Quantity: {_plain(part.get('quantity'))}", f"Size: {_plain(part.get('size'))}",
             f"Identification: {_plain(part.get('part_identification'))}",
             f"Summary: {_plain(part.get('intrinsic_summary'))}"]
    _box(fig, [0.38, 0.48, 0.58, 0.35], "Part profile", facts, width=105, max_lines=13)
    _box(fig, [0.04, 0.08, 0.44, 0.34], "Design drawbacks",
         [item.get("statement") for item in findings], color=COLORS["risk"], max_lines=13)
    _box(fig, [0.52, 0.08, 0.44, 0.34], "Top improvements",
         [f"{item.get('action')} Expected effect: {item.get('expected_effect')}"
          for item in recommendations], color=COLORS["accent"], max_lines=13)
    pdf.savefig(fig); plt.close(fig)


def _save_step(pdf, step, images) -> None:
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=PAGE_SIZE, facecolor="white")
    _header(fig, f"Step {step.get('step_id')} · {_plain(step.get('step_description'))}",
            f"{_plain(step.get('joining_process'))} · Step FFA {_plain(step.get('total_ffa'))}")
    _image(fig, [0.04, 0.48, 0.40, 0.35], images.step(int(step["step_id"]), step.get("image_refs")), "Step image")
    score_axis = fig.add_axes([0.48, 0.48, 0.48, 0.35]); score_axis.axis("off")
    score_axis.text(0.02, 0.92, "SUBPROCESS SCORES", fontsize=10, fontweight="bold",
                    color=COLORS["primary"])
    for index, name in enumerate(("separation", "handling", "positioning", "joining")):
        _score(score_axis, name, step["subprocesses"][name].get("score"), 0.75 - index * 0.17)
    for index, name in enumerate(("separation", "handling", "positioning", "joining")):
        value = step["subprocesses"][name]
        text = [f"Automation potential: {_plain(value.get('automation_potential'))}",
                f"Risks: {_plain(value.get('risks'))}"]
        col, row = index % 2, index // 2
        _box(fig, [0.04 + col * 0.48, 0.26 - row * 0.19, 0.44, 0.16], name,
             text, width=73, max_lines=6, font_size=7.4)
    pdf.savefig(fig); plt.close(fig)


def run_pdf_report(*, report: str | Path | Mapping[str, Any], output_dir: str | Path,
                   image_roots: Mapping[str, str | Path] | None = None,
                   filename: str | None = None) -> dict[str, Any]:
    """Create one PDF from an existing synthesized report; performs no LLM calls."""
    from .pillow_renderer import render_pdf

    model = load_report(report)
    target = Path(output_dir).resolve(); target.mkdir(parents=True, exist_ok=True)
    images = ImageResolver(image_roots)
    overview = model["assembly_overview"]
    stem = _slug(overview.get("assembly_name_guess") or overview.get("assembly_name"))
    pdf_path = target / (filename or f"{stem}_ffa_report.pdf")
    sequence_root = Path(image_roots["sequence_renderings"]).resolve() if image_roots and image_roots.get("sequence_renderings") else None
    pages = render_pdf(model, images, sequence_root, pdf_path)
    manifest = {"status": "complete", "created_at": datetime.now(timezone.utc).isoformat(),
                "pdf": str(pdf_path), "pages": pages,
                "assembly_pages": 1, "sequence_pages": 1,
                "part_pages": len(model["parts"]), "step_pages": len(model["steps"]),
                "images": {"used": sorted(images.used), "missing": sorted(images.missing)},
                "llm_calls": 0}
    manifest_path = target / "pdf_report_manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return {"status": "complete", "artifact": str(pdf_path), "manifest": str(manifest_path),
            "result": manifest}
