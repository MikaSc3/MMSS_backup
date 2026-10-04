"""Configured inputs for one monopart-analysis invocation."""

from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.prompting import PromptPayload, build_prompt

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")


def effective_settings(settings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = {"enabled", "llm", "prompts", "structured_output", "tools", "execution", "inputs", "fanout"}
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"Unknown monopart_analysis settings: {sorted(unknown)}")
    fanout = settings.get("fanout", {})
    if not isinstance(fanout, dict) or set(fanout) - {"parallel", "max_workers"}:
        raise ValueError("monopart_analysis.fanout supports parallel and max_workers")
    if type(fanout.get("parallel", True)) is not bool:
        raise ValueError("monopart_analysis.fanout.parallel must be boolean")
    if type(fanout.get("max_workers", 4)) is not int or fanout.get("max_workers", 4) < 1:
        raise ValueError("monopart_analysis.fanout.max_workers must be a positive integer")
    return {key: value for key, value in settings.items() if key != "fanout"}, dict(fanout)


def build_monopart_analysis_prompt(
    settings: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> PromptPayload:
    if not context or not context.get("part_id"):
        raise ValueError("monopart_analysis requires part_id in invocation context")
    prompts = settings.get("prompts")
    inputs = settings.get("inputs")
    if not isinstance(prompts, dict) or set(prompts) != {"system", "human"}:
        raise ValueError("monopart_analysis.prompts requires exactly system and human IDs")
    if not isinstance(inputs, dict):
        raise ValueError("monopart_analysis.inputs must be a mapping")
    return build_prompt(prompts_path=PROMPTS_PATH,
                        system_prompt_id=prompts["system"],
                        human_prompt_id=prompts["human"],
                        input_specs=inputs, artifacts=artifacts,
                        context=context)
