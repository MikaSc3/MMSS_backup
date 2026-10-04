"""Configured evidence assembly for one FFA step assessment."""

import json
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.nodes.interaction_analysis.inputs import prepare_step_inputs
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


def prepare_ffa_inputs(artifacts: Mapping[str, Any], step_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared, context = prepare_step_inputs(artifacts, step_id)
    interaction_source = artifacts.get("interaction_step")
    if interaction_source is None:
        interaction = None
    else:
        document = _mapping(interaction_source, "interaction step")
        interaction = document.get("interaction_analysis", document.get("InteractionAnalysisDetail", document))
        interaction_step = document.get("step")
        if isinstance(interaction_step, dict) and interaction_step.get("step_id") != step_id:
            raise ValueError(f"Interaction artifact belongs to step {interaction_step.get('step_id')}, expected {step_id}")
        if not isinstance(interaction, dict):
            raise ValueError("Interaction step requires an interaction_analysis object")
    prepared["interaction_analysis"] = interaction
    return prepared, context


def effective_settings(settings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = {"enabled", "llm", "prompts", "structured_output", "tools", "execution", "inputs", "fanout"}
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"Unknown ffa_assessment settings: {sorted(unknown)}")
    fanout = settings.get("fanout", {})
    if not isinstance(fanout, dict) or set(fanout) - {"parallel", "max_workers"}:
        raise ValueError("ffa_assessment.fanout supports parallel and max_workers")
    if type(fanout.get("parallel", True)) is not bool:
        raise ValueError("ffa_assessment.fanout.parallel must be boolean")
    if type(fanout.get("max_workers", 4)) is not int or fanout.get("max_workers", 4) < 1:
        raise ValueError("ffa_assessment.fanout.max_workers must be a positive integer")
    return {key: value for key, value in settings.items() if key != "fanout"}, dict(fanout)


def build_ffa_prompt(settings: Mapping[str, Any], artifacts: Mapping[str, Any],
                     context: Mapping[str, Any] | None = None) -> PromptPayload:
    prompts = settings.get("prompts")
    if not isinstance(prompts, dict) or set(prompts) != {"system", "human"}:
        raise ValueError("ffa_assessment.prompts requires system and human IDs")
    inputs = settings.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("ffa_assessment.inputs must be a mapping")
    return build_prompt(prompts_path=PROMPTS_PATH, system_prompt_id=prompts["system"],
                        human_prompt_id=prompts["human"], input_specs=inputs,
                        artifacts=artifacts, context=context)
