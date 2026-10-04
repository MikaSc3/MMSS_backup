from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_automation_idea_prompt
from .structured_output import get_schema


def run_automation_idea(*, artifacts: Mapping[str, Any], settings: Mapping[str, Any],
                        llm_profiles: Mapping[str, Any], context: Mapping[str, Any],
                        output_path: str | Path | None = None, llm: Any = None) -> dict[str, Any]:
    instruction = context.get("planning_instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("automation_idea requires nonempty planning_instruction")
    response = run_llm_node(node_id="automation_idea", artifacts=artifacts, settings=settings,
                            llm_profiles=llm_profiles, build_payload=build_automation_idea_prompt,
                            get_schema=get_schema, context=context, output_path=output_path, llm=llm)
    return response
