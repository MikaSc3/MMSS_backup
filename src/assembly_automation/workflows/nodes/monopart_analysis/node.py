"""Single-part analysis LLM node."""

from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_monopart_analysis_prompt, effective_settings
from .structured_output import get_schema


def run_monopart_analysis(
    *,
    part_id: str,
    artifacts: Mapping[str, Any],
    settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze exactly one unique BOM part; workflows fan out over part IDs."""
    if not isinstance(part_id, str) or not part_id.strip():
        raise ValueError("part_id must be a nonempty string")
    configured, _fanout = effective_settings(settings)
    invocation_context = {**dict(context or {}), "part_id": part_id}
    return run_llm_node(node_id="monopart_analysis", artifacts=artifacts,
                        settings=configured, llm_profiles=llm_profiles,
                        build_payload=build_monopart_analysis_prompt,
                        get_schema=get_schema, context=invocation_context,
                        output_path=output_path, llm=llm,
                        tool_registry=tool_registry)
