"""Evidence-bound final report synthesis node."""

import json
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node, write_run_record

from .inputs import build_report_prompt
from .report_data import compile_report, prepare_report_data, prompt_evidence
from .structured_output import get_schema


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def run_report_synthesis(
    *, artifacts: Mapping[str, Any], settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any], context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None, llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile deterministic report data around one small synthesis call."""
    if settings.get("enabled", True) is not True:
        return {"status": "disabled", "artifact": None}
    prepared = prepare_report_data(artifacts)
    response = run_llm_node(
        node_id="report_synthesis", artifacts={"report_evidence": prompt_evidence(prepared)},
        settings=settings, llm_profiles=llm_profiles, build_payload=build_report_prompt,
        get_schema=get_schema, context=context, output_path=None, llm=llm,
        tool_registry=tool_registry)
    if response["status"] != "complete":
        return response
    report = compile_report(prepared, response["result"])
    artifact = Path(output_path).resolve() if output_path is not None else None
    run_record_path = None
    if artifact is not None:
        _write_json(artifact, report)
        run_record_path = write_run_record(
            artifact, "report_synthesis", response["run_record"])
    return {"status": "complete", "artifact": str(artifact) if artifact else None,
            "result": report, "run_record": response["run_record"],
            "run_record_path": run_record_path}
