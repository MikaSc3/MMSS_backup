from __future__ import annotations

import json
import textwrap
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from evaluation.ffa_evaluator import (
    CATEGORY_WEIGHT,
    FIELD_TO_SUBPROCESS,
    SUBPROCESSES,
    CriterionRecord,
    _parse_assessment_file,
)
from evaluation.ffa_plots import _COLOR_GT, _step_ffa_from_records
from evaluation.ffa_scoring import get_criterion_weight, resolve_ffa_value, resolve_option_id


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _strip_validation_suffix(text: str) -> str:
    t = text.strip()
    if t.endswith("[x]"):
        return t[:-3].rstrip()
    if t.endswith("[]"):
        return t[:-2].rstrip()
    return t


def _normalize_item(item: Any) -> str:
    if isinstance(item, str):
        return _strip_validation_suffix(item)
    if isinstance(item, dict):
        if "statement" in item:
            return _strip_validation_suffix(str(item.get("statement", "")).strip())
        return _strip_validation_suffix(str(item).strip())
    return _strip_validation_suffix(str(item).strip())


def _normalize_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for x in value:
            t = _normalize_item(x)
            if t:
                out.append(t)
        return out
    t = _normalize_item(value)
    return [t] if t else []


def _clip_lines(items: List[str], max_items: int = 5, max_chars: int = 120) -> List[str]:
    clipped: List[str] = []
    for x in items[:max_items]:
        x = x.strip()
        clipped.append(x)
    return clipped


def _step_subprocess_lines(step: Dict[str, Any], subprocess_name: str) -> List[str]:
    """Build compact lines for one subprocess from step-level potential/risk fields."""
    potential = _normalize_text_list(step.get(f"{subprocess_name}_potential"))
    risks = _normalize_text_list(step.get(f"{subprocess_name}_risks"))

    lines: List[str] = []
    for p in potential:
        lines.append(f"Potential: {p}")
    for r in risks:
        lines.append(f"Risk: {r}")

    # Backward-compatible fallback for older report formats.
    if not lines:
        overall = _normalize_text_list(step.get("overall_ffa"))
        prefix = subprocess_name.lower()
        for item in overall:
            if item.lower().startswith(prefix):
                lines.append(item)

    if not lines:
        for r in _normalize_text_list(step.get("risks"))[:2]:
            lines.append(f"Risk: {r}")

    return _clip_lines(lines, max_items=4, max_chars=9999)


def _draw_box(
    ax,
    title: str,
    lines: List[str],
    title_color: str = "#0f5b55",
    wrap_width: Optional[int] = None,
    font_size: float = 9.0,
    line_step: float = 0.12,
) -> None:
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
    ax.text(0.02, 0.94, title, fontsize=10, fontweight="bold", color=title_color, va="top")
    y = 0.84

    if wrap_width is None:
        # Estimate a reasonable wrap width from actual box width and font size.
        # This avoids premature line breaks from static character limits.
        fig_w_in = ax.figure.get_size_inches()[0]
        box_w_in = max(ax.get_position().width * fig_w_in, 1e-3)
        chars_per_line = int((box_w_in * 72.0) / max(font_size * 0.56, 1e-3))
        effective_width = max(42, min(130, chars_per_line - 2))
    else:
        effective_width = wrap_width

    for line in lines:
        wrapped = (
            textwrap.wrap(
                " ".join(str(line).split()),
                width=effective_width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            if effective_width
            else [line]
        )
        for idx, chunk in enumerate(wrapped):
            prefix = "•  " if idx == 0 else "   "
            ax.text(0.04, y, f"{prefix}{chunk}", fontsize=font_size, va="top", color="#1f1f1f")
            y -= line_step
            if y < 0.07:
                break
        if y < 0.07:
            break


def _draw_placeholder(ax, title: str) -> None:
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
    ax.text(0.5, 0.57, "IMAGE PLACEHOLDER", ha="center", va="center", fontsize=11, color="#8a8a8a")
    ax.text(0.5, 0.43, title, ha="center", va="center", fontsize=9, color="#8a8a8a")


def _find_first_existing(candidates: List[Path]) -> Optional[Path]:
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def _find_step_iso_image(step_renderings_dir: Optional[Path], step_id: str) -> Optional[Path]:
    if not step_renderings_dir or not step_renderings_dir.exists():
        return None

    # Some callers pass the run directory; resolve to sequence_renderings if present.
    search_dir = step_renderings_dir
    nested = step_renderings_dir / "sequence_renderings"
    if nested.exists() and nested.is_dir():
        search_dir = nested

    sid = str(step_id).zfill(2)
    patterns = [
        f"step_{sid}_iso1_transp_0_0.png",
        f"step_{sid}_iso1_exp_transp_0_0.png",
        f"step_{sid}_iso2_transp_0_0.png",
        f"step_{sid}_iso2_exp_transp_0_0.png",
        f"step_{sid}_iso1*.png",
        f"step_{sid}_iso2*.png",
    ]
    for pat in patterns:
        matches = sorted(search_dir.glob(pat))
        if matches:
            return matches[0]
    return None


def _find_assembly_image(parts_root_dir: Optional[Path], assembly_name: str) -> Optional[Path]:
    if not parts_root_dir or not parts_root_dir.exists():
        return None
    assy_dir = parts_root_dir / f"assembly_{assembly_name}"
    if not assy_dir.exists():
        return None
    candidates = [
        assy_dir / f"{assembly_name}.STEP-iso1_exp_transp_0_0.png",
        assy_dir / f"{assembly_name}.STEP-iso1_transp_0_0.png",
        assy_dir / f"{assembly_name}.STEP-iso2_exp_transp_0_0.png",
        assy_dir / f"{assembly_name}.STEP-iso2_transp_0_0.png",
    ]
    p = _find_first_existing(candidates)
    if p:
        return p
    fallback = sorted(assy_dir.glob("*iso1*.png")) or sorted(assy_dir.glob("*iso2*.png"))
    return fallback[0] if fallback else None


def _find_part_image(parts_root_dir: Optional[Path], part_id: str) -> Optional[Path]:
    if not parts_root_dir or not parts_root_dir.exists():
        return None
    pdir = parts_root_dir / part_id
    if not pdir.exists():
        return None
    candidates = [
        pdir / f"{part_id}-highlighted-in-assy-isometric.png",
        pdir / f"{part_id}-iso1_transp_0_0.png",
        pdir / f"{part_id}-iso4_transp_0_0.png",
    ]
    p = _find_first_existing(candidates)
    if p:
        return p
    fallback = sorted(pdir.glob("*.png"))
    return fallback[0] if fallback else None


def _draw_image_or_placeholder(ax, image_path: Optional[Path], title: str) -> None:
    if image_path and image_path.exists():
        ax.axis("off")
        ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
        try:
            img = mpimg.imread(str(image_path))
            ax.imshow(img)
            # Keep the original image aspect ratio to avoid visual skew.
            ax.set_aspect("equal")
            return
        except Exception:
            pass
    _draw_placeholder(ax, title)


def _build_records_from_assessment(assembly_name: str, assessment_file: Path) -> List[CriterionRecord]:
    steps = _parse_assessment_file(assessment_file)
    records: List[CriterionRecord] = []

    for step_key, step_data in steps.items():
        step_id = str(step_data.get("step_id", step_key))
        step_desc = str(step_data.get("step_description", step_id))
        assessment = step_data.get("assessment") or {}

        for sp in SUBPROCESSES:
            sp_data = assessment.get(sp) or {}
            for field_name, raw_val in sp_data.items():
                if field_name not in FIELD_TO_SUBPROCESS:
                    continue

                ffa_val = resolve_ffa_value(field_name, raw_val)
                opt_id = resolve_option_id(field_name, raw_val)
                if ffa_val is None or opt_id is None:
                    continue

                records.append(
                    CriterionRecord(
                        assembly_id=assembly_name,
                        step_id=step_id,
                        step_description=step_desc,
                        category=sp,
                        field_name=field_name,
                        criterion_weight=get_criterion_weight(field_name),
                        category_weight=CATEGORY_WEIGHT,
                        gt_option_id=int(opt_id),
                        pred_option_id=int(opt_id),
                        gt_ffa_value=float(ffa_val),
                        pred_ffa_value=float(ffa_val),
                        abs_error=0.0,
                        run_id="",
                    )
                )

    return records


def _compute_metrics(records: List[CriterionRecord]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    step_scores = _step_ffa_from_records(records, use_gt=True)

    step_recs: Dict[str, List[CriterionRecord]] = defaultdict(list)
    for r in records:
        step_recs[str(r.step_id)].append(r)

    def _k(s: str):
        try:
            return int(s)
        except Exception:
            return s

    rows: List[Dict[str, Any]] = []
    for sid in sorted(step_recs.keys(), key=_k):
        recs = step_recs[sid]
        by_cat: Dict[str, float] = {}
        for cat in SUBPROCESSES:
            cat_recs = [r for r in recs if r.category == cat]
            if not cat_recs:
                by_cat[cat] = float("nan")
                continue
            vals = np.array([r.gt_ffa_value for r in cat_recs], dtype=float)
            ws = np.array([r.criterion_weight for r in cat_recs], dtype=float)
            w_sum = float(ws.sum())
            by_cat[cat] = float(np.dot(ws, vals) / w_sum) if w_sum > 0 else float("nan")

        step_score = _safe_float(step_scores.get(sid), default=float(np.nan))
        rows.append(
            {
                "step_id": sid,
                "step_description": recs[0].step_description,
                "separation": by_cat.get("separation", float("nan")),
                "handling": by_cat.get("handling", float("nan")),
                "positioning": by_cat.get("positioning", float("nan")),
                "joining": by_cat.get("joining", float("nan")),
                "step_ffa": step_score,
            }
        )

    df = pd.DataFrame(rows)
    assembly_score = float(np.nanmean(df["step_ffa"].values)) if not df.empty else float("nan")
    subprocess_scores = {
        "separation": float(np.nanmean(df["separation"].values)) if not df.empty else float("nan"),
        "handling": float(np.nanmean(df["handling"].values)) if not df.empty else float("nan"),
        "positioning": float(np.nanmean(df["positioning"].values)) if not df.empty else float("nan"),
        "joining": float(np.nanmean(df["joining"].values)) if not df.empty else float("nan"),
    }

    metrics = {
        "overall_ffa_score": assembly_score,
        "subprocess_scores": subprocess_scores,
        "n_steps": int(len(df)),
        "n_records": int(len(records)),
    }
    return metrics, df


def _save_step_plot(df_step: pd.DataFrame, assembly_name: str, out_png: Path) -> None:
    if df_step.empty:
        return

    step_ids = [str(x) for x in df_step["step_id"].tolist()]
    x = list(range(1, len(step_ids) + 1))
    y = [float(v) for v in df_step["step_ffa"].tolist()]

    fig, ax = plt.subplots(figsize=(max(7, len(step_ids) * 1.2 + 2), 5))
    fig.suptitle(f"{assembly_name}  -  FFA per Step", fontsize=11, fontweight="bold")
    ax.plot(x, y, color=_COLOR_GT, linewidth=2.0, zorder=6)
    ax.scatter(x, y, color=_COLOR_GT, s=70, zorder=7, edgecolors="white", linewidths=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels([f"Step {sid}" for sid in step_ids], fontsize=8.5)
    ax.set_xlabel("Assembly Step", fontsize=10)
    ax.set_ylabel("FFA Score", fontsize=10)
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, axis="y", linestyle="-", alpha=0.22)
    ax.grid(False, axis="x")
    ax.margins(x=0.03)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def _load_report(report_dir: Path, assembly_name: str) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    p1 = report_dir / f"{assembly_name}_ffa_report.json"
    p2 = report_dir / "ffa_report.json"
    for p in [p1, p2]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f), p
    return None, None


def _extract_step_overall_ffa_from_assessment(assessment_raw: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build {step_id: [overall_ffa bullet, ...]} from ffa_assessment step_assessments."""
    out: Dict[str, List[str]] = {}
    for step in assessment_raw.get("step_assessments") or []:
        sid = str(step.get("step_id", "")).strip()
        if not sid:
            continue
        overall_items = ((step.get("assessment") or {}).get("overall_ffa")) or []
        bullets: List[str] = []
        for item in overall_items:
            if not isinstance(item, dict):
                continue
            sp = str(item.get("subprocess") or "").strip()
            ap = str(item.get("automation_potential") or "").strip()
            rk = str(item.get("risks") or "").strip()
            parts = []
            if sp:
                parts.append(f"{sp.capitalize()}")
            if ap:
                parts.append(ap)
            if rk:
                parts.append(f"Risks: {rk}")
            line = " | ".join(parts).strip()
            if line:
                bullets.append(line)
        if bullets:
            out[sid] = bullets
    return out


def _enrich_report_with_overall_ffa(report: Dict[str, Any], assessment_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Build steps[].overall_ffa and steps[].risks from report step fields; fallback to assessment overall_ffa."""
    step_map = _extract_step_overall_ffa_from_assessment(assessment_raw)
    steps = report.get("steps") or []
    if not isinstance(steps, list):
        return report

    potential_fields = [
        "separation_potential",
        "handling_potential",
        "positioning_potential",
        "joining_potential",
    ]
    risk_fields = [
        "separation_risks",
        "handling_risks",
        "positioning_risks",
        "joining_risks",
    ]

    for st in steps:
        if not isinstance(st, dict):
            continue

        sid = str(st.get("step_id", "")).strip()

        # Prefer explicit report potentials for OVERALL FFA content.
        composed_overall: List[str] = []
        for field in potential_fields:
            composed_overall.extend(_normalize_text_list(st.get(field)))

        if composed_overall:
            st["overall_ffa"] = composed_overall
        elif (not st.get("overall_ffa")) and sid in step_map:
            st["overall_ffa"] = step_map[sid]

        # Build consolidated RISKS from per-subprocess risk fields.
        composed_risks: List[str] = []
        for field in risk_fields:
            composed_risks.extend(_normalize_text_list(st.get(field)))
        if composed_risks:
            st["risks"] = composed_risks
    return report


def _render_pdf(
    report: Dict[str, Any],
    metrics: Dict[str, Any],
    df_step: pd.DataFrame,
    step_plot_path: Path,
    out_pdf: Path,
    step_renderings_dir: Optional[Path] = None,
    parts_root_dir: Optional[Path] = None,
    *,
    report_version: int = 1,
) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    # A4 landscape (inches): 11.69 x 8.27
    page_size = (11.69, 8.27)

    assembly_name = str(report.get("assembly_name") or "Unknown Assembly")
    model_name = str(report.get("llm_model") or "n/a")
    primary_function = _clip_lines(_normalize_text_list(report.get("primary_function")), max_items=3, max_chars=120)

    al = report.get("assembly_level") or {}
    top_risks = _clip_lines(_normalize_text_list(al.get("drawbacks")), max_items=5, max_chars=115)
    top_improvements = _clip_lines(_normalize_text_list(al.get("improvements")), max_items=5, max_chars=115)

    overall = _safe_float(metrics.get("overall_ffa_score"), 0.0)

    with PdfPages(out_pdf) as pdf:
        # Page 1: Executive summary
        fig = plt.figure(figsize=page_size)

        # Header
        h = fig.add_axes([0.02, 0.86, 0.96, 0.12])
        h.axis("off")
        h.add_patch(Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#c9d4d2", linewidth=1.0))
        h.text(0.02, 0.58, assembly_name, fontsize=22, fontweight="bold", va="center", color="#10212b")
        h.text(0.02, 0.20, "Fitness for Automation Report", fontsize=15, va="center", color="#1e2a32")

        # Row 1
        a1 = fig.add_axes([0.02, 0.49, 0.23, 0.34])
        a2 = fig.add_axes([0.27, 0.49, 0.31, 0.34])
        a3 = fig.add_axes([0.60, 0.49, 0.38, 0.34])

        # FFA gauge (left)
        a1.axis("off")
        a1.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
        a1.text(0.5, 0.93, "OVERALL FFA SCORE", ha="center", va="center", fontsize=10, fontweight="bold", color="#0f5b55")
        g = fig.add_axes([0.055, 0.56, 0.17, 0.22], polar=True)
        g.set_theta_direction(-1)
        g.set_theta_offset(np.pi / 2)
        g.set_axis_off()
        th = np.linspace(0, 2 * np.pi, 240)
        g.plot(th, np.ones_like(th), color="#b7b9bc", linewidth=6)
        g.plot(np.linspace(0, 2 * np.pi * np.clip(overall, 0.0, 1.0), 160), np.ones(160), color="#57a60a", linewidth=6)
        a1.text(0.5, 0.50, f"{overall:.2f}", ha="center", va="center", fontsize=26, fontweight="bold", color="#10212b")
        a1.text(0.5, 0.36, "/ 1.00", ha="center", va="center", fontsize=14, color="#6f7378")
        if overall >= 0.75:
            lbl = "High Automation Potential"
        elif overall >= 0.50:
            lbl = "Medium Automation Potential"
        else:
            lbl = "Low Automation Potential"
        a1.text(0.5, 0.12, lbl, ha="center", va="center", fontsize=10, color="#3c9a10", fontweight="bold")

        # Assembly image placeholder
        assembly_img = _find_assembly_image(parts_root_dir, assembly_name)
        _draw_image_or_placeholder(a2, assembly_img, "Assembly Image")

        # Step graph (right)
        a3.axis("off")
        a3.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
        a3.text(0.5, 0.93, "FFA SCORE PER STEP", ha="center", va="center", fontsize=10, fontweight="bold", color="#0f5b55")
        chart = fig.add_axes([0.625, 0.55, 0.32, 0.24])
        if step_plot_path.exists():
            step_ids = [str(x) for x in df_step["step_id"].tolist()]
            x = list(range(1, len(step_ids) + 1))
            y = [float(v) for v in df_step["step_ffa"].tolist()]
            chart.plot(x, y, color=_COLOR_GT, linewidth=2.0)
            chart.scatter(x, y, color=_COLOR_GT, s=35, edgecolors="white", linewidths=0.6)
            chart.set_xticks(x)
            chart.set_xticklabels(step_ids, fontsize=8)
            chart.set_ylim(0.0, 1.0)
            chart.set_ylabel("FFA Score", fontsize=9)
            chart.set_xlabel("Assembly Step", fontsize=9)
            chart.grid(True, axis="y", alpha=0.22)
            chart.grid(False, axis="x")
            chart.spines["top"].set_visible(False)
            chart.spines["right"].set_visible(False)
        else:
            chart.axis("off")
            chart.text(0.5, 0.5, "Step-Plot missing", ha="center", va="center")

        # Row 2
        if report_version == 1:
            r = fig.add_axes([0.02, 0.17, 0.47, 0.28])
            i = fig.add_axes([0.51, 0.17, 0.47, 0.28])
            _draw_box(r, "TOP RISKS", top_risks, title_color="#be1e2d", font_size=8.6, line_step=0.095)
            _draw_box(i, "TOP IMPROVEMENTS", top_improvements, title_color="#15954c", font_size=8.6, line_step=0.095)
        else:
            function_box = fig.add_axes([0.02, 0.17, 0.96, 0.28])
            _draw_box(
                function_box,
                "PRIMARY FUNCTION",
                primary_function,
                title_color="#0f5b55",
                font_size=9.2,
                line_step=0.11,
            )

        pdf.savefig(fig)
        plt.close(fig)

        # Part pages are intentionally omitted from report V2.
        for part in (report.get("parts") or []) if report_version == 1 else []:
            pid = str(part.get("part_id") or "unknown")
            geom = _clip_lines(_normalize_text_list(part.get("geometric_characteristics")), max_items=5, max_chars=95)
            drawbacks = _clip_lines(_normalize_text_list(part.get("drawbacks")), max_items=5, max_chars=95)
            improvements = _clip_lines(_normalize_text_list(part.get("improvements")), max_items=5, max_chars=95)

            fig = plt.figure(figsize=page_size)
            h = fig.add_axes([0.02, 0.86, 0.96, 0.12])
            h.axis("off")
            h.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
            h.text(0.02, 0.50, f"Part ID: {pid}", fontsize=20, fontweight="bold", va="center")

            text_box = fig.add_axes([0.02, 0.49, 0.61, 0.34])
            _draw_box(text_box, "GEOMETRIC CHARACTERISTICS", geom, title_color="#0f5b55", font_size=8.8, line_step=0.10)

            img_box = fig.add_axes([0.65, 0.49, 0.33, 0.34])
            part_img = _find_part_image(parts_root_dir, pid)
            _draw_image_or_placeholder(img_box, part_img, f"Part Image - {pid}")

            dbox = fig.add_axes([0.02, 0.08, 0.47, 0.37])
            ibox = fig.add_axes([0.51, 0.08, 0.47, 0.37])
            _draw_box(dbox, "DRAWBACKS", drawbacks, title_color="#be1e2d", font_size=8.6, line_step=0.095)
            _draw_box(ibox, "IMPROVEMENTS", improvements, title_color="#15954c", font_size=8.6, line_step=0.095)

            pdf.savefig(fig)
            plt.close(fig)

        # Step pages
        step_ffa_map = {str(r["step_id"]): _safe_float(r["step_ffa"], float("nan")) for _, r in df_step.iterrows()}
        for step in report.get("steps") or []:
            sid = str(step.get("step_id") or "?")
            step_desc = _clip_lines(_normalize_text_list(step.get("step_description")), max_items=3, max_chars=110)
            separation_lines = _step_subprocess_lines(step, "separation")
            handling_lines = _step_subprocess_lines(step, "handling")
            positioning_lines = _step_subprocess_lines(step, "positioning")
            joining_lines = _step_subprocess_lines(step, "joining")
            step_ffa = _safe_float(step_ffa_map.get(sid), float("nan"))

            fig = plt.figure(figsize=page_size)
            h = fig.add_axes([0.02, 0.84, 0.96, 0.14])
            h.axis("off")
            h.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
            h.text(0.02, 0.73, f"Step ID: {sid}", fontsize=19, fontweight="bold", va="center")
            h.text(0.02, 0.44, "STEP DESCRIPTION", fontsize=10, fontweight="bold", color="#0f5b55", va="center")
            y_desc = 0.27
            for line in step_desc[:2]:
                wrapped_desc = textwrap.wrap(line, width=120, break_long_words=False, break_on_hyphens=False) or [line]
                for idx, chunk in enumerate(wrapped_desc[:2]):
                    prefix = "•  " if idx == 0 else "   "
                    h.text(0.03, y_desc, f"{prefix}{chunk}", fontsize=9, va="top", color="#1f1f1f")
                    y_desc -= 0.13
                    if y_desc < 0.05:
                        break
                if y_desc < 0.05:
                    break

            # Four subprocess text blocks stacked vertically (left side).
            sep_box = fig.add_axes([0.02, 0.63, 0.56, 0.17])
            han_box = fig.add_axes([0.02, 0.43, 0.56, 0.17])
            pos_box = fig.add_axes([0.02, 0.23, 0.56, 0.17])
            joi_box = fig.add_axes([0.02, 0.03, 0.56, 0.17])
            _draw_box(sep_box, "SEPARATION", separation_lines, title_color="#0f5b55", font_size=8.6, line_step=0.105)
            _draw_box(han_box, "HANDLING", handling_lines, title_color="#0f5b55", font_size=8.6, line_step=0.105)
            _draw_box(pos_box, "POSITIONING", positioning_lines, title_color="#0f5b55", font_size=8.6, line_step=0.105)
            _draw_box(joi_box, "JOINING", joining_lines, title_color="#0f5b55", font_size=8.6, line_step=0.105)

            # Right column: image and gauge use identical container sizes for alignment.
            img = fig.add_axes([0.60, 0.43, 0.38, 0.39])
            step_img = _find_step_iso_image(step_renderings_dir, sid)
            _draw_image_or_placeholder(img, step_img, f"Step Image - Step {sid}")

            gbox = fig.add_axes([0.60, 0.03, 0.38, 0.39])
            gbox.axis("off")
            gbox.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor="#c9d4d2", linewidth=1.0))
            gbox.text(0.5, 0.93, "FFA SCORE (STEP)", ha="center", va="center", fontsize=11, fontweight="bold", color="#0f5b55")

            g = fig.add_axes([0.665, 0.08, 0.25, 0.29], polar=True)
            g.set_theta_direction(-1)
            g.set_theta_offset(np.pi / 2)
            g.set_axis_off()
            th = np.linspace(0, 2 * np.pi, 240)
            g.plot(th, np.ones_like(th), color="#b7b9bc", linewidth=5)
            val = np.clip(step_ffa if not np.isnan(step_ffa) else 0.0, 0.0, 1.0)
            g.plot(np.linspace(0, 2 * np.pi * val, 160), np.ones(160), color="#0f8b5b", linewidth=5)
            gbox.text(0.5, 0.50, f"{val:.2f}", ha="center", va="center", fontsize=28, color="#0f8b5b", fontweight="bold")
            gbox.text(0.5, 0.36, "/ 1.00", ha="center", va="center", fontsize=14, color="#6f7378")

            pdf.savefig(fig)
            plt.close(fig)


def _render_pdf_with_fallback(
    *,
    preferred_path: Path,
    report: Dict[str, Any],
    metrics: Dict[str, Any],
    df_step: pd.DataFrame,
    step_plot_path: Path,
    step_renderings_dir: Optional[Path],
    parts_root_dir: Optional[Path],
    report_version: int,
) -> Path:
    candidates = [preferred_path]
    candidates.extend(
        preferred_path.with_name(f"{preferred_path.stem}_copy_{idx}{preferred_path.suffix}")
        for idx in range(2, 13)
    )
    for candidate in candidates:
        try:
            _render_pdf(
                report,
                metrics,
                df_step,
                step_plot_path,
                candidate,
                step_renderings_dir=step_renderings_dir,
                parts_root_dir=parts_root_dir,
                report_version=report_version,
            )
            return candidate
        except PermissionError:
            continue
    raise PermissionError(
        f"Could not write {preferred_path.name} because all candidate filenames are locked. "
        "Please close open PDF files and retry."
    )


def run_ffa_post_processing(
    *,
    ffa_assessment_dir: Path,
    ffa_report_dir: Path,
    assembly_name: str,
    output_root: Path,
    step_renderings_dir: Optional[Path] = None,
    parts_root_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Create assembly-level metrics, step-level metrics/plot, and a PDF report package."""
    assessment_file = ffa_assessment_dir / "ffa_assessment.json"
    if not assessment_file.exists():
        raise FileNotFoundError(f"FFA assessment not found: {assessment_file}")

    with open(assessment_file, "r", encoding="utf-8") as f:
        assessment_raw = json.load(f)

    output_root.mkdir(parents=True, exist_ok=True)

    records = _build_records_from_assessment(assembly_name, assessment_file)
    if not records:
        raise RuntimeError("No CriterionRecord entries could be computed from ffa_assessment.json")

    metrics, df_step = _compute_metrics(records)

    step_csv = output_root / f"{assembly_name}_step_level_metrics.csv"
    assy_json = output_root / "assembly_level_metrics.json"
    step_plot = output_root / f"{assembly_name}_step_ffa_plot.png"

    df_step.to_csv(step_csv, index=False)
    with open(assy_json, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    _save_step_plot(df_step, assembly_name, step_plot)

    report, report_path = _load_report(ffa_report_dir, assembly_name)
    if report is None:
        raise FileNotFoundError(
            f"FFA report not found in {ffa_report_dir} (expected {assembly_name}_ffa_report.json or ffa_report.json)"
        )

    report = _enrich_report_with_overall_ffa(report, assessment_raw)

    pdf_path = _render_pdf_with_fallback(
        preferred_path=output_root / f"{assembly_name}_ffa_report.pdf",
        report=report,
        metrics=metrics,
        df_step=df_step,
        step_plot_path=step_plot,
        step_renderings_dir=step_renderings_dir,
        parts_root_dir=parts_root_dir,
        report_version=1,
    )
    pdf_v2_path = _render_pdf_with_fallback(
        preferred_path=output_root / f"{assembly_name}_ffa_report_V2.pdf",
        report=report,
        metrics=metrics,
        df_step=df_step,
        step_plot_path=step_plot,
        step_renderings_dir=step_renderings_dir,
        parts_root_dir=parts_root_dir,
        report_version=2,
    )

    return {
        "metrics_csv": str(step_csv),
        "assembly_metrics_json": str(assy_json),
        "step_plot": str(step_plot),
        "pdf_report": str(pdf_path),
        "pdf_report_v2": str(pdf_v2_path),
        "report_source": str(report_path),
    }
