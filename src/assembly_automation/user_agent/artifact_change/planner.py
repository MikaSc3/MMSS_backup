"""Configured structured-output planner for one resolved artifact correction."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from assembly_automation.workflows.runtime.execution import invoke_structured
from assembly_automation.workflows.runtime.llms import create_llm
from assembly_automation.workflows.runtime.prompting import load_prompt
from assembly_automation.workflows.nodes.assembly_analysis.structured_output import AssemblyAnalysis
from assembly_automation.workflows.nodes.monopart_analysis.structured_output import SinglePartAnalysis
from assembly_automation.workflows.nodes.sequence_generation.structured_output import AssemblySequence, AssemblyStep

from .structured_output import get_schema
from .target_resolver import ResolvedTarget


def _field_guidance(fields: tuple[str, ...]) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for model in (AssemblyAnalysis, SinglePartAnalysis, AssemblySequence, AssemblyStep):
        for name, field in model.model_fields.items():
            if name in fields and name not in descriptions:
                descriptions[name] = field.description or f"Descriptive value for {name}."
    return {name: descriptions.get(name, f"Descriptive value for {name}.") for name in fields}


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

    def plan(self, resolved: ResolvedTarget, change: str) -> dict[str, Any]:
        instruction = change.strip()
        if not instruction:
            raise ValueError("change_artifact change cannot be empty")
        prompt_path = Path(__file__).with_name("prompts.yaml")
        system = load_prompt(prompt_path, self.prompts["system"], "system")
        human = load_prompt(prompt_path, self.prompts["human"], "human")
        context = {
            "target": resolved.label,
            "editable_fields": list(resolved.editable_fields),
            "field_guidance": _field_guidance(resolved.editable_fields),
            "current_values": {key: resolved.current.get(key) for key in resolved.editable_fields},
            "user_change": instruction,
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
        edits = execution["result"].get("edits")
        if not isinstance(edits, list) or not edits:
            raise ValueError("Artifact-change planner returned no edits")
        changes: dict[str, str] = {}
        for edit in edits:
            field, value = edit.get("field"), edit.get("new_value")
            if field not in resolved.editable_fields:
                raise ValueError(f"Artifact-change planner selected read-only or unknown field: {field}")
            if field in changes:
                raise ValueError(f"Artifact-change planner repeated field: {field}")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Artifact-change planner returned empty value for {field}")
            if value.strip() == str(resolved.current.get(field, "")).strip():
                raise ValueError(f"Artifact-change planner returned unchanged field: {field}")
            changes[field] = value.strip()
        return {"changes": changes, "plan": execution["result"],
                "execution": {"llm_profile": self.profile, "llm_overrides": self.overrides,
                              "schema": self.schema_id, "token_usage": execution["token_usage"],
                              "prompt_ids": dict(self.prompts),
                              "prompt_hashes": {
                                  "system": sha256(system.encode("utf-8")).hexdigest(),
                                  "human": sha256(human.encode("utf-8")).hexdigest(),
                              },
                              "elapsed_seconds": execution["elapsed_seconds"]},
                "input": context}
