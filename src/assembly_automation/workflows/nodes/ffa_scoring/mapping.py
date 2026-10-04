"""Load and validate the versioned product FFA scoring mapping."""

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import yaml

from assembly_automation.workflows.nodes.ffa_assessment.structured_output import (
    Accessibility,
    AccuracyOfTargetPosition,
    AdditionalOrientation,
    FeedingOfJoiningElement,
    FixingOfMountedPart,
    GrippingAreas,
    NatureOfProvision,
    OrientationFeatures,
    PartRigidity,
    PositioningAids,
    PositioningMotion,
    PositioningTolerances,
    Stability,
    SurfaceSensibility,
)

MAPPING_PATH = Path(__file__).with_name("scoring_mapping.yaml")
SUBPROCESSES = ("separation", "handling", "positioning", "joining")
FIELD_ENUMS = {
    "nature_of_provision": NatureOfProvision,
    "part_rigidity": PartRigidity,
    "gripping_areas": GrippingAreas,
    "orientation_features": OrientationFeatures,
    "surface_sensibility": SurfaceSensibility,
    "accuracy_of_target_position": AccuracyOfTargetPosition,
    "positioning_aids": PositioningAids,
    "additional_orientation_by_rotation": AdditionalOrientation,
    "accessibility_to_joining_position": Accessibility,
    "positioning_motion": PositioningMotion,
    "positioning_tolerances": PositioningTolerances,
    "stability_in_positioned_state": Stability,
    "feeding_of_joining_element": FeedingOfJoiningElement,
    "fixing_of_mounted_part": FixingOfMountedPart,
}


def load_mapping(mapping_id: str = "ffa_scoring_v1") -> tuple[dict[str, Any], dict[str, str]]:
    if mapping_id != "ffa_scoring_v1":
        raise ValueError(f"Unknown FFA scoring mapping: {mapping_id}")
    raw = MAPPING_PATH.read_bytes()
    mapping = yaml.safe_load(raw)
    validate_mapping(mapping)
    for entry in mapping["criteria"].values():
        options = entry["options"]
        entry["scores"] = {option["label"]: float(option["score"])
                           for option in options.values()}
        entry["scores_by_id"] = {int(option_id): float(option["score"])
                                 for option_id, option in options.items()}
        entry["labels_by_id"] = {int(option_id): option["label"]
                                 for option_id, option in options.items()}
    return mapping, {"id": mapping["version"], "sha256": sha256(raw).hexdigest(),
                     "path": MAPPING_PATH.name, "status": mapping["status"]}


def validate_mapping(mapping: Mapping[str, Any]) -> None:
    if not isinstance(mapping, Mapping) or mapping.get("version") != "ffa_scoring_v1":
        raise ValueError("FFA scoring mapping requires version ffa_scoring_v1")
    if not isinstance(mapping.get("status"), str):
        raise ValueError("FFA scoring mapping requires a status")
    subprocess_weights = mapping.get("subprocess_weights")
    if not isinstance(subprocess_weights, Mapping) or set(subprocess_weights) != set(SUBPROCESSES):
        raise ValueError("FFA scoring mapping requires four subprocess weights")
    _weights(subprocess_weights, "subprocess")
    criteria = mapping.get("criteria")
    if not isinstance(criteria, Mapping) or set(criteria) != set(FIELD_ENUMS):
        raise ValueError("FFA scoring criteria must match the 14 classification fields")
    grouped = {name: {} for name in SUBPROCESSES}
    for field, enum in FIELD_ENUMS.items():
        entry = criteria[field]
        if not isinstance(entry, Mapping) or entry.get("subprocess") not in SUBPROCESSES:
            raise ValueError(f"Invalid subprocess for scoring field {field}")
        weight = entry.get("criterion_weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError(f"Invalid criterion weight for {field}")
        expected = {item.value for item in enum}
        options = entry.get("options")
        if not isinstance(options, Mapping) or not options:
            raise ValueError(f"Scoring options missing for {field}")
        expected_ids = set(range(1, len(options) + 1))
        if set(options) != expected_ids:
            raise ValueError(f"Option IDs for {field} must be consecutive integers from 1")
        labels = {option.get("label") for option in options.values()
                  if isinstance(option, Mapping)}
        if len(labels) != len(options) or labels != expected:
            raise ValueError(f"Scoring options differ from structured enum for {field}")
        for option_id, option in options.items():
            if set(option) != {"label", "score"}:
                raise ValueError(f"Invalid option structure for {field}: {option_id}")
            score = option["score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
                raise ValueError(f"Invalid score for {field}: {option_id}")
        grouped[entry["subprocess"]][field] = weight
    for subprocess, weights in grouped.items():
        _weights(weights, subprocess)


def _weights(values: Mapping[str, Any], label: str) -> None:
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
           for value in values.values()):
        raise ValueError(f"{label} weights must be positive numbers")
    if abs(sum(float(value) for value in values.values()) - 1.0) > 1e-9:
        raise ValueError(f"{label} weights must sum to 1.0")
