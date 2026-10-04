"""Common execution shell for configured structured-output LLM nodes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .execution import invoke_structured
from .llms import create_llm
from .prompting import PromptPayload
from .tools import resolve_tools


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_run_record(output_path: str | Path, node_id: str,
                     record: Mapping[str, Any]) -> str:
    """Persist execution-only data below the owning session's runlog."""
    artifact = Path(output_path).resolve()
    session_root = next((parent for parent in artifact.parents
                         if parent.joinpath("manifest.json").exists()
                         or parent.joinpath("planning_manifest.json").exists()
                         or parent.joinpath("01_input").is_dir()), artifact.parent)
    try:
        relative = artifact.relative_to(session_root).with_suffix("")
        base_name = re.sub(r"[^A-Za-z0-9._-]+", "__", relative.as_posix())
    except ValueError:
        base_name = artifact.stem
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    record_name = f"{stamp}__{base_name}.run.json"
    target = session_root / "10_runs" / node_id / record_name
    _write_json(target, dict(record))
    return str(target)


def run_llm_node(
    *,
    node_id: str,
    artifacts: Mapping[str, Any],
    settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any],
    build_payload: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any] | None], PromptPayload],
    get_schema: Callable[[str], type],
    context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one node invocation; workflow fan-out remains outside this function."""
    allowed = {"enabled", "prompts", "structured_output", "llm", "inputs", "tools", "execution"}
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"Unknown {node_id} settings: {sorted(unknown)}")
    if settings.get("enabled", True) is not True:
        return {"status": "disabled", "artifact": None}

    payload = build_payload(settings, artifacts, context)
    schema_id = str(settings.get("structured_output"))
    schema = get_schema(schema_id)
    llm_settings = settings.get("llm")
    if isinstance(llm_settings, str):
        profile_name, llm_overrides = llm_settings, {}
    elif isinstance(llm_settings, dict):
        profile_name = llm_settings.get("profile")
        llm_overrides = {key: value for key, value in llm_settings.items() if key != "profile"}
    else:
        profile_name, llm_overrides = None, {}
    if not isinstance(profile_name, str) or not profile_name:
        raise ValueError(f"{node_id}.llm must name an LLM profile")
    model = llm or create_llm(profile_name, llm_profiles, llm_overrides)

    tool_names = settings.get("tools", [])
    if not isinstance(tool_names, list) or any(not isinstance(name, str) for name in tool_names):
        raise ValueError(f"{node_id}.tools must be a list of registered names")
    tools = resolve_tools(tool_names, tool_registry)
    execution_settings = settings.get("execution", {})
    if not isinstance(execution_settings, dict):
        raise ValueError(f"{node_id}.execution must be a mapping")
    unknown_execution = set(execution_settings) - {"max_tool_rounds"}
    if unknown_execution:
        raise ValueError(f"Unknown {node_id}.execution settings: {sorted(unknown_execution)}")

    execution = invoke_structured(model, payload.messages, schema, tools=tools,
                                  max_tool_rounds=int(execution_settings.get("max_tool_rounds", 4)))
    product = execution["result"]
    run_record = {
        "inputs": payload.inputs,
        "images_used": payload.images,
        "execution": {
            "node": node_id,
            "llm_profile": profile_name,
            "llm_overrides": llm_overrides,
            "schema": schema_id,
            "prompt_ids": dict(settings["prompts"]),
            "prompt_hashes": payload.prompt_hashes,
            "token_usage": execution["token_usage"],
            "elapsed_seconds": execution["elapsed_seconds"],
            "tool_calls": execution["tool_calls"],
        },
    }
    artifact = Path(output_path).resolve() if output_path is not None else None
    run_record_path = None
    if artifact is not None:
        _write_json(artifact, product)
        run_record_path = write_run_record(artifact, node_id, run_record)
    return {"status": "complete", "artifact": str(artifact) if artifact else None,
            "result": product, "run_record": run_record,
            "run_record_path": run_record_path}
