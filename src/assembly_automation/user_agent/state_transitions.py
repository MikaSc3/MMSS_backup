"""Single transition policy for user-facing artifact changes.

Artifacts/manifests remain the engineering record. This module only maintains
the agent projection used for capability eligibility and stale-output handling.
"""

from __future__ import annotations

from typing import Any, Mapping


_INVALIDATION: Mapping[str, tuple[str, ...]] = {
    "assembly": ("assembly", "monoparts", "sequence", "renderings", "final"),
    "monoparts": ("monoparts", "sequence", "renderings", "final"),
    "sequence": ("sequence", "renderings", "final"),
    "interaction": ("final",),
    "ffa_report": ("final",),
}


def invalidate(state: dict[str, Any], source: str) -> dict[str, Any]:
    """Mark downstream work stale after a substantive source change."""
    affected = _INVALIDATION.get(source)
    if affected is None:
        raise ValueError(f"Unknown transition source: {source}")
    stale = state["stale"]
    for key in affected:
        stale[key] = True
    return state


def mark_current(state: dict[str, Any], artifact: str) -> dict[str, Any]:
    """Mark one regenerated artifact current and preserve invalidation semantics."""
    if artifact not in {"assembly", "monoparts", "sequence", "final"}:
        raise ValueError(f"Unknown current artifact: {artifact}")
    state["stale"][artifact if artifact != "final" else "final"] = False
    if artifact == "sequence":
        state["stale"].update({"renderings": True, "final": True})
    elif artifact == "final":
        state["stale"].update({"renderings": False, "final": False})
    return state
