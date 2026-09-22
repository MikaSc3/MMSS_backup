"""Initial generation and feedback-driven revision of assembly sequences."""

import json
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_sequence_prompt, effective_settings
from .structured_output import get_schema
from .validation import validate_sequence


def run_sequence_generation(
    *,
    mode: str,
    artifacts: Mapping[str, Any],
    settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an initial sequence or revise it from summarized feedback."""
    context = dict(context or {})
    if mode == "revise":
        if artifacts.get("initial_sequence") is None:
            raise ValueError("revise mode requires the initially generated sequence")
        feedback = context.get("user_feedback_summary")
        if not isinstance(feedback, str) or not feedback.strip():
            raise ValueError("revise mode requires nonempty summarized user feedback")
    configured = effective_settings(settings, mode)
    response = run_llm_node(node_id="sequence_generation", artifacts=artifacts,
                            settings=configured, llm_profiles=llm_profiles,
                            build_payload=build_sequence_prompt, get_schema=get_schema,
                            context=context, output_path=None, llm=llm,
                            tool_registry=tool_registry, result_key="sequence")
    if response["status"] != "complete":
        return response
    bom_source = artifacts.get("bom_enriched")
    if bom_source is None:
        raise ValueError("sequence_generation requires bom_enriched")
    bom = dict(bom_source) if isinstance(bom_source, Mapping) else json.loads(Path(bom_source).read_text(encoding="utf-8"))
    validate_sequence(response["result"]["sequence"], bom)
    response["result"]["execution"]["mode"] = mode
    artifact = Path(output_path).resolve() if output_path is not None else None
    if artifact is not None:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        temporary = artifact.with_suffix(artifact.suffix + ".tmp")
        temporary.write_text(json.dumps(response["result"], ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(artifact)
        response["artifact"] = str(artifact)
    return response
