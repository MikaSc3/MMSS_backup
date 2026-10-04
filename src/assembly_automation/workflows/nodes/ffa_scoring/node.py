"""Deterministic scoring of per-step FFA classifications."""

import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from .mapping import FIELD_ENUMS, SUBPROCESSES, load_mapping


def _read(value: Any) -> Any:
    return json.loads(Path(value).read_text(encoding="utf-8")) if isinstance(value, (str, Path)) else value


def _normalise_assessments(value: Any) -> list[dict[str, Any]]:
    value = _read(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        documents = list(value)
    elif isinstance(value, Mapping) and "ffa_assessment" in value:
        documents = [value]
    elif isinstance(value, Mapping):
        documents = value.get("steps", value.get("step_assessments"))
        if documents is None:
            documents = list(value.values())
    else:
        raise ValueError("FFA scoring input must be a step artifact, list, aggregate object or JSON path")
    if not isinstance(documents, list) or not documents:
        raise ValueError("FFA scoring requires at least one step assessment")
    result = []
    for document in documents:
        document = _read(document)
        if not isinstance(document, Mapping):
            raise ValueError("Every FFA step assessment must be an object or JSON path")
        step = document.get("step")
        assessment = document.get("ffa_assessment", document.get("assessment"))
        if not isinstance(step, Mapping):
            step_id = document.get("step_id")
            step = {"step_id": step_id, "step_description": document.get("step_description", "")}
        if type(step.get("step_id")) is not int or step["step_id"] < 1:
            raise ValueError("Every FFA assessment requires a positive integer step_id")
        if not isinstance(assessment, Mapping):
            raise ValueError(f"Step {step['step_id']} has no FFA assessment object")
        result.append({"step": dict(step), "ffa_assessment": dict(assessment)})
    result.sort(key=lambda item: item["step"]["step_id"])
    ids = [item["step"]["step_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ValueError("FFA scoring input contains duplicate step IDs")
    return result


def _score_step(document: Mapping[str, Any], mapping: Mapping[str, Any], strict: bool) -> dict[str, Any]:
    assessment = document["ffa_assessment"]
    details = {name: {} for name in SUBPROCESSES}
    missing = []
    for field in FIELD_ENUMS:
        entry = mapping["criteria"][field]
        subprocess = entry["subprocess"]
        section = assessment.get(subprocess)
        value = section.get(field) if isinstance(section, Mapping) else None
        if type(value) is int:
            score = entry["scores_by_id"].get(value)
            classification = entry["labels_by_id"].get(value)
            option_id = value
        else:
            score = entry["scores"].get(value)
            classification = value
            option_id = next((key for key, label in entry["labels_by_id"].items()
                              if label == value), None)
        if score is None:
            missing.append(f"{subprocess}.{field}={value!r}")
            continue
        weight = float(entry["criterion_weight"])
        details[subprocess][field] = {"classification": classification,
                                     "option_id": option_id, "score": score,
                                     "criterion_weight": weight,
                                     "weighted_contribution": round(score * weight, 6)}
    if strict and missing:
        raise ValueError(f"Step {document['step']['step_id']} has unscorable classifications: {missing}")
    subprocess_scores = {}
    for subprocess, criteria in details.items():
        covered_weight = sum(item["criterion_weight"] for item in criteria.values())
        weighted_sum = sum(item["score"] * item["criterion_weight"]
                           for item in criteria.values())
        subprocess_scores[subprocess] = (round(weighted_sum / covered_weight, 4)
                                         if covered_weight else None)
    available = [value for value in subprocess_scores.values() if value is not None]
    weighted = sum(subprocess_scores[name] * mapping["subprocess_weights"][name]
                   for name in SUBPROCESSES if subprocess_scores[name] is not None)
    covered = sum(mapping["subprocess_weights"][name]
                  for name in SUBPROCESSES if subprocess_scores[name] is not None)
    return {"step_id": document["step"]["step_id"],
            "step_description": document["step"].get("step_description", ""),
            "subprocess_scores": subprocess_scores,
            "total_ffa": round(weighted / covered, 4) if available and covered else None,
            "coverage": {"scored_criteria": sum(len(value) for value in details.values()),
                         "expected_criteria": len(FIELD_ENUMS), "missing": missing},
            "details": details}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def run_ffa_scoring(*, assessments: Any, settings: Mapping[str, Any] | None = None,
                    output_path: str | Path | None = None) -> dict[str, Any]:
    """Score step artifacts without LLM, NumPy, plotting or research imports."""
    settings = dict(settings or {})
    unknown = set(settings) - {"enabled", "mapping", "strict"}
    if unknown:
        raise ValueError(f"Unknown ffa_scoring settings: {sorted(unknown)}")
    if settings.get("enabled", True) is not True:
        return {"status": "disabled", "artifact": None}
    strict = settings.get("strict", True)
    if type(strict) is not bool:
        raise ValueError("ffa_scoring.strict must be boolean")
    mapping, provenance = load_mapping(str(settings.get("mapping", "ffa_scoring_v1")))
    documents = _normalise_assessments(assessments)
    steps = [_score_step(document, mapping, strict) for document in documents]

    def values(key):
        return [step["subprocess_scores"][key] for step in steps
                if step["subprocess_scores"][key] is not None]

    totals = [step["total_ffa"] for step in steps if step["total_ffa"] is not None]
    aggregate = {f"mean_{name}_score": round(mean(values(name)), 4) if values(name) else None
                 for name in SUBPROCESSES}
    aggregate.update({"mean_total_ffa": round(mean(totals), 4) if totals else None,
                      "std_total_ffa": round(pstdev(totals), 4) if totals else None,
                      "num_steps": len(steps), "num_steps_scored": len(totals)})
    result = {"mapping": provenance, "strict": strict, "steps": steps, "aggregate": aggregate}
    artifact = Path(output_path).resolve() if output_path is not None else None
    if artifact is not None:
        _write_json(artifact, result)
    return {"status": "complete", "artifact": str(artifact) if artifact else None,
            "result": result}
