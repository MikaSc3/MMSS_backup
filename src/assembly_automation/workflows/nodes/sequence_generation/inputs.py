"""Mode-aware configured inputs for sequence generation and revision."""

from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.prompting import PromptPayload, build_prompt

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")


def effective_settings(settings: Mapping[str, Any], mode: str) -> dict[str, Any]:
    if mode not in ("generate", "revise"):
        raise ValueError("sequence_generation mode must be generate or revise")
    prompts = settings.get("prompts")
    inputs = settings.get("inputs")
    if not isinstance(prompts, dict) or not isinstance(prompts.get(mode), dict):
        raise ValueError(f"sequence_generation.prompts.{mode} must be a mapping")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("common"), dict):
        raise ValueError("sequence_generation.inputs.common must be a mapping")
    mode_inputs = inputs.get(mode, {})
    if not isinstance(mode_inputs, dict):
        raise ValueError(f"sequence_generation.inputs.{mode} must be a mapping")
    return {**settings, "prompts": dict(prompts[mode]),
            "inputs": {**inputs["common"], **mode_inputs}}


def build_sequence_prompt(settings: Mapping[str, Any], artifacts: Mapping[str, Any],
                          context: Mapping[str, Any] | None = None) -> PromptPayload:
    prompts = settings.get("prompts")
    inputs = settings.get("inputs")
    if not isinstance(prompts, dict) or set(prompts) != {"system", "human"}:
        raise ValueError("Effective sequence prompts require system and human IDs")
    if not isinstance(inputs, dict):
        raise ValueError("Effective sequence inputs must be a mapping")
    return build_prompt(prompts_path=PROMPTS_PATH,
                        system_prompt_id=prompts["system"],
                        human_prompt_id=prompts["human"],
                        input_specs=inputs, artifacts=artifacts,
                        context=context)
