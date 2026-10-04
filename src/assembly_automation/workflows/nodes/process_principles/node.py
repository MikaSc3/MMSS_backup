from pathlib import Path
from typing import Any, Mapping
from assembly_automation.workflows.runtime.node import run_llm_node
from .inputs import build_process_principles_prompt
from .structured_output import get_schema

def run_process_principles(*, step_id: int, artifacts: Mapping[str, Any], settings: Mapping[str, Any], llm_profiles: Mapping[str, Any], context: Mapping[str, Any] | None = None, output_path: str | Path | None = None, llm: Any = None) -> dict[str, Any]:
    variables = {**dict(context or {}), "step_id": int(step_id)}
    configured = {key: value for key, value in settings.items() if key != "fanout"}
    response = run_llm_node(node_id="process_principles", artifacts=artifacts, settings=configured, llm_profiles=llm_profiles, build_payload=build_process_principles_prompt, get_schema=get_schema, context=variables, output_path=output_path, llm=llm)
    if response["status"] == "complete" and response["result"]["step_id"] != int(step_id):
        raise ValueError("process-principles output changed step_id")
    return response
