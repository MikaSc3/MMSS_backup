# -*- coding: utf-8 -*-
"""Visualization component for assembly, part, and assembly-step images."""

from pathlib import Path
from typing import List, Optional, Tuple
import re
import time
import base64

import streamlit as st


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
STAGE_HEIGHT_PX = 600


def render_image_box(session_root: Path = None, workflow_phase: str = "IDLE"):
    """Render the image group that best matches the active workflow context."""
    with st.container():
        if not session_root or not Path(session_root).exists():
            _render_empty_stage("Visualization pending")
            return

        session_root = Path(session_root)
        images, context_label = _get_context_images(session_root, workflow_phase)
        images = _filter_ready_images(images)

        if not images:
            _render_empty_stage(f"Waiting for {context_label}")
            return

        selected_img = _select_cycle_image(images, context_label)
        if selected_img is None:
            _render_empty_stage(f"Preparing {context_label}")
            return

        try:
            with selected_img.open("rb") as handle:
                image_bytes = handle.read()
            encoded = base64.b64encode(image_bytes).decode("ascii")
            mime = "image/png" if selected_img.suffix.lower() == ".png" else "image/jpeg"
            st.markdown(
                f"""
                <div style="{_stage_style()} background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                  <img src="data:{mime};base64,{encoded}" style="display:block; width:100%; height:100%; max-width:100%; max-height:100%; object-fit:contain;" />
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception as exc:
            st.error(f"Error loading image: {exc}")


def _stage_style() -> str:
    return (
        "position:relative; box-sizing:border-box; width:100%; max-width:100%; "
        f"height:{STAGE_HEIGHT_PX}px; max-height:calc(100vh - 22rem); min-height:280px; "
        "border:1px solid #D9E2E7; border-radius:12px; overflow:hidden; "
        "box-shadow:0 10px 28px rgba(17,24,39,0.06);"
    )


def _render_empty_stage(label: str):
    st.markdown(
        f"""
        <div style="{_stage_style()} background:#F7F9FA; display:flex; align-items:center; justify-content:center;">
          <div style="position:absolute; inset:14px; border:1px dashed #B8C4CC; border-radius:8px;"></div>
          <div style="color:#6B7280; font-size:1rem; font-weight:700; letter-spacing:0.04em; text-transform:uppercase;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_context_images(session_root: Path, workflow_phase: str, view_mode: str = "Auto") -> Tuple[List[Path], str]:
    progress_step = st.session_state.get("progress_step", 0)
    phase = (workflow_phase or "IDLE").upper()

    if view_mode == "Assembly":
        return _assembly_images(session_root), "Assembly"
    if view_mode == "Parts":
        part_id = _latest_analysed_part_id(session_root)
        if part_id:
            images = _part_images(session_root, part_id)
            if images:
                return images, f"Monopart {part_id}"
        return _all_part_images(session_root), "Monoparts"
    if view_mode == "Steps":
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            return _step_images(session_root, step_no), f"Assembly Step {step_no}"
        return _sequence_images(session_root), "Assembly Steps"
    if view_mode == "Sections":
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            images = _section_step_images(session_root, step_no)
            if images:
                return images, f"Interaction Sections - Step {step_no}"
        return _section_images(session_root), "Interaction Sections"
    if view_mode == "FFA":
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            return _step_images(session_root, step_no), f"FFA Context - Step {step_no}"
        return _assembly_images(session_root), "FFA Context"

    if progress_step in {1, 2, 3} or phase in {"PHASE_1", "PHASE_2A", "AGENT_1"}:
        return _assembly_images(session_root), "Assembly"

    if progress_step == 4 or phase in {"PHASE_2B", "PHASE_2B_MONOPARTS"}:
        part_id = _latest_analysed_part_id(session_root)
        if part_id:
            images = _part_images(session_root, part_id)
            if images:
                return images, f"Monopart {part_id}"
        return _all_part_images(session_root), "Monoparts"

    if progress_step == 8 or phase == "PHASE_4_INTERACTIONS":
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            images = _section_step_images(session_root, step_no)
            if images:
                return images, f"Interaction Sections - Step {step_no}"
        section_images = _section_images(session_root)
        if section_images:
            return section_images, "Interaction Sections"

    if progress_step in {7, 9} or phase in {"PHASE_4", "PHASE_4_RENDERING", "PHASE_4_FFA"}:
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            images = _step_images(session_root, step_no)
            if images:
                return images, f"Assembly Step {step_no}"
        return _sequence_images(session_root), "Assembly Steps"

    if progress_step >= 10 or phase in {"PHASE_4_REPORT", "AGENT_3", "DONE"}:
        step_no = _latest_rendered_step(session_root)
        if step_no is not None:
            return _step_images(session_root, step_no), f"Assembly Step {step_no}"
        return _assembly_images(session_root), "Assembly"

    sequence_images = _sequence_images(session_root)
    if sequence_images:
        step_no = _latest_rendered_step(session_root)
        label = f"Assembly Step {step_no}" if step_no is not None else "Assembly Sequence"
        return sequence_images, label

    assembly_images = _assembly_images(session_root)
    if assembly_images:
        return assembly_images, "Assembly"

    return _all_images(session_root), "Visualization"


def _suggested_view_mode(workflow_phase: str) -> str:
    progress_step = st.session_state.get("progress_step", 0)
    phase = (workflow_phase or "IDLE").upper()
    if progress_step in {1, 2, 3} or phase in {"PHASE_1", "PHASE_2A", "AGENT_1"}:
        return "Assembly"
    if progress_step == 4 or phase in {"PHASE_2B", "PHASE_2B_MONOPARTS"}:
        return "Parts"
    if progress_step == 8 or phase == "PHASE_4_INTERACTIONS":
        return "Sections"
    if progress_step in {7, 9} or phase in {"PHASE_4", "PHASE_4_RENDERING", "PHASE_4_FFA"}:
        return "Steps"
    if progress_step >= 10 or phase in {"PHASE_4_REPORT", "AGENT_3", "DONE"}:
        return "FFA"
    return "Assembly"


def _assembly_images(session_root: Path) -> List[Path]:
    candidates: List[Path] = []
    preprocessing_root = session_root / "preprocessing"
    for assembly_dir in preprocessing_root.rglob("assembly_*"):
        if not assembly_dir.is_dir():
            continue
        candidates.extend(_image_files(assembly_dir))
    return _sort_visuals([path for path in candidates if "part_" not in path.name.lower()])


def _part_images(session_root: Path, part_id: str) -> List[Path]:
    normalized = _normalize_part_id(part_id)
    candidates = [
        path for path in _all_part_images(session_root)
        if _normalize_part_id(path.name).startswith(normalized)
        or _normalize_part_id(path.parent.name).startswith(normalized)
    ]
    return _sort_visuals(candidates)


def _all_part_images(session_root: Path) -> List[Path]:
    candidates: List[Path] = []
    preprocessing_root = session_root / "preprocessing"
    for path in preprocessing_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES and _part_id_from_text(path.name):
            candidates.append(path)
    return _sort_visuals(candidates)


def _sequence_images(session_root: Path) -> List[Path]:
    candidates: List[Path] = []
    for sequence_dir in _sequence_rendering_dirs(session_root):
        candidates.extend(_image_files(sequence_dir))
    return _sort_visuals(candidates)


def _step_images(session_root: Path, step_no: int) -> List[Path]:
    pattern = f"step_{step_no:02d}_"
    return _sort_visuals([
        path
        for path in _sequence_images(session_root)
        if path.name.lower().startswith(pattern)
    ])


def _section_step_images(session_root: Path, step_no: int) -> List[Path]:
    return _sort_visuals([
        path
        for path in _step_images(session_root, step_no)
        if "section_" in path.name.lower()
    ])


def _section_images(session_root: Path) -> List[Path]:
    return _sort_visuals([
        path
        for path in _sequence_images(session_root)
        if "section_" in path.name.lower()
    ])


def _all_images(session_root: Path) -> List[Path]:
    return _sort_visuals([
        path
        for path in session_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ])


def _sequence_rendering_dirs(session_root: Path) -> List[Path]:
    dirs = [
        path for path in session_root.rglob("sequence_renderings")
        if path.is_dir()
    ]
    return sorted(dirs, key=_safe_mtime, reverse=True)


def _latest_rendered_step(session_root: Path) -> Optional[int]:
    newest: Optional[Tuple[float, int]] = None
    for path in _sequence_images(session_root):
        match = re.match(r"step_(\d+)_", path.name.lower())
        if not match:
            continue
        mtime = _safe_mtime(path)
        if mtime <= 0:
            continue
        item = (mtime, int(match.group(1)))
        if newest is None or item[0] > newest[0]:
            newest = item
    return newest[1] if newest else None


def _latest_analysed_part_id(session_root: Path) -> Optional[str]:
    enriched_dir = session_root / "enriched_parts"
    candidates = [
        path for path in enriched_dir.glob("part_*_Data_enriched*.json")
        if path.is_file()
    ]
    if not candidates:
        return _latest_part_image_id(session_root)
    latest = max(candidates, key=_safe_mtime)
    return _part_id_from_text(latest.name)


def _latest_part_image_id(session_root: Path) -> Optional[str]:
    images = _all_part_images(session_root)
    if not images:
        return None
    latest = max(images, key=_safe_mtime)
    return _part_id_from_text(latest.name) or _part_id_from_text(latest.parent.name)


def _part_id_from_text(text: str) -> Optional[str]:
    match = re.search(r"part[_-]?(\d{1,4})(?:_copy\d+)?", text.lower())
    if not match:
        return None
    return f"part_{int(match.group(1)):03d}"


def _normalize_part_id(text: str) -> str:
    part_id = _part_id_from_text(text)
    if part_id:
        return part_id
    return text.lower().replace("-", "_")


def _image_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    images: List[Path] = []
    try:
        children = list(folder.iterdir())
    except OSError:
        return images
    for path in children:
        try:
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES and "_temp" not in path.name.lower():
                images.append(path)
        except OSError:
            continue
    return images


def _filter_ready_images(images: List[Path]) -> List[Path]:
    ready: List[Path] = []
    seen = set()
    for path in images:
        try:
            resolved = str(path.resolve())
            if resolved in seen or path.stat().st_size <= 0:
                continue
            with path.open("rb") as handle:
                if not handle.read(32):
                    continue
            seen.add(resolved)
            ready.append(path)
        except OSError:
            continue
    return ready


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _select_cycle_image(images: List[Path], context_label: str) -> Optional[Path]:
    if not images:
        return None
    cycle_key = f"image_cycle_{context_label}_{len(images)}"
    index = int(time.time() / 2) % len(images)
    st.session_state[cycle_key] = index
    return images[index]


def _sort_visuals(images: List[Path]) -> List[Path]:
    priority_patterns = [
        "highlighted-in-assy",
        "iso1_transp_0_0",
        "iso1_exp",
        "iso2_transp_0_0",
        "iso2_exp",
        "section_xy_after",
        "section_xz_after",
        "section_yz_after",
        "section_xy_before",
        "section_xz_before",
        "section_yz_before",
    ]

    def score(path: Path):
        name = path.name.lower()
        step_match = re.match(r"step_(\d+)_", name)
        part_match = _part_id_from_text(name) or _part_id_from_text(path.parent.name) or ""
        priority = next((i for i, pattern in enumerate(priority_patterns) if pattern in name), 99)
        step = int(step_match.group(1)) if step_match else 0
        return (step, part_match, priority, name)

    return sorted(images, key=score)
