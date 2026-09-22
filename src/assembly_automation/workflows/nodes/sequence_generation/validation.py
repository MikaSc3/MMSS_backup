"""Deterministic validation of generated assembly sequences."""

from typing import Any, Mapping


def validate_sequence(sequence: Mapping[str, Any], bom: Mapping[str, Any]) -> None:
    instances = bom.get("instances")
    steps = sequence.get("steps")
    if not isinstance(instances, list) or not isinstance(steps, list):
        raise ValueError("Sequence validation requires BOM instances and sequence steps")
    valid_ids = {item.get("instance_id") for item in instances if isinstance(item, dict)}
    if None in valid_ids or len(valid_ids) != len(instances):
        raise ValueError("Every BOM instance requires a unique instance_id")
    expected_steps = list(range(1, len(steps) + 1))
    actual_steps = [step.get("step_id") for step in steps]
    if actual_steps != expected_steps:
        raise ValueError(f"Sequence step IDs must be consecutive: expected {expected_steps}, got {actual_steps}")

    introduced: set[str] = set()
    first_context_steps: set[str] = set()
    for step in steps:
        context = step.get("belongs_to")
        if context not in first_context_steps:
            if step.get("base_part") is not None:
                raise ValueError(f"First step of {context!r} must have base_part null")
            first_context_steps.add(context)
        base = step.get("base_part")
        if base is not None:
            if base not in valid_ids:
                raise ValueError(f"Unknown base_part instance_id: {base}")
            if base not in introduced:
                raise ValueError(f"base_part must be introduced by an earlier step: {base}")
        joining = step.get("joining_part")
        joining_ids = [joining] if isinstance(joining, str) else list(joining or [])
        for instance_id in joining_ids:
            if instance_id not in valid_ids:
                raise ValueError(f"Unknown joining_part instance_id: {instance_id}")
            if instance_id in introduced:
                raise ValueError(f"Instance appears in more than one step: {instance_id}")
            introduced.add(instance_id)
    missing = sorted(valid_ids - introduced)
    if missing:
        raise ValueError(f"Sequence does not introduce every BOM instance: {missing}")
