"""Report validation and safe image lookup shared by all renderers."""

import json
from pathlib import Path
from typing import Any, Mapping


def load_report(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    report = (json.loads(Path(value).read_text(encoding="utf-8"))
              if isinstance(value, (str, Path)) else dict(value))
    required_objects = ("assembly_overview", "scorecard", "provenance")
    required_lists = ("executive_summary", "key_findings", "recommendations", "steps",
                      "parts", "assumptions_and_unknowns")
    if any(not isinstance(report.get(key), Mapping) for key in required_objects):
        raise ValueError("Report requires assembly_overview, scorecard and provenance objects")
    if any(not isinstance(report.get(key), list) for key in required_lists):
        raise ValueError(f"Report requires list fields: {required_lists}")
    finding_ids = _unique_ids(report["key_findings"], "finding_id", "finding")
    recommendation_ids = _unique_ids(report["recommendations"], "recommendation_id", "recommendation")
    _unique_ids(report["steps"], "step_id", "step")
    _unique_ids(report["parts"], "part_id", "part")
    for recommendation in report["recommendations"]:
        if not isinstance(recommendation, Mapping) or not isinstance(recommendation.get("addresses_findings"), list):
            raise ValueError("Every recommendation requires addresses_findings")
        unknown = set(recommendation["addresses_findings"]) - finding_ids
        if unknown:
            raise ValueError(f"Recommendation references unknown findings: {sorted(unknown)}")
    for part in report["parts"]:
        if set(part.get("finding_ids", [])) - finding_ids:
            raise ValueError(f"Part {part.get('part_id')} references unknown findings")
        if set(part.get("recommendation_ids", [])) - recommendation_ids:
            raise ValueError(f"Part {part.get('part_id')} references unknown recommendations")
    for step in report["steps"]:
        _score(step.get("total_ffa"), f"step {step.get('step_id')} total_ffa")
        subprocesses = step.get("subprocesses")
        if not isinstance(subprocesses, Mapping):
            raise ValueError(f"Step {step.get('step_id')} requires subprocesses")
        for name in ("separation", "handling", "positioning", "joining"):
            if not isinstance(subprocesses.get(name), Mapping):
                raise ValueError(f"Step {step.get('step_id')} requires subprocess {name}")
            _score(subprocesses[name].get("score"), f"step {step.get('step_id')} {name}")
    return report


def _unique_ids(items: list[Any], key: str, label: str) -> set[Any]:
    values = []
    for item in items:
        value = item.get(key) if isinstance(item, Mapping) else None
        if not isinstance(value, (str, int)) or isinstance(value, bool) or value == "":
            raise ValueError(f"Every report {label} requires {key}")
        values.append(value)
    if len(values) != len(set(values)):
        raise ValueError(f"Report {label} IDs must be unique")
    return set(values)


def _score(value: Any, label: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                              or not 0 <= value <= 1):
        raise ValueError(f"{label} must be null or a number from 0 to 1")


class ImageResolver:
    def __init__(self, roots: Mapping[str, str | Path] | None = None):
        roots = dict(roots or {})
        unknown = set(roots) - {"preprocessing_images", "sequence_renderings"}
        if unknown:
            raise ValueError(f"Unknown report image roots: {sorted(unknown)}")
        self.roots = {key: Path(value).resolve() for key, value in roots.items()}
        self.used: set[str] = set()
        self.missing: set[str] = set()

    def assembly(self) -> Path | None:
        return self._find("preprocessing_images", ["assembly/collage_assembly.png",
                                                    "images/assembly/collage_assembly.png"])

    def part(self, part_id: str) -> Path | None:
        return self._find("preprocessing_images", [f"parts/{part_id}/collage_{part_id}.png",
                                                    f"images/parts/{part_id}/collage_{part_id}.png"])

    def step(self, step_id: int, references: list[str] | None = None) -> Path | None:
        candidates = [Path(item).name for item in (references or [])]
        candidates.append(f"collage_step_{step_id:02d}.png")
        return self._find("sequence_renderings", candidates)

    def _find(self, root_id: str, relatives: list[str]) -> Path | None:
        root = self.roots.get(root_id)
        logical = f"{root_id}:" + "|".join(relatives)
        if root is None:
            self.missing.add(logical)
            return None
        for relative in relatives:
            candidate = (root / relative).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                self.used.add(candidate.as_posix())
                return candidate
        self.missing.add(logical)
        return None
