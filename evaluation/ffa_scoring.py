"""
FFA Scoring Module

Converts FFA assessment data (enum IDs or string labels) into numeric FFA scores.

Score structure:
  - Per step: separation_score, handling_score, positioning_score, joining_score, total_ffa
  - Per assembly: mean scores across all steps, per subprocess and total

Formula:
  subprocess_score = sum(criterion_weight_i * ffa_value_i)   [range 0.0–1.0]
  total_ffa        = mean(separation, handling, positioning, joining)  [range 0.0–1.0]

Input formats accepted:
  - Integer enum IDs  (from *_ffa_assessment_enum.json annotation files)
  - Full string labels (from *_ffa_assessment.json LLM output files)

Mapping source:
  data/ground_truth/mapping/ffa_scoring_mapping.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================================
# MAPPING FILE
# ============================================================================

_MAPPING_FILE = Path(__file__).resolve().parent.parent / "data" / "ground_truth" / "mapping" / "ffa_scoring_mapping.json"
_MAPPING: Optional[Dict] = None


def load_scoring_mapping(path: Path = _MAPPING_FILE) -> Dict:
    """Load (and cache) the FFA scoring mapping JSON."""
    global _MAPPING
    if _MAPPING is None:
        if not path.exists():
            raise FileNotFoundError(f"FFA scoring mapping not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            _MAPPING = json.load(f)
    return _MAPPING


# ============================================================================
# FIELD → SUBPROCESS MAPPING
# ============================================================================

# Maps each FFA field name to its subprocess and the criterion key in the mapping JSON.
FIELD_TO_SUBPROCESS: Dict[str, Tuple[str, str]] = {
    # subprocess: separation
    "nature_of_provision":                  ("separation",  "nature_of_provision"),
    # subprocess: handling
    "part_rigidity":                        ("handling",    "part_rigidity"),
    "gripping_areas":                       ("handling",    "gripping_areas"),
    "orientation_features":                 ("handling",    "orientation_features"),
    "surface_sensibility":                  ("handling",    "surface_sensibility"),
    # subprocess: positioning
    "accuracy_of_target_position":          ("positioning", "accuracy_of_target_position"),
    "positioning_aids":                     ("positioning", "positioning_aids"),
    "additional_orientation_by_rotation":   ("positioning", "additional_orientation_by_rotation"),
    "accessibility_to_joining_position":    ("positioning", "accessibility_to_joining_position"),
    "positioning_motion":                   ("positioning", "positioning_motion"),
    "positioning_tolerances":               ("positioning", "positioning_tolerances"),
    "stability_in_positioned_state":        ("positioning", "stability_in_positioned_state"),
    # subprocess: joining
    "feeding_of_joining_element":           ("joining",     "feeding_of_joining_element"),
    "fixing_of_mounted_part":               ("joining",     "fixing_of_mounted_part"),
}

SUBPROCESSES = ["separation", "handling", "positioning", "joining"]

# FFA field evaluation order (1-14 as per spec)
FFA_FIELD_ORDER = [
    "nature_of_provision",
    "part_rigidity",
    "gripping_areas",
    "orientation_features",
    "surface_sensibility",
    "accuracy_of_target_position",
    "positioning_aids",
    "additional_orientation_by_rotation",
    "accessibility_to_joining_position",
    "positioning_motion",
    "positioning_tolerances",
    "stability_in_positioned_state",
    "feeding_of_joining_element",
    "fixing_of_mounted_part",
]


# ============================================================================
# LOOKUP HELPERS
# ============================================================================

def resolve_ffa_value(field_name: str, value: Union[int, str, None]) -> Optional[float]:
    """
    Returns the ffa_value (0.0–1.0) for a given field name and option value.

    Args:
        field_name: e.g. "part_rigidity"
        value:      integer enum ID (1, 2, 3...) OR full string label OR None

    Returns:
        ffa_value float, or None if lookup fails.
    """
    if value is None:
        return None

    mapping = load_scoring_mapping()

    if field_name not in FIELD_TO_SUBPROCESS:
        logger.debug(f"Unknown field: {field_name}")
        return None

    subprocess_key, criterion_key = FIELD_TO_SUBPROCESS[field_name]
    options = mapping[subprocess_key][criterion_key]["options"]

    # Integer ID: look up directly by string key (JSON keys are strings)
    if isinstance(value, int):
        key = str(value)
        if key in options:
            return float(options[key]["ffa_value"])
        logger.warning(f"  {field_name}: enum ID {value} not found in mapping")
        return None

    # String label: scan options for matching label
    if isinstance(value, str):
        # Try exact match first
        for opt_key, opt_data in options.items():
            if opt_data["label"] == value:
                return float(opt_data["ffa_value"])
        # Fallback: case-insensitive match
        value_lower = value.strip().lower()
        for opt_key, opt_data in options.items():
            if opt_data["label"].lower() == value_lower:
                return float(opt_data["ffa_value"])
        logger.warning(f"  {field_name}: string '{value}' not found in mapping")
        return None

    logger.warning(f"  {field_name}: unsupported value type {type(value)}")
    return None


def resolve_option_id(field_name: str, value: Union[int, str, None]) -> Optional[int]:
    """
    Returns the integer enum ID for a given field name and option value.

    Args:
        field_name: e.g. "part_rigidity"
        value:      integer enum ID OR full string label OR None

    Returns:
        integer option ID, or None if lookup fails.
    """
    if value is None:
        return None

    # Already an integer
    if isinstance(value, int):
        return value

    # Digit string  (e.g. "2")
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    mapping = load_scoring_mapping()

    if field_name not in FIELD_TO_SUBPROCESS:
        return None

    subprocess_key, criterion_key = FIELD_TO_SUBPROCESS[field_name]
    options = mapping[subprocess_key][criterion_key]["options"]

    # String label: scan options
    value_lower = value.strip().lower()
    for opt_key, opt_data in options.items():
        if opt_data["label"] == value or opt_data["label"].lower() == value_lower:
            return int(opt_key)

    logger.warning(f"  {field_name}: string '{value}' not found in mapping (resolve_option_id)")
    return None


def get_criterion_weight(field_name: str) -> float:
    """Returns the criterion weight (0.0–1.0) for a field within its subprocess."""
    mapping = load_scoring_mapping()
    subprocess_key, criterion_key = FIELD_TO_SUBPROCESS[field_name]
    return float(mapping[subprocess_key][criterion_key]["criterion_weight"])


# ============================================================================
# STEP-LEVEL SCORING
# ============================================================================

def compute_step_ffa_score(step_data: Dict[str, Union[int, str, None]]) -> Dict:
    """
    Compute FFA scores for a single assembly step.

    Args:
        step_data: Dict mapping field_name → enum_id (int) or string label.
                   Fields may be missing or None – treated as no data for that criterion.

    Returns:
        {
          "separation_score":  float | None,
          "handling_score":    float | None,
          "positioning_score": float | None,
          "joining_score":     float | None,
          "total_ffa":         float | None,
          "details": {
            "separation":  { field_name: {"value": ..., "ffa_value": ..., "weight": ...}, ... },
            "handling":    { ... },
            "positioning": { ... },
            "joining":     { ... }
          },
          "warnings": [...]
        }
    """
    mapping = load_scoring_mapping()
    warnings = []

    # Collect per-criterion values grouped by subprocess
    subprocess_contributions: Dict[str, Dict[str, Dict]] = {sp: {} for sp in SUBPROCESSES}

    for field_name, value in step_data.items():
        if field_name not in FIELD_TO_SUBPROCESS:
            continue  # skip non-FFA fields (e.g. reasoning text)

        subprocess_key, criterion_key = FIELD_TO_SUBPROCESS[field_name]
        ffa_value = resolve_ffa_value(field_name, value)
        weight = get_criterion_weight(field_name)

        subprocess_contributions[subprocess_key][field_name] = {
            "raw_value": value,
            "ffa_value": ffa_value,
            "criterion_weight": weight,
            "weighted_contribution": ffa_value * weight if ffa_value is not None else None,
        }

        if ffa_value is None:
            warnings.append(f"No ffa_value resolved for field '{field_name}' with value '{value}'")

    # Compute subprocess scores
    subprocess_scores: Dict[str, Optional[float]] = {}
    for sp in SUBPROCESSES:
        contribs = subprocess_contributions[sp]
        if not contribs:
            subprocess_scores[sp] = None
            continue

        weighted_sum = 0.0
        total_weight = 0.0
        has_any_value = False

        for field_name, data in contribs.items():
            if data["ffa_value"] is not None:
                weighted_sum += data["weighted_contribution"]
                total_weight += data["criterion_weight"]
                has_any_value = True

        if not has_any_value or total_weight == 0:
            subprocess_scores[sp] = None
            warnings.append(f"No values available for subprocess '{sp}'")
        else:
            # Normalize by actual covered weight (handles partial data gracefully)
            subprocess_scores[sp] = round(weighted_sum / total_weight, 4)

    # Compute total FFA (mean of available subprocess scores)
    available_scores = [s for s in subprocess_scores.values() if s is not None]
    total_ffa = round(float(np.mean(available_scores)), 4) if available_scores else None

    if len(available_scores) < len(SUBPROCESSES):
        missing = [sp for sp, s in subprocess_scores.items() if s is None]
        warnings.append(f"Total FFA computed from {len(available_scores)}/4 subprocesses (missing: {missing})")

    return {
        "separation_score":  subprocess_scores["separation"],
        "handling_score":    subprocess_scores["handling"],
        "positioning_score": subprocess_scores["positioning"],
        "joining_score":     subprocess_scores["joining"],
        "total_ffa":         total_ffa,
        "details":           subprocess_contributions,
        "warnings":          warnings,
    }


# ============================================================================
# ASSEMBLY-LEVEL SCORING
# ============================================================================

def compute_assembly_ffa_scores(assessment_data: Dict[str, Dict]) -> Dict:
    """
    Compute FFA scores for all steps in an assembly assessment.

    Args:
        assessment_data: {step_name: {field_name: value, ...}, ...}
                         Values can be integers (enum IDs) or strings.

    Returns:
        {
          "per_step": {
            step_name: {separation_score, handling_score, positioning_score,
                        joining_score, total_ffa, details, warnings}
          },
          "aggregate": {
            "mean_separation_score":  float,
            "mean_handling_score":    float,
            "mean_positioning_score": float,
            "mean_joining_score":     float,
            "mean_total_ffa":         float,
            "std_total_ffa":          float,
            "num_steps":              int,
            "num_steps_scored":       int,
          }
        }
    """
    per_step: Dict[str, Dict] = {}

    for step_name, step_data in assessment_data.items():
        if not isinstance(step_data, dict):
            continue
        per_step[step_name] = compute_step_ffa_score(step_data)

    # Aggregate
    def _collect(key: str) -> List[float]:
        return [v[key] for v in per_step.values() if v.get(key) is not None]

    sep   = _collect("separation_score")
    hand  = _collect("handling_score")
    pos   = _collect("positioning_score")
    joi   = _collect("joining_score")
    total = _collect("total_ffa")

    def _mean(lst): return round(float(np.mean(lst)), 4) if lst else None
    def _std(lst):  return round(float(np.std(lst)),  4) if lst else None

    return {
        "per_step": per_step,
        "aggregate": {
            "mean_separation_score":  _mean(sep),
            "mean_handling_score":    _mean(hand),
            "mean_positioning_score": _mean(pos),
            "mean_joining_score":     _mean(joi),
            "mean_total_ffa":         _mean(total),
            "std_total_ffa":          _std(total),
            "num_steps":              len(per_step),
            "num_steps_scored":       len(total),
        },
    }


# ============================================================================
# FILE-LEVEL HELPERS
# ============================================================================

def load_and_score_assessment_file(file_path: Path) -> Dict:
    """
    Load a *_ffa_assessment_enum.json or *_ffa_assessment.json file and compute FFA scores.

    Handles two common file structures:
      A) Flat: { step_name: { field_name: value } }
      B) Nested: { step_name: { "separation": {...}, "handling": {...}, ... } }

    Returns compute_assembly_ffa_scores() output plus the raw data.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Normalise to flat { step_name: { field_name: value } }
    flat: Dict[str, Dict] = {}
    for step_name, step_data in raw.items():
        if not isinstance(step_data, dict):
            continue

        # Detect nested structure (keys are subprocess names)
        subproc_keys = {"separation", "handling", "positioning", "joining"}
        if subproc_keys & set(step_data.keys()):
            merged: Dict = {}
            for sub_key in subproc_keys:
                if sub_key in step_data and isinstance(step_data[sub_key], dict):
                    merged.update(step_data[sub_key])
            flat[step_name] = merged
        else:
            flat[step_name] = step_data

    result = compute_assembly_ffa_scores(flat)
    result["source_file"] = str(file_path)
    result["raw_data"] = raw
    return result


# ============================================================================
# COMPARISON: PREDICTION vs GROUND TRUTH
# ============================================================================

def compare_ffa_scores(
    prediction_file: Path,
    ground_truth_file: Path,
) -> Dict:
    """
    Compare FFA scores between prediction and ground truth files.

    Returns:
        {
          "prediction":    compute_assembly_ffa_scores() output,
          "ground_truth":  compute_assembly_ffa_scores() output,
          "delta": {
            "mean_separation_delta":  float,   # pred - gt
            "mean_handling_delta":    float,
            "mean_positioning_delta": float,
            "mean_joining_delta":     float,
            "mean_total_ffa_delta":   float,
            "mae_total_ffa":          float,   # mean absolute error across steps
            "per_step_delta":         { step_name: {"total_ffa_delta": float, ...} }
          }
        }
    """
    pred_result = load_and_score_assessment_file(prediction_file)
    gt_result   = load_and_score_assessment_file(ground_truth_file)

    pred_agg = pred_result["aggregate"]
    gt_agg   = gt_result["aggregate"]

    def _delta(key: str) -> Optional[float]:
        p = pred_agg.get(key)
        g = gt_agg.get(key)
        if p is None or g is None:
            return None
        return round(p - g, 4)

    # Per-step delta
    per_step_delta: Dict[str, Dict] = {}
    all_abs_errors: List[float] = []

    common_steps = set(pred_result["per_step"].keys()) & set(gt_result["per_step"].keys())
    for step_name in sorted(common_steps):
        p_step = pred_result["per_step"][step_name]
        g_step = gt_result["per_step"][step_name]
        step_delta: Dict[str, Optional[float]] = {}

        for key in ("separation_score", "handling_score", "positioning_score",
                    "joining_score", "total_ffa"):
            p_val = p_step.get(key)
            g_val = g_step.get(key)
            if p_val is not None and g_val is not None:
                d = round(p_val - g_val, 4)
                step_delta[f"{key}_delta"] = d
                if key == "total_ffa":
                    all_abs_errors.append(abs(d))
            else:
                step_delta[f"{key}_delta"] = None

        per_step_delta[step_name] = step_delta

    mae = round(float(np.mean(all_abs_errors)), 4) if all_abs_errors else None

    return {
        "prediction":   pred_result,
        "ground_truth": gt_result,
        "delta": {
            "mean_separation_delta":  _delta("mean_separation_score"),
            "mean_handling_delta":    _delta("mean_handling_score"),
            "mean_positioning_delta": _delta("mean_positioning_score"),
            "mean_joining_delta":     _delta("mean_joining_score"),
            "mean_total_ffa_delta":   _delta("mean_total_ffa"),
            "mae_total_ffa":          mae,
            "common_steps":           len(common_steps),
            "per_step_delta":         per_step_delta,
        },
    }


# ============================================================================
# CLI  (python -m evaluation.ffa_scoring <pred_file> <gt_file>)
# ============================================================================

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute and compare FFA scores from assessment files."
    )
    parser.add_argument("prediction",   type=Path, help="Prediction file (*_ffa_assessment_enum.json or *_ffa_assessment.json)")
    parser.add_argument("ground_truth", type=Path, nargs="?", help="Ground truth file (optional – if omitted, only scores the prediction)")
    parser.add_argument("--output",     type=Path, default=None, help="Write JSON result to this file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.ground_truth:
        result = compare_ffa_scores(args.prediction, args.ground_truth)
        print(f"\n{'='*60}")
        print(f"FFA SCORE COMPARISON")
        print(f"{'='*60}")
        pred_agg = result["prediction"]["aggregate"]
        gt_agg   = result["ground_truth"]["aggregate"]
        delta    = result["delta"]

        print(f"\n{'Subprocess':<28} {'Prediction':>12} {'Ground Truth':>14} {'Delta':>8}")
        print("─" * 66)
        for label, pred_key, gt_key, delta_key in [
            ("Separation",  "mean_separation_score",  "mean_separation_score",  "mean_separation_delta"),
            ("Handling",    "mean_handling_score",     "mean_handling_score",    "mean_handling_delta"),
            ("Positioning", "mean_positioning_score",  "mean_positioning_score", "mean_positioning_delta"),
            ("Joining",     "mean_joining_score",      "mean_joining_score",     "mean_joining_delta"),
            ("─" * 28, "", "", ""),
            ("Total FFA",   "mean_total_ffa",          "mean_total_ffa",         "mean_total_ffa_delta"),
        ]:
            if label.startswith("─"):
                print("─" * 66)
                continue
            p = pred_agg.get(pred_key)
            g = gt_agg.get(gt_key)
            d = delta.get(delta_key)
            p_str = f"{p:.4f}" if p is not None else "  N/A"
            g_str = f"{g:.4f}" if g is not None else "       N/A"
            d_str = f"{d:+.4f}" if d is not None else "    N/A"
            print(f"  {label:<26} {p_str:>12} {g_str:>14} {d_str:>8}")

        mae = delta.get("mae_total_ffa")
        if mae is not None:
            print(f"\n  MAE total FFA across steps: {mae:.4f}")
        print(f"  Common steps evaluated: {delta.get('common_steps', 0)}")

    else:
        result = load_and_score_assessment_file(args.prediction)
        agg = result["aggregate"]
        print(f"\n{'='*50}")
        print(f"FFA SCORES: {args.prediction.name}")
        print(f"{'='*50}")
        print(f"  Separation:  {agg.get('mean_separation_score', 'N/A')}")
        print(f"  Handling:    {agg.get('mean_handling_score',    'N/A')}")
        print(f"  Positioning: {agg.get('mean_positioning_score', 'N/A')}")
        print(f"  Joining:     {agg.get('mean_joining_score',     'N/A')}")
        print(f"  ─────────────────────────")
        print(f"  Total FFA:   {agg.get('mean_total_ffa', 'N/A')}")
        print(f"  Steps scored: {agg.get('num_steps_scored', 0)}/{agg.get('num_steps', 0)}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Saved to: {args.output}")
