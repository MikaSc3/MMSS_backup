"""Deterministic evidence collection and final report compilation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SUBPROCESSES = ("separation", "handling", "positioning", "joining")


def _read(value: Any) -> Any:
    return json.loads(Path(value).read_text(encoding="utf-8")) if isinstance(value, (str, Path)) else value


def _document(value: Any, label: str) -> dict[str, Any]:
    value = _read(value)
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must contain a JSON object")
    return dict(value)


def _assessment_documents(value: Any) -> list[dict[str, Any]]:
    value = _read(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw = list(value)
    elif isinstance(value, Mapping) and ("ffa_assessment" in value or "assessment" in value):
        raw = [value]
    elif isinstance(value, Mapping):
        raw = value.get("steps", value.get("step_assessments"))
    else:
        raw = None
    if not isinstance(raw, list) or not raw:
        raise ValueError("report_synthesis requires at least one FFA step assessment")
    documents = []
    for item in raw:
        item = _read(item)
        if not isinstance(item, Mapping):
            raise ValueError("Every FFA assessment must be an object or JSON path")
        step = item.get("step")
        if not isinstance(step, Mapping):
            step = {key: item.get(key) for key in
                    ("step_id", "step_description", "base_part", "joining_part", "joining_process")}
        assessment = item.get("ffa_assessment", item.get("assessment"))
        if type(step.get("step_id")) is not int or not isinstance(assessment, Mapping):
            raise ValueError("Every FFA assessment requires step.step_id and ffa_assessment")
        documents.append({"step": dict(step), "ffa_assessment": dict(assessment)})
    documents.sort(key=lambda item: item["step"]["step_id"])
    ids = [item["step"]["step_id"] for item in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("FFA assessments contain duplicate step IDs")
    return documents


def _score_document(value: Any) -> dict[str, Any]:
    scores = _document(value, "FFA scores")
    if not isinstance(scores.get("steps"), list) or not isinstance(scores.get("aggregate"), Mapping):
        raise ValueError("FFA scores require steps and aggregate")
    return scores


def _sequence_steps(value: Any) -> list[dict[str, Any]]:
    sequence = _document(value, "assembly sequence")
    steps = sequence.get("steps")
    return [dict(item) for item in steps] if isinstance(steps, list) else []


def _part_profiles(bom: Mapping[str, Any]) -> list[dict[str, Any]]:
    parts = bom.get("parts")
    instances = bom.get("instances", [])
    if not isinstance(parts, list):
        raise ValueError("Enriched BOM requires a parts list")
    quantities: dict[str, int] = {}
    if isinstance(instances, list):
        for instance in instances:
            if isinstance(instance, Mapping) and isinstance(instance.get("part_id"), str):
                quantities[instance["part_id"]] = quantities.get(instance["part_id"], 0) + 1
    profiles = []
    for part in parts:
        if not isinstance(part, Mapping) or not isinstance(part.get("part_id"), str):
            raise ValueError("Every BOM part requires part_id")
        part_id = part["part_id"]
        analysis = part.get("part_analysis", {})
        geometry = part.get("geometry", {}) if isinstance(part.get("geometry"), Mapping) else {}
        profiles.append({
            "part_id": part_id,
            "name": ((analysis.get("part_name_guess") if isinstance(analysis, Mapping) else None)
                     or part.get("name") or part.get("part_name")),
            "quantity": quantities.get(part_id, part.get("quantity_in_assembly", 1)),
            "color": part.get("color") or (analysis.get("part_color") if isinstance(analysis, Mapping) else None),
            "size": geometry.get("size", part.get("size")),
            "volume": geometry.get("volume", part.get("volume")),
            "surface_area": geometry.get("surface_area", part.get("surface_area")),
            "part_identification": analysis.get("part_identification") if isinstance(analysis, Mapping) else None,
            "intrinsic_summary": analysis.get("intrinsic_summary") if isinstance(analysis, Mapping) else None,
            "geometric_characteristics": analysis.get("geometric_characteristics") if isinstance(analysis, Mapping) else None,
            "source_ref": f"bom.parts.{part_id}",
        })
    return profiles


def _part_id_by_instance(bom: Mapping[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for instance in bom.get("instances", []):
        if (isinstance(instance, Mapping)
                and isinstance(instance.get("instance_id"), str)
                and isinstance(instance.get("part_id"), str)):
            mapping[instance["instance_id"]] = instance["part_id"]
    return mapping


def _canonical_part_ids(values: Sequence[Any], mapping: Mapping[str, str]) -> list[str]:
    return list(dict.fromkeys(mapping.get(value, value) for value in values
                              if isinstance(value, str)))


def _overview(value: Mapping[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "assembly_name": value.get("assembly_name"),
        "assembly_name_guess": value.get("assembly_name_guess"),
        "assembly_description": value.get("assembly_description"),
        "primary_function": value.get("primary_function"),
        "total_parts": value.get("total_parts") or sum(int(item.get("quantity") or 0) for item in profiles),
        "unique_parts": value.get("unique_parts") or len(profiles),
        "source_ref": "assembly_overview",
    }


def _drawback_candidates(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for document in documents:
        step_id = document["step"]["step_id"]
        assessment = document["ffa_assessment"]
        groups = (("base_part", assessment.get("design_drawbacks_base_part", [])),
                  ("joining_part", assessment.get("design_drawbacks_joining_parts", [])))
        for role, entries in groups:
            for group in entries if isinstance(entries, list) else []:
                if not isinstance(group, Mapping):
                    continue
                part_id = group.get("part_id")
                for drawback in group.get("drawbacks", []):
                    if not isinstance(drawback, Mapping):
                        continue
                    drawback_id = str(drawback.get("drawback_id") or "unknown")
                    ref = f"ffa_assessment.step_{step_id:03d}.drawbacks.{role}.{part_id}.{drawback_id}"
                    candidates.append({"source_ref": ref, "scope": "part", "step_id": step_id,
                                       "part_id": part_id, "drawback_id": drawback_id,
                                       "description": drawback.get("description"),
                                       "improvement_measure": drawback.get("improvement_measure")})
        for group in assessment.get("design_drawbacks_assembly", []):
            if not isinstance(group, Mapping):
                continue
            for drawback in group.get("drawbacks", []):
                if not isinstance(drawback, Mapping):
                    continue
                drawback_id = str(drawback.get("drawback_id") or "unknown")
                ref = f"ffa_assessment.step_{step_id:03d}.drawbacks.assembly.{drawback_id}"
                candidates.append({"source_ref": ref, "scope": "assembly", "step_id": step_id,
                                   "part_id": None, "drawback_id": drawback_id,
                                   "description": drawback.get("description"),
                                   "improvement_measure": drawback.get("improvement_measure")})
    return candidates


def _risk_candidates(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for document in documents:
        step, assessment = document["step"], document["ffa_assessment"]
        for item in assessment.get("overall_ffa", []):
            if not isinstance(item, Mapping) or item.get("subprocess") not in SUBPROCESSES:
                continue
            subprocess = item["subprocess"]
            candidates.append({
                "source_ref": f"ffa_assessment.step_{step['step_id']:03d}.overall_ffa.{subprocess}",
                "step_id": step["step_id"], "part_ids": [value for value in
                    (step.get("base_part"), step.get("joining_part")) if isinstance(value, str)],
                "subprocess": subprocess, "automation_potential": item.get("automation_potential"),
                "risks": item.get("risks"),
            })
    return candidates


def prepare_report_data(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    required = {"assembly_overview", "bom_enriched", "sequence", "ffa_assessments", "ffa_scores"}
    missing = sorted(name for name in required if artifacts.get(name) is None)
    if missing:
        raise ValueError(f"report_synthesis missing artifacts: {missing}")
    overview_doc = _document(artifacts["assembly_overview"], "assembly overview")
    bom = _document(artifacts["bom_enriched"], "BOM")
    documents = _assessment_documents(artifacts["ffa_assessments"])
    scores = _score_document(artifacts["ffa_scores"])
    sequence_steps = _sequence_steps(artifacts["sequence"])
    assessment_ids = {item["step"]["step_id"] for item in documents}
    score_ids = {item.get("step_id") for item in scores["steps"]}
    if assessment_ids != score_ids:
        raise ValueError("FFA assessment and scoring step IDs differ")
    sequence_ids = {item.get("step_id") for item in sequence_steps}
    if sequence_ids and not assessment_ids.issubset(sequence_ids):
        raise ValueError("FFA assessments reference steps absent from the assembly sequence")
    profiles = _part_profiles(bom)
    part_id_by_instance = _part_id_by_instance(bom)
    drawbacks = _drawback_candidates(documents)
    risks = _risk_candidates(documents)
    for item in drawbacks:
        if isinstance(item.get("part_id"), str):
            item["part_id"] = part_id_by_instance.get(item["part_id"], item["part_id"])
    for item in risks:
        item["part_ids"] = _canonical_part_ids(item.get("part_ids", []), part_id_by_instance)
    unknowns = []
    for document in documents:
        step_id = document["step"]["step_id"]
        for index, statement in enumerate(document["ffa_assessment"].get("additional_information_required", []), 1):
            unknowns.append({"source_ref": f"ffa_assessment.step_{step_id:03d}.unknowns.{index}",
                             "step_id": step_id, "statement": statement})
    return {
        "assembly_overview": _overview(overview_doc, profiles),
        "scorecard": {"aggregate": scores["aggregate"], "steps": [
            {**{key: item.get(key) for key in
                ("step_id", "subprocess_scores", "total_ffa", "coverage")},
             "source_ref": f"ffa_scoring.step_{item.get('step_id'):03d}"}
            for item in scores["steps"]], "mapping": scores.get("mapping")},
        "parts": profiles, "risk_candidates": risks,
        "drawback_candidates": drawbacks, "unknowns": unknowns,
        "_documents": documents, "_scores": scores,
        "_part_id_by_instance": part_id_by_instance,
    }


def prompt_evidence(prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {key: prepared[key] for key in
            ("assembly_overview", "scorecard", "parts", "risk_candidates",
             "drawback_candidates", "unknowns")}


def allowed_source_refs(prepared: Mapping[str, Any]) -> set[str]:
    refs = {item["source_ref"] for key in ("risk_candidates", "drawback_candidates", "unknowns")
            for item in prepared[key]}
    refs.add("assembly_overview")
    refs.update(item["source_ref"] for item in prepared["parts"])
    refs.update(f"ffa_scoring.step_{item['step_id']:03d}" for item in prepared["scorecard"]["steps"])
    return refs


def validate_insights(insights: Mapping[str, Any], prepared: Mapping[str, Any]) -> None:
    allowed = allowed_source_refs(prepared)
    improvement_refs = {item["source_ref"] for item in prepared["drawback_candidates"]
                        if item.get("improvement_measure")}
    part_ids = {item["part_id"] for item in prepared["parts"]}
    step_ids = {item["step"]["step_id"] for item in prepared["_documents"]}
    for kind in ("findings", "recommendations"):
        for item in insights[kind]:
            unknown_refs = set(item["source_refs"]) - allowed
            if unknown_refs:
                raise ValueError(f"Report {kind[:-1]} cites unknown sources: {sorted(unknown_refs)}")
            if kind == "findings":
                unknown_parts = set(item["part_ids"]) - part_ids
                if unknown_parts:
                    raise ValueError(f"Report finding references unknown parts: {sorted(unknown_parts)}")
                if set(item["step_ids"]) - step_ids:
                    raise ValueError(f"Report finding references unknown steps: {item['step_ids']}")
                if item["scope"] == "part" and not item["part_ids"]:
                    raise ValueError("Part-scoped report findings require part_ids")
                if item["scope"] == "step" and not item["step_ids"]:
                    raise ValueError("Step-scoped report findings require step_ids")
            elif item["origin"] == "source_derived" and not (
                    set(item["source_refs"]) & improvement_refs):
                raise ValueError("Source-derived recommendations must cite a supplied improvement")
            elif item["origin"] == "proposed_hypothesis" and not item["assumptions"]:
                raise ValueError("Proposed report recommendations require explicit assumptions")


def _step_records(prepared: Mapping[str, Any]) -> list[dict[str, Any]]:
    scores = {item["step_id"]: item for item in prepared["_scores"]["steps"]}
    records = []
    for document in prepared["_documents"]:
        step, assessment = document["step"], document["ffa_assessment"]
        score = scores[step["step_id"]]
        overall = {item["subprocess"]: item for item in assessment.get("overall_ffa", [])
                   if isinstance(item, Mapping) and item.get("subprocess") in SUBPROCESSES}
        subprocesses = {}
        for name in SUBPROCESSES:
            subprocesses[name] = {
                "score": score.get("subprocess_scores", {}).get(name),
                "automation_potential": overall.get(name, {}).get("automation_potential"),
                "risks": overall.get(name, {}).get("risks"),
                "classification_details": score.get("details", {}).get(name, {}),
                "source_ref": f"ffa_assessment.step_{step['step_id']:03d}.overall_ffa.{name}",
            }
        records.append({
            **{key: step.get(key) for key in ("step_id", "step_description", "base_part", "joining_part", "joining_process")},
            "total_ffa": score.get("total_ffa"), "subprocesses": subprocesses,
            "image_refs": [f"sequence_renderings/collage_step_{step['step_id']:02d}.png"],
        })
    return records


def compile_report(prepared: Mapping[str, Any], insights: Mapping[str, Any]) -> dict[str, Any]:
    insights = dict(insights)
    mapping = prepared.get("_part_id_by_instance", {})
    insights["findings"] = [
        {**item, "part_ids": _canonical_part_ids(item.get("part_ids", []), mapping)}
        for item in insights["findings"]
    ]
    validate_insights(insights, prepared)
    key_to_id = {item["finding_key"]: f"F-{index:03d}"
                 for index, item in enumerate(insights["findings"], 1)}
    findings = []
    for item in insights["findings"]:
        value = dict(item)
        value["finding_id"] = key_to_id[value.pop("finding_key")]
        value["validation_status"] = "unreviewed"
        findings.append(value)
    recommendations = []
    for index, item in enumerate(insights["recommendations"], 1):
        value = dict(item)
        value["recommendation_id"] = f"R-{index:03d}"
        value["addresses_findings"] = [key_to_id[key] for key in value["addresses_findings"]]
        value["validation_status"] = "unreviewed"
        recommendations.append(value)
    parts = []
    for source_part in prepared["parts"]:
        part = dict(source_part)
        part["finding_ids"] = [item["finding_id"] for item in findings
                                if part["part_id"] in item["part_ids"]]
        addressed = set(part["finding_ids"])
        part["recommendation_ids"] = [item["recommendation_id"] for item in recommendations
                                       if addressed.intersection(item["addresses_findings"])]
        parts.append(part)
    summary = [{"summary_id": f"S-{index:03d}", "statement": statement,
                "validation_status": "unreviewed"}
               for index, statement in enumerate(insights["executive_summary"], 1)]
    unknowns = [{**item, "validation_status": "unreviewed"} for item in prepared["unknowns"]]
    return {
        "assembly_overview": prepared["assembly_overview"],
        "executive_summary": summary,
        "scorecard": prepared["scorecard"],
        "key_findings": findings,
        "recommendations": recommendations,
        "steps": _step_records(prepared),
        "parts": parts,
        "assumptions_and_unknowns": unknowns,
        "provenance": {"source_artifacts": ["assembly_overview", "bom_enriched", "sequence",
                                              "ffa_assessments", "ffa_scores"]},
    }
