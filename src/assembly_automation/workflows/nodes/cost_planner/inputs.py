from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.prompting import PromptPayload, build_prompt

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")


def build_cost_prompt(settings: Mapping[str, Any], artifacts: Mapping[str, Any],
                      context: Mapping[str, Any] | None = None) -> PromptPayload:
    return build_prompt(prompts_path=PROMPTS_PATH,
                        system_prompt_id=settings["prompts"]["system"],
                        human_prompt_id=settings["prompts"]["human"],
                        input_specs=settings["inputs"], artifacts=artifacts, context=context)
