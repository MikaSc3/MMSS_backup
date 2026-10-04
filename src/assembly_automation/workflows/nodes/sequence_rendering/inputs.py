"""Artifact loading and sequence-state planning for sequence rendering."""

import json
from pathlib import Path
from typing import Any, Mapping


def load_mapping(value: Mapping[str, Any] | str | Path, name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value).resolve(strict=True)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {name}: {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return loaded


def unwrap_sequence(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    sequence = load_mapping(value, "assembly sequence")
    if not isinstance(sequence.get("steps"), list):
        raise ValueError("Assembly sequence requires a steps list")
    return sequence


def build_step_states(sequence: Mapping[str, Any], valid_instance_ids: set[str]) -> list[dict[str, Any]]:
    """Return deterministic before/after states in global execution order."""
    states = []
    assembled: list[str] = []
    seen: set[str] = set()
    steps = sequence.get("steps", [])
    expected = list(range(1, len(steps) + 1))
    actual = [step.get("step_id") for step in steps]
    if actual != expected:
        raise ValueError(f"Sequence step IDs must be consecutive: expected {expected}, got {actual}")
    for step in steps:
        joining = step.get("joining_part")
        joining_ids = [joining] if isinstance(joining, str) else list(joining or [])
        if not joining_ids:
            raise ValueError(f"Step {step['step_id']} has no joining_part")
        unknown = [item for item in joining_ids if item not in valid_instance_ids]
        if unknown:
            raise ValueError(f"Step {step['step_id']} references unknown instances: {unknown}")
        repeated = [item for item in joining_ids if item in seen]
        if repeated:
            raise ValueError(f"Instances occur in multiple steps: {repeated}")
        before = list(assembled)
        assembled.extend(joining_ids)
        seen.update(joining_ids)
        states.append({"step": dict(step), "joining": joining_ids,
                       "before": before, "after": list(assembled)})
    return states
