"""One configured FFA assessment for one assembly step."""

import json
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node, write_run_record

from .inputs import build_ffa_prompt, effective_settings, prepare_ffa_inputs
from .structured_output import get_schema


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def run_ffa_assessment(
    *,
    step_id: int,
    artifacts: Mapping[str, Any],
    settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess one step; workflow code owns fan-out and final aggregation."""
    if type(step_id) is not int or step_id < 1:
        raise ValueError("ffa_assessment step_id must be a positive integer")
    configured, _fanout = effective_settings(settings)
    if configured.get("enabled", True) is not True:
        return {"status": "disabled", "artifact": None}
    prepared, derived_context = prepare_ffa_inputs(artifacts, step_id)
    invocation_context = {**dict(context or {}), **derived_context}
    response = run_llm_node(
        node_id="ffa_assessment", artifacts=prepared, settings=configured,
        llm_profiles=llm_profiles, build_payload=build_ffa_prompt,
        get_schema=get_schema, context=invocation_context, output_path=None,
        llm=llm, tool_registry=tool_registry)
    if response["status"] != "complete":
        return response
    result = {"step": prepared["assembly_step"], "ffa_assessment": response["result"]}
    artifact = Path(output_path).resolve() if output_path is not None else None
    run_record_path = None
    if artifact is not None:
        _write_json(artifact, result)
        run_record_path = write_run_record(
            artifact, "ffa_assessment", response["run_record"])
    return {"status": "complete", "artifact": str(artifact) if artifact else None,
            "result": result, "run_record": response["run_record"],
            "run_record_path": run_record_path}
