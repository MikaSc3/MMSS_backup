"""Configured LLM rewriter for one complete resolved artifact."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.execution import invoke_structured
from assembly_automation.workflows.runtime.llms import create_llm
from assembly_automation.workflows.runtime.prompting import load_prompt
from assembly_automation.workflows.nodes.assembly_analysis.structured_output import AssemblyAnalysis
from assembly_automation.workflows.nodes.automation_concept_synthesis.structured_output import (
    AutomationEquipmentList)
from assembly_automation.workflows.nodes.automation_idea.structured_output import (
    AutomationPlanningBrief)
from assembly_automation.workflows.nodes.cost_planner.structured_output import EquipmentPriceMatches
from assembly_automation.workflows.nodes.ffa_assessment.structured_output import FFAAssessment
from assembly_automation.workflows.nodes.interaction_analysis.structured_output import (
    InteractionAnalysis)
from assembly_automation.workflows.nodes.layout_planner.structured_output import EquipmentLayout
from assembly_automation.workflows.nodes.monopart_analysis.structured_output import (
    SinglePartAnalysis)
from assembly_automation.workflows.nodes.report_synthesis.structured_output import ReportInsights
from assembly_automation.workflows.nodes.sequence_generation.structured_output import AssemblySequence
from assembly_automation.workflows.nodes.step_planner_detailed.structured_output import (
    DetailedStepPlan)
from .structured_output import get_schema
from .target_resolver import ResolvedTarget


_NODE_CONTRACTS: dict[str, tuple[type[Any], str, str]] = {
    "assembly_overview": (
        AssemblyAnalysis, "$", "The node output is the complete stored artifact."),
    "bom": (
        SinglePartAnalysis, "$.parts[*].part_analysis",
        "The stored BOM is a deterministic wrapper; this schema applies to every part_analysis."),
    "sequence": (
        AssemblySequence, "$", "The node output is the complete stored artifact."),
    "interaction_analysis": (
        InteractionAnalysis, "$.steps[*].interaction_analysis",
        "The stored artifact aggregates one node output per assembly step."),
    "ffa_assessment": (
        FFAAssessment, "$.steps[*].ffa_assessment",
        "The stored artifact aggregates one node output per assembly step."),
    "report": (
        ReportInsights, "compiled report insight fields",
        "The report is compiled deterministically around this node output; preserve its wrapper."),
    "automation_idea": (
        AutomationPlanningBrief, "$", "The node output is the complete stored artifact."),
    "detailed_step_plans": (
        DetailedStepPlan, "$.steps[*]",
        "The stored artifact aggregates one detailed-step node output per assembly step."),
    "automation_concept": (
        AutomationEquipmentList, "$", "The node output is the complete stored artifact."),
    "layout": (
        EquipmentLayout, "$", "The node output is the complete stored artifact."),
    "cost_estimate": (
        EquipmentPriceMatches, "price-matching evidence used by the deterministic estimate",
        "The stored cost estimate is calculated deterministically from these matches; preserve its wrapper."),
}


def _node_contract(artifact: str, current: Mapping[str, Any]) -> dict[str, Any]:
    """Expose original node field descriptions without pretending wrappers are node outputs."""
    configured = _NODE_CONTRACTS.get(artifact)
    if configured is None:
        return {
            "source_model": None,
            "applies_at": "$",
            "note": "This is a deterministic artifact with no LLM-node structured output.",
            "current_root_keys": list(current),
        }
    model, applies_at, note = configured
    return {
        "source_model": model.__name__,
        "applies_at": applies_at,
        "note": note,
        "json_schema": model.model_json_schema(),
        "current_root_keys": list(current),
    }


class ArtifactChangePlanner:
    def __init__(self, settings: Mapping[str, Any], llm_profiles: Mapping[str, Any],
                 *, llm: Any = None):
        allowed = {"enabled", "llm", "prompts", "structured_output"}
        unknown = set(settings) - allowed
        if unknown:
            raise ValueError(f"Unknown artifact_change settings: {sorted(unknown)}")
        if settings.get("enabled", True) is not True:
            raise ValueError("artifact_change is disabled")
        prompts = settings.get("prompts")
        if not isinstance(prompts, Mapping) or not all(
                isinstance(prompts.get(key), str) for key in ("system", "human")):
            raise ValueError("artifact_change.prompts requires system and human IDs")
        llm_settings = settings.get("llm")
        if isinstance(llm_settings, str):
            profile, overrides = llm_settings, {}
        elif isinstance(llm_settings, Mapping):
            profile = llm_settings.get("profile")
            overrides = {key: value for key, value in llm_settings.items() if key != "profile"}
        else:
            profile, overrides = None, {}
        if not isinstance(profile, str) or not profile:
            raise ValueError("artifact_change.llm must name a profile")
        self.settings = dict(settings)
        self.prompts = dict(prompts)
        self.schema_id = str(settings.get("structured_output"))
        self.profile, self.overrides = profile, overrides
        self.llm_profiles, self._llm = llm_profiles, llm

    def rewrite(self, resolved: ResolvedTarget, change: str) -> dict[str, Any]:
        instruction = change.strip()
        if not instruction:
            raise ValueError("change_artifact change cannot be empty")
        prompt_path = Path(__file__).with_name("prompts.yaml")
        system = load_prompt(prompt_path, self.prompts["system"], "system")
        human = load_prompt(prompt_path, self.prompts["human"], "human")
        context = {
            "artifact_name": resolved.artifact,
            "revision_id": resolved.revision_id,
            "NODE_STRUCTURED_OUTPUT_CONTRACT": _node_contract(
                resolved.artifact, resolved.current),
            "USER_CHANGE": instruction,
            "CURRENT_ARTIFACT": resolved.current,
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": human + "\n\n" + json.dumps(
                context, ensure_ascii=False, indent=2)},
        ]
        if self._llm is None:
            self._llm = create_llm(self.profile, self.llm_profiles, self.overrides)
        model = self._llm
        execution = invoke_structured(model, messages, get_schema(self.schema_id))
        artifact_json = execution["result"].get("artifact_json")
        if not isinstance(artifact_json, str):
            raise ValueError("Artifact rewriter returned no complete artifact JSON")
        try:
            rewritten = json.loads(artifact_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Artifact rewriter returned invalid artifact JSON") from exc
        if not isinstance(rewritten, dict) or not rewritten:
            raise ValueError("Artifact rewriter returned no complete artifact")
        if rewritten == resolved.current:
            raise ValueError("Artifact rewriter returned the artifact unchanged")
        locations = execution["result"].get("changed_locations")
        if not isinstance(locations, list) or not locations:
            raise ValueError("Artifact rewriter returned no changed locations")
        return {"artifact": rewritten, "rewrite": execution["result"],
                "execution": {"llm_profile": self.profile, "llm_overrides": self.overrides,
                              "schema": self.schema_id, "token_usage": execution["token_usage"],
                              "prompt_ids": dict(self.prompts),
                              "prompt_hashes": {
                                  "system": sha256(system.encode("utf-8")).hexdigest(),
                                  "human": sha256(human.encode("utf-8")).hexdigest(),
                              },
                              "elapsed_seconds": execution["elapsed_seconds"]},
                "input": context}

    # Compatibility for callers/tests that still use the old method name.
    def plan(self, resolved: ResolvedTarget, change: str) -> dict[str, Any]:
        return self.rewrite(resolved, change)
