from __future__ import annotations

from typing import Any

from ..selection import SelectionContext


def _view_index(value: Any, image_count: int) -> int:
    """Normalize persisted widget state from this and earlier UI versions."""
    if type(value) is int and 0 <= value < image_count:
        return value
    if isinstance(value, str) and value.isdigit():
        index = int(value)
        if 0 <= index < image_count:
            return index
    return 0


def _show_image(st: Any, path: Any, *, caption: str | None = None) -> bool:
    try:
        st.image(str(path), width="stretch", caption=caption)
        return True
    except (OSError, ValueError):
        st.caption("Image is being updated…")
        return False


def images_for_selection(entries: list[Any], selection: SelectionContext | None) -> list[Any]:
    """Select visual evidence for the artifact navigator's current context."""
    if selection is None:
        return []
    if selection.scope == "assembly":
        chosen = [entry for entry in entries if entry.category == "assembly"]
    elif selection.scope == "part":
        chosen = [entry for entry in entries
                  if entry.category == "part" and entry.part_id == selection.entity_id]
    elif selection.scope == "sequence":
        chosen = [entry for entry in entries if entry.category not in {"assembly", "part"}]
    elif selection.scope in {"interaction", "ffa"}:
        chosen = [entry for entry in entries
                  if entry.category not in {"assembly", "part", "sequence_overview"}
                  and str(entry.step_id) == str(selection.step_id)]
    elif selection.scope == "layout":
        chosen = [entry for entry in entries if entry.category == "layout"]
    else:
        chosen = []
    priority = {"sequence_overview": 0, "step_collage": 1, "assembled": 2,
                "highlighted": 3, "exploded": 4}
    return sorted(chosen, key=lambda entry: (
        priority.get(entry.category, 5), int(entry.step_id or 0), entry.label.lower()))


def render_visuals(st: Any, entries: list[Any], selection: SelectionContext | None = None,
                   *, show_header: bool = True, use_all_entries: bool = False) -> None:
    if show_header:
        st.markdown("#### Visual workspace")
        st.caption("Visual evidence for the selected output")
    images = entries if use_all_entries else images_for_selection(entries, selection)
    if not images:
        st.markdown("<div class='empty-visual'>VISUAL OUTPUT PENDING</div>",
                    unsafe_allow_html=True)
        return
    labels = [entry.label for entry in images]
    view_key = f"visual_view::{selection.key if selection else 'none'}"
    st.session_state[view_key] = _view_index(
        st.session_state.get(view_key, 0), len(images))
    chosen = st.selectbox("View", range(len(images)), key=view_key,
                          format_func=lambda index: labels[index],
                          label_visibility="collapsed")
    selected = images[chosen]
    _show_image(st, selected.path, caption=selected.label)
    if len(images) > 1:
        cols = st.columns(min(4, len(images)))
        for index, entry in enumerate(images[:8]):
            with cols[index % len(cols)]:
                _show_image(st, entry.path)
                st.caption(entry.label[:28])
