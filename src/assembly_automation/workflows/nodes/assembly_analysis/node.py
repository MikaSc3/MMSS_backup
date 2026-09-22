"""Assembly-analysis LLM node."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.node import run_llm_node

from .inputs import build_assembly_analysis_prompt
from .structured_output import get_schema


def run_assembly_analysis(
    *,
    artifacts: Mapping[str, Any],
    settings: Mapping[str, Any],
    llm_profiles: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    llm: Any = None,
    tool_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze one assembly through the shared vanilla-node runtime."""
    return run_llm_node(node_id="assembly_analysis", artifacts=artifacts,
                        settings=settings, llm_profiles=llm_profiles,
                        build_payload=build_assembly_analysis_prompt,
                        get_schema=get_schema, context=context,
                        output_path=output_path, llm=llm,
                        tool_registry=tool_registry)
