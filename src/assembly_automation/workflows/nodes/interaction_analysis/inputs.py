"""Resolve one sequence step into compact interaction-analysis evidence."""

import json
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.prompting import PromptPayload, build_prompt

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        result = dict(value)
    elif isinstance(value, (str, Path)):
        result = json.loads(Path(value).read_text(encoding="utf-8"))
    else:
        raise ValueError(f"{label} must be a mapping or JSON path")
    if not isinstance(result, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return result


def _sequence(value: Any) -> dict[str, Any]:
    sequence = _mapping(value, "assembly sequence")
    if not isinstance(sequence.get("steps"), list):
        raise ValueError("Assembly sequence requires a steps list")
    return sequence


def _joining_ids(step: Mapping[str, Any]) -> list[str]:
    value = step.get("joining_part")
    result = [value] if isinstance(value, str) else list(value or [])
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"Step {step.get('step_id')} requires joining instance IDs")
    return result


def _part_evidence(instance_id: str, instances: Mapping[str, Any], parts: Mapping[str, Any]) -> dict[str, Any]:
    instance = instances.get(instance_id)
    if instance is None:
        raise ValueError(f"BOM has no instance {instance_id!r}")
    definition = parts.get(instance.get("part_id"))
    if definition is None:
        raise ValueError(f"BOM has no definition for instance {instance_id!r}")
    return {"instance": instance, "part": definition}


def prepare_step_inputs(artifacts: Mapping[str, Any], step_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    sequence = _sequence(artifacts.get("sequence"))
    matches = [step for step in sequence["steps"] if step.get("step_id") == step_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one sequence step {step_id}, found {len(matches)}")
    step = dict(matches[0])
    bom = _mapping(artifacts.get("bom_enriched"), "enriched BOM")
    if not isinstance(bom.get("parts"), list) or not isinstance(bom.get("instances"), list):
        raise ValueError("Enriched BOM requires parts and instances lists")
    parts = {item.get("part_id"): item for item in bom["parts"] if isinstance(item, dict)}
    instances = {item.get("instance_id"): item for item in bom["instances"] if isinstance(item, dict)}
    joining = _joining_ids(step)
    base = step.get("base_part")
    joining_evidence = [_part_evidence(item, instances, parts) for item in joining]
    base_evidence = (_part_evidence(base, instances, parts) if isinstance(base, str)
                     else {"status": "initial_placement", "instance": None, "part": None})

    assembled_before: list[str] = []
    for prior in sequence["steps"]:
        if prior.get("step_id", 0) >= step_id:
            break
        assembled_before.extend(_joining_ids(prior))
    relevant_ids = set(assembled_before) | set(joining)
    spatial = (_mapping(artifacts["spatial_relations"], "spatial relations")
               if artifacts.get("spatial_relations") is not None else {})
    pairs = [item for item in spatial.get("pairs", []) if isinstance(item, dict)
             and item.get("part_a") in relevant_ids and item.get("part_b") in relevant_ids
             and (item.get("part_a") in joining or item.get("part_b") in joining)]
    spatial_context = {"unit": spatial.get("unit", "mm"), "assembled_before": assembled_before,
                       "joining_instances": joining, "relevant_pairs": pairs}

    interlocking = (_mapping(artifacts["interlocking"], "interlocking")
                    if artifacts.get("interlocking") is not None else {})
    part_results = []
    for item in interlocking.get("parts", []):
        if not isinstance(item, dict) or item.get("instance_id") not in joining:
            continue
        directions = []
        for direction in item.get("blocked_directions", []):
            if not isinstance(direction, dict):
                continue
            blockers = [blocker for blocker in direction.get("blockers", []) if blocker in relevant_ids]
            directions.append({**direction, "blockers": blockers, "blocked": bool(blockers)})
        if not directions:
            part_results.append({**item, "sequence_state_filter": "no_direction_records_to_filter"})
            continue
        blocked = [direction for direction in directions if direction["blocked"]]
        free = [direction.get("direction") for direction in directions if not direction["blocked"]]
        part_results.append({**item, "blocked_directions": directions,
                             "blocked_direction_count": len(blocked), "free_directions": free,
                             "sequence_state_filter": "assembled_before_plus_joining"})
    blocker_edges = [item for item in interlocking.get("blocker_edges", []) if isinstance(item, dict)
                     and item.get("blocked_part") in joining and item.get("blocker") in relevant_ids]
    interlocking_context = {"method": interlocking.get("method"), "joining_parts": part_results,
                            "relevant_blocker_edges": blocker_edges,
                            "limitations": interlocking.get("limitations", [])}

    prepared = {**artifacts, "assembly_step": step, "base_part": base_evidence,
                "joining_parts": joining_evidence, "step_spatial_relations": spatial_context,
                "step_interlocking": interlocking_context}
    context = {"step_id": step_id, "step_description": step.get("step_description", ""),
               "belongs_to": step.get("belongs_to", ""),
               "base_instance_id": base or "none (initial placement)",
               "joining_instance_ids": ", ".join(joining),
               "joining_part_id": joining_evidence[0]["part"]["part_id"],
               "joining_process": step.get("joining_process", "")}
    return prepared, context


def effective_settings(settings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = {"enabled", "llm", "prompts", "structured_output", "tools", "execution", "inputs", "fanout"}
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"Unknown interaction_analysis settings: {sorted(unknown)}")
    fanout = settings.get("fanout", {})
    if not isinstance(fanout, dict) or set(fanout) - {"parallel", "max_workers"}:
        raise ValueError("interaction_analysis.fanout supports parallel and max_workers")
    if type(fanout.get("parallel", True)) is not bool:
        raise ValueError("interaction_analysis.fanout.parallel must be boolean")
    if type(fanout.get("max_workers", 4)) is not int or fanout.get("max_workers", 4) < 1:
        raise ValueError("interaction_analysis.fanout.max_workers must be a positive integer")
    return {key: value for key, value in settings.items() if key != "fanout"}, dict(fanout)


def build_interaction_prompt(settings: Mapping[str, Any], artifacts: Mapping[str, Any],
                             context: Mapping[str, Any] | None = None) -> PromptPayload:
    prompts = settings.get("prompts")
    if not isinstance(prompts, dict) or set(prompts) != {"system", "human"}:
        raise ValueError("interaction_analysis.prompts requires system and human IDs")
    inputs = settings.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("interaction_analysis.inputs must be a mapping")
    return build_prompt(prompts_path=PROMPTS_PATH, system_prompt_id=prompts["system"],
                        human_prompt_id=prompts["human"], input_specs=inputs,
                        artifacts=artifacts, context=context)
