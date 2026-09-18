"""
FFA Evaluator – Core Metrics Engine

Implements the full evaluation specification:
  - Step level (per criterion)
  - Category level (per subprocess)
  - Assembly level (total FFA)
  - Experiment level (cross-assembly summary)
  + Statistical testing (Wilcoxon, paired t-test)

Input:  *_ffa_assessment_enum.json  (predictions, same nested structure as GT)
        *_ffa_assessment_enum_gt.json (ground truth)

Output: CriterionRecord list  →  all derived metrics and CSV files
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from evaluation.ffa_scoring import (
    FIELD_TO_SUBPROCESS,
    get_criterion_weight,
    load_scoring_mapping,
    resolve_ffa_value,
    resolve_option_id,
)

logger = logging.getLogger(__name__)

CATEGORY_WEIGHT = 0.25          # all four subprocesses equally weighted
SUBPROCESSES = ["separation", "handling", "positioning", "joining"]


def display_assembly_name(assembly_id: str) -> str:
    """Return a short report label while keeping raw assembly IDs unchanged."""
    replacements = {
        "Husquarna 365 crankshaft assembly": "crankshaft assembly",
        "Husqvarna 365 crankshaft assembly": "crankshaft assembly",
    }
    return replacements.get(assembly_id, assembly_id)

# ============================================================================
# FIELD-LEVEL RECORD
# ============================================================================

@dataclass
class CriterionRecord:
    """One row = one FFA criterion for one step of one assembly."""
    assembly_id:       str
    step_id:           str
    step_description:  str
    category:          str    # separation | handling | positioning | joining
    field_name:        str
    criterion_weight:  float  # weight within its subprocess (sums to 1.0 per subprocess)
    category_weight:   float  # subprocess weight in total FFA (always 0.25)
    gt_option_id:      int    # integer annotation ID (ground truth)
    pred_option_id:    int    # integer annotation ID (prediction)
    gt_ffa_value:      float
    pred_ffa_value:    float
    abs_error:         float  # |gt_ffa_value - pred_ffa_value|
    run_id:            str = ""   # identifies the repetition (e.g. "run1", "run3")


# ============================================================================
# DATA LOADING / PARSING
# ============================================================================

def _parse_assessment_file(path: Path) -> Dict[str, Dict]:
    """
    Parse any *_ffa_assessment_enum.json or *_ffa_assessment_enum_gt.json.

    Returns:
        { step_key: {"step_id": int, "step_description": str,
                     "assessment": {category: {field: int_id}}} }
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    steps: Dict[str, Dict] = {}

    # ----- Format A1: bare list [{step_id, assessment, ...}, ...] (GT enum files) -----
    if isinstance(raw, list):
        for s in raw:
            key = f"step_{s['step_id']}"
            steps[key] = {
                "step_id":          s["step_id"],
                "step_description": s.get("step_description", key),
                "assessment":       s.get("assessment") or {},
            }
        return steps

    # ----- Format A2: list under "step_assessments" key -----
    if isinstance(raw, dict) and "step_assessments" in raw:
        for s in raw["step_assessments"]:
            key = f"step_{s['step_id']}"
            steps[key] = {
                "step_id":          s["step_id"],
                "step_description": s.get("step_description", key),
                "assessment":       s.get("assessment") or {},
            }
        return steps

    # ----- Format B: flat dict {step_key: {field: value}} -----
    for step_key, step_data in raw.items():
        if not isinstance(step_data, dict):
            continue
        # Already nested by subprocess?
        if set(SUBPROCESSES) & set(step_data.keys()):
            assessment = {sp: step_data[sp] for sp in SUBPROCESSES if sp in step_data}
        else:
            # Flat: group by subprocess
            assessment = {sp: {} for sp in SUBPROCESSES}
            for field, val in step_data.items():
                if field in FIELD_TO_SUBPROCESS:
                    sp, _ = FIELD_TO_SUBPROCESS[field]
                    assessment[sp][field] = val
        steps[step_key] = {
            "step_id":          step_key,
            "step_description": step_key,
            "assessment":       assessment,
        }

    return steps


def load_criterion_records(
    pred_file: Path,
    gt_file: Path,
    assembly_id: str,
    run_id: str = "",
) -> List[CriterionRecord]:
    """
    Align prediction and GT files step-by-step, field-by-field.

    Returns a flat list of CriterionRecord, one per matched (step, field).
    """
    pred_steps = _parse_assessment_file(pred_file)
    gt_steps   = _parse_assessment_file(gt_file)

    # Match steps by step_id number
    def _step_num(key: str, data: dict) -> int:
        sid = data.get("step_id", key)
        try:
            return int(str(sid).replace("step_", ""))
        except ValueError:
            return hash(key)

    pred_by_num = {_step_num(k, v): v for k, v in pred_steps.items()}
    gt_by_num   = {_step_num(k, v): v for k, v in gt_steps.items()}

    common_steps = sorted(set(pred_by_num.keys()) & set(gt_by_num.keys()))
    if not common_steps:
        logger.warning(f"  {assembly_id}: no common steps between pred and GT")
        return []

    records: List[CriterionRecord] = []

    for step_num in common_steps:
        pred_step = pred_by_num[step_num]
        gt_step   = gt_by_num[step_num]
        step_id   = str(step_num)
        step_desc = gt_step.get("step_description", step_id)

        for sp in SUBPROCESSES:
            pred_sp = (pred_step.get("assessment") or {}).get(sp, {})
            gt_sp   = (gt_step.get("assessment")  or {}).get(sp, {})

            for field_name in gt_sp:
                if field_name not in FIELD_TO_SUBPROCESS:
                    continue
                if field_name not in pred_sp:
                    continue  # prediction missing this field

                gt_id   = gt_sp[field_name]
                pred_id = pred_sp[field_name]

                gt_ffa   = resolve_ffa_value(field_name, gt_id)
                pred_ffa = resolve_ffa_value(field_name, pred_id)

                if gt_ffa is None or pred_ffa is None:
                    continue

                gt_opt_id   = resolve_option_id(field_name, gt_id)
                pred_opt_id = resolve_option_id(field_name, pred_id)
                if gt_opt_id is None or pred_opt_id is None:
                    continue

                records.append(CriterionRecord(
                    assembly_id      = assembly_id,
                    step_id          = step_id,
                    step_description = step_desc,
                    category         = sp,
                    field_name       = field_name,
                    criterion_weight = get_criterion_weight(field_name),
                    category_weight  = CATEGORY_WEIGHT,
                    gt_option_id     = gt_opt_id,
                    pred_option_id   = pred_opt_id,
                    gt_ffa_value     = float(gt_ffa),
                    pred_ffa_value   = float(pred_ffa),
                    abs_error        = abs(float(gt_ffa) - float(pred_ffa)),
                    run_id           = run_id,
                ))

    return records


def compute_gt_assembly_ffa_from_file(gt_file: Path) -> Tuple[Optional[float], int, int]:
    """Compute the GT assembly FFA directly from a ground-truth enum file."""
    gt_steps = _parse_assessment_file(gt_file)
    step_gt: List[float] = []
    n_criteria = 0

    for step_data in gt_steps.values():
        assessment = step_data.get("assessment") or {}
        sp_scores = []

        for sp in SUBPROCESSES:
            fields = assessment.get(sp, {})
            if not isinstance(fields, dict):
                continue

            vals = []
            weights = []
            for field_name, gt_id in fields.items():
                if field_name not in FIELD_TO_SUBPROCESS:
                    continue
                gt_ffa = resolve_ffa_value(field_name, gt_id)
                if gt_ffa is None:
                    continue
                vals.append(float(gt_ffa))
                weights.append(float(get_criterion_weight(field_name)))
                n_criteria += 1

            if weights:
                w = np.array(weights, dtype=float)
                v = np.array(vals, dtype=float)
                w_sum = w.sum()
                if w_sum > 0:
                    sp_scores.append(float(np.dot(w, v) / w_sum))

        if sp_scores:
            step_gt.append(float(np.mean(sp_scores)))

    if not step_gt:
        return None, 0, n_criteria

    return round(float(np.mean(step_gt)), 4), len(step_gt), n_criteria


# ============================================================================
# CLASSIFICATION METRICS (per category)
# ============================================================================

def _classification_metrics(y_true: List[int], y_pred: List[int]) -> Dict:
    """Compute all classification metrics for one category."""
    if not y_true:
        return {}

    from sklearn.metrics import (
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
        balanced_accuracy_score,
        confusion_matrix,
    )

    labels = sorted(set(y_true) | set(y_pred))
    kwargs_macro    = dict(average="macro",    labels=labels, zero_division=0)
    kwargs_weighted = dict(average="weighted", labels=labels, zero_division=0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {
            "n_samples":        len(y_true),
            "n_classes":        len(labels),
            "labels":           labels,
            "accuracy":         float(accuracy_score(y_true, y_pred)),
            "macro_f1":         float(f1_score(y_true, y_pred, **kwargs_macro)),
            "weighted_f1":      float(f1_score(y_true, y_pred, **kwargs_weighted)),
            "macro_precision":  float(precision_score(y_true, y_pred, **kwargs_macro)),
            "macro_recall":     float(recall_score(y_true, y_pred, **kwargs_macro)),
            "weighted_precision": float(precision_score(y_true, y_pred, **kwargs_weighted)),
            "weighted_recall":    float(recall_score(y_true, y_pred, **kwargs_weighted)),
            "balanced_accuracy":  float(balanced_accuracy_score(y_true, y_pred)),
            "confusion_matrix":   confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        }


# ============================================================================
# REGRESSION METRICS
# ============================================================================

def _regression_metrics(y_true: List[float], y_pred: List[float]) -> Dict:
    """Compute MAE, RMSE, R², Spearman, Pearson."""
    if len(y_true) < 2:
        return {"n": len(y_true)}

    y_t = np.array(y_true, dtype=float)
    y_p = np.array(y_pred, dtype=float)

    mae  = float(np.mean(np.abs(y_t - y_p)))
    rmse = float(np.sqrt(np.mean((y_t - y_p) ** 2)))

    # R²
    ss_res = np.sum((y_t - y_p) ** 2)
    ss_tot = np.sum((y_t - np.mean(y_t)) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    # Correlations (suppress constant-array warnings)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            spearman_r, spearman_p = stats.spearmanr(y_t, y_p)
        except Exception:
            spearman_r, spearman_p = float("nan"), float("nan")
        try:
            pearson_r,  pearson_p  = stats.pearsonr(y_t, y_p)
        except Exception:
            pearson_r,  pearson_p  = float("nan"), float("nan")

    return {
        "n":           len(y_true),
        "mae":         round(mae,  4),
        "rmse":        round(rmse, 4),
        "r2":          round(r2,   4),
        "spearman_r":  round(float(spearman_r), 4),
        "spearman_p":  round(float(spearman_p), 6),
        "pearson_r":   round(float(pearson_r),  4),
        "pearson_p":   round(float(pearson_p),  6),
    }


# ============================================================================
# ASSEMBLY-LEVEL FFA AGGREGATION
# ============================================================================

def compute_assembly_ffa_from_records(
    records: List[CriterionRecord],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute total FFA (GT and predicted) for one assembly from its criterion records.

    Formula:
        total_ffa = mean over steps of [mean over subprocesses of
                        [weighted_sum(criterion_ffa) / total_weight_in_subprocess]]
    """
    # Group by step
    from collections import defaultdict
    step_records: Dict[str, List[CriterionRecord]] = defaultdict(list)
    for r in records:
        step_records[r.step_id].append(r)

    step_gt   = []
    step_pred = []

    for step_id, step_recs in step_records.items():
        # Per subprocess, compute weighted mean FFA
        sp_gt: Dict[str, List] = {sp: [] for sp in SUBPROCESSES}
        sp_pred: Dict[str, List] = {sp: [] for sp in SUBPROCESSES}
        sp_w: Dict[str, List] = {sp: [] for sp in SUBPROCESSES}

        for r in step_recs:
            sp_gt[r.category].append(r.gt_ffa_value)
            sp_pred[r.category].append(r.pred_ffa_value)
            sp_w[r.category].append(r.criterion_weight)

        sp_scores_gt   = []
        sp_scores_pred = []
        for sp in SUBPROCESSES:
            if not sp_gt[sp]:
                continue
            w = np.array(sp_w[sp])
            g = np.array(sp_gt[sp])
            p = np.array(sp_pred[sp])
            w_sum = w.sum()
            if w_sum > 0:
                sp_scores_gt.append(float(np.dot(w, g) / w_sum))
                sp_scores_pred.append(float(np.dot(w, p) / w_sum))

        if sp_scores_gt:
            step_gt.append(float(np.mean(sp_scores_gt)))
            step_pred.append(float(np.mean(sp_scores_pred)))

    if not step_gt:
        return None, None

    return round(float(np.mean(step_gt)), 4), round(float(np.mean(step_pred)), 4)


# ============================================================================
# EXPERIMENT METRICS
# ============================================================================

def compute_experiment_metrics(
    all_records: List[CriterionRecord],
) -> Dict:
    """
    Full hierarchical metrics from a flat list of CriterionRecord.

    Returns:
        {
          "classification": {
            "<category>": {accuracy, macro_f1, weighted_f1, ...},
            "global": {macro_f1, weighted_f1, balanced_accuracy}
          },
          "regression": {
            "<category>": {mae, rmse, r2, ...},
            "global": {mae, rmse, r2, ...}
          },
          "assembly_ffa": {
            "<assembly_id>": {gt_total_ffa, pred_total_ffa, abs_error}
          },
          "soft_score": float,
          "summary": {macro_f1, weighted_f1, balanced_accuracy, total_ffa_mae, ...}
        }
    """
    from collections import defaultdict

    result: Dict = {
        "n_records":      len(all_records),
        "classification": {},
        "regression":     {},
        "assembly_ffa":   {},
        "soft_score":     None,
        "summary":        {},
    }

    if not all_records:
        return result

    # --- Classification per category (field-weighted: mean of F1 per field in category) ---
    gt_ffa_by_cat:   Dict[str, List[float]] = defaultdict(list)
    pred_ffa_by_cat: Dict[str, List[float]] = defaultdict(list)

    for r in all_records:
        gt_ffa_by_cat[r.category].append(r.gt_ffa_value)
        pred_ffa_by_cat[r.category].append(r.pred_ffa_value)

    # Collect all fields across all categories
    all_fields = sorted(set(r.field_name for r in all_records))
    all_field_f1s = []
    all_field_weighted_f1s = []

    for sp in SUBPROCESSES:
        # Collect all fields in this category
        fields_in_cat = sorted(set(r.field_name for r in all_records if r.category == sp))
        if not fields_in_cat:
            continue
        
        # Compute F1 per field in this category
        field_f1s = []
        field_weighted_f1s = []
        for field_name in fields_in_cat:
            field_recs = [r for r in all_records if r.category == sp and r.field_name == field_name]
            if not field_recs:
                continue
            field_gt_ids = [r.gt_option_id for r in field_recs]
            field_pred_ids = [r.pred_option_id for r in field_recs]
            if field_gt_ids and field_pred_ids:
                field_metrics = _classification_metrics(field_gt_ids, field_pred_ids)
                if "macro_f1" in field_metrics:
                    field_f1s.append(field_metrics["macro_f1"])
                    all_field_f1s.append(field_metrics["macro_f1"])  # ← Collect for system-level
                if "weighted_f1" in field_metrics:
                    field_weighted_f1s.append(field_metrics["weighted_f1"])
                    all_field_weighted_f1s.append(field_metrics["weighted_f1"])
        
        # Average F1 across fields in category (for category-level metrics)
        avg_macro_f1 = round(float(np.mean(field_f1s)), 4) if field_f1s else None
        avg_weighted_f1 = round(float(np.mean(field_weighted_f1s)), 4) if field_weighted_f1s else None
        
        result["classification"][sp] = {
            "macro_f1": avg_macro_f1,
            "weighted_f1": avg_weighted_f1,
            "note": f"Mean of {len(fields_in_cat)} field(s): {', '.join(fields_in_cat)}",
        }
        result["regression"][sp] = _regression_metrics(
            gt_ffa_by_cat[sp], pred_ffa_by_cat[sp]
        )

    # --- Global classification (all categories combined) ---
    all_gt_ids   = [r.gt_option_id   for r in all_records]
    all_pred_ids = [r.pred_option_id for r in all_records]
    # Global classification: treat all field option IDs independently
    # (not directly comparable across categories, but per spec §4.2)
    result["classification"]["global"] = {
        "note": "Cross-category classification metrics (option IDs not comparable across categories)",
        **_classification_metrics(all_gt_ids, all_pred_ids),
    }

    # --- Compute system-level macro F1 as mean of all 14 fields (field-unweighted) ---
    system_macro_f1 = round(float(np.mean(all_field_f1s)), 4) if all_field_f1s else None
    system_weighted_f1 = round(float(np.mean(all_field_weighted_f1s)), 4) if all_field_weighted_f1s else None

    result["classification"]["mean_across_categories"] = {
        "system_macro_f1":  system_macro_f1,
        "system_weighted_f1": system_weighted_f1,
        "balanced_accuracy": None,  # Not computed for system-level (14-field average)
    }

    # --- Global regression (all FFA values combined) ---
    all_gt_ffa   = [r.gt_ffa_value   for r in all_records]
    all_pred_ffa = [r.pred_ffa_value for r in all_records]
    result["regression"]["global"] = _regression_metrics(all_gt_ffa, all_pred_ffa)

    # --- Assembly-level FFA ---
    assemblies = sorted(set(r.assembly_id for r in all_records))
    asm_gt_ffa   = []
    asm_pred_ffa = []

    for asm_id in assemblies:
        asm_recs = [r for r in all_records if r.assembly_id == asm_id]
        gt_total, pred_total = compute_assembly_ffa_from_records(asm_recs)
        result["assembly_ffa"][asm_id] = {
            "name":            display_assembly_name(asm_id),
            "gt_total_ffa":   gt_total,
            "pred_total_ffa": pred_total,
            "abs_error":      round(abs(gt_total - pred_total), 4) if (gt_total is not None and pred_total is not None) else None,
            "n_steps":        len(set(r.step_id for r in asm_recs)),
            "n_criteria":     len(asm_recs),
        }
        if gt_total is not None and pred_total is not None:
            asm_gt_ffa.append(gt_total)
            asm_pred_ffa.append(pred_total)

    result["regression"]["assembly_ffa"] = _regression_metrics(asm_gt_ffa, asm_pred_ffa)

    # --- Soft score ---
    soft_scores = [1.0 - abs(r.gt_ffa_value - r.pred_ffa_value) for r in all_records]
    result["soft_score"] = round(float(np.mean(soft_scores)), 4) if soft_scores else None

    # --- Summary dict (for CSV / quick comparison) ---
    mean_cat = result["classification"]["mean_across_categories"]
    global_reg = result["regression"]["global"]
    asm_reg = result["regression"]["assembly_ffa"]

    result["summary"] = {
        "system_macro_f1":    mean_cat.get("system_macro_f1"),
        "weighted_f1":        mean_cat.get("weighted_f1"),
        "balanced_accuracy":  mean_cat.get("balanced_accuracy"),
        "criterion_mae":      global_reg.get("mae"),
        "criterion_rmse":     global_reg.get("rmse"),
        "criterion_r2":       global_reg.get("r2"),
        "criterion_spearman": global_reg.get("spearman_r"),
        "total_ffa_mae":      asm_reg.get("mae"),
        "total_ffa_rmse":     asm_reg.get("rmse"),
        "total_ffa_r2":       asm_reg.get("r2"),
        "total_ffa_spearman": asm_reg.get("spearman_r"),
        "soft_score":         result["soft_score"],
        "n_assemblies":       len(assemblies),
        "n_records":          len(all_records),
    }

    return result


# ============================================================================
# STATISTICAL TESTING
# ============================================================================

def mean_std_summary(values: List[float]) -> Dict:
    """Return mean/ci95/min/max/n for a list of floats.
    
    CI95 = 1.96 * std / sqrt(n)
    """
    if not values:
        return {"mean": None, "ci": None, "min": None, "max": None, "n": 0}
    a = np.array(values, dtype=float)
    n = len(a)
    std = float(np.std(a, ddof=1)) if n > 1 else 0.0
    # 95% confidence interval half-width: 1.96 * std_error, where std_error = std / sqrt(n)
    ci = round(1.96 * std / np.sqrt(n), 4) if n > 1 else 0.0
    return {
        "mean": round(float(np.mean(a)), 4),
        "ci":   ci,
        "min":  round(float(np.min(a)), 4),
        "max":  round(float(np.max(a)), 4),
        "n":    n,
    }


def interpret_effect_size(r_rb: float) -> str:
    """Interpret rank-biserial correlation as effect size label."""
    r = abs(r_rb)
    if r < 0.3:  return "klein"
    if r < 0.5:  return "mittel"
    return "groß"


def _bh_correct(p_values: List[float], alpha: float = 0.05) -> List[float]:
    """Benjamini-Hochberg FDR correction. Returns adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * n
    prev = 1.0
    for rank, (orig_idx, p) in enumerate(reversed(indexed), 1):
        adj = min(prev, p * n / (n - rank + 1))
        adjusted[orig_idx] = round(adj, 6)
        prev = adj
    return adjusted


def _run_mae(records: List[CriterionRecord]) -> Optional[float]:
    """Compute mean absolute error over all assemblies for one run's records."""
    assemblies = sorted(set(r.assembly_id for r in records))
    errors = []
    for asm in assemblies:
        recs = [r for r in records if r.assembly_id == asm]
        gt, pred = compute_assembly_ffa_from_records(recs)
        if gt is not None and pred is not None:
            errors.append(abs(gt - pred))
    return float(np.mean(errors)) if errors else None


def _run_macro_f1(records: List[CriterionRecord]) -> Optional[float]:
    """Compute mean macro-F1 across categories for one run's records."""
    from sklearn.metrics import f1_score
    f1_values = []
    for sp in ["separation", "handling", "positioning", "joining"]:
        cat_recs = [r for r in records if r.category == sp]
        if not cat_recs:
            continue
        gt_ids   = [r.gt_option_id   for r in cat_recs]
        pred_ids = [r.pred_option_id for r in cat_recs]
        labels   = sorted(set(gt_ids) | set(pred_ids))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            f1_values.append(float(f1_score(gt_ids, pred_ids, average="macro",
                                            labels=labels, zero_division=0)))
    return round(float(np.mean(f1_values)), 4) if f1_values else None


def _run_weighted_f1(records: List[CriterionRecord]) -> Optional[float]:
    """Compute mean weighted-F1 across categories for one run's records."""
    from sklearn.metrics import f1_score
    f1_values = []
    for sp in ["separation", "handling", "positioning", "joining"]:
        cat_recs = [r for r in records if r.category == sp]
        if not cat_recs:
            continue
        gt_ids   = [r.gt_option_id   for r in cat_recs]
        pred_ids = [r.pred_option_id for r in cat_recs]
        labels   = sorted(set(gt_ids) | set(pred_ids))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            f1_values.append(float(f1_score(gt_ids, pred_ids, average="weighted",
                                            labels=labels, zero_division=0)))
    return round(float(np.mean(f1_values)), 4) if f1_values else None


def statistical_testing_groups(
    group_a_runs: Dict[str, List[CriterionRecord]],
    group_b_runs: Dict[str, List[CriterionRecord]],
    name_a: str,
    name_b: str,
    dataset_label: str,
    alpha: float = 0.05,
) -> Dict:
    """
    Pairwise group comparison using per-run scalar metrics (independent samples).

    For each metric (total_ffa_mae, macro_f1):
      1. Compute one scalar per run → vec_a, vec_b
      2. Mann-Whitney-U test (primary, for independent samples)
      3. Welch's t-test (secondary, for independent samples)
      4. Rank-biserial correlation as effect size

    Runs are independent (not paired) - each run is a separate realization of the system.
    BH correction is applied externally across all comparisons.
    """
    # Build per-run metric vectors
    def _build_vec(runs: Dict[str, List[CriterionRecord]], fn) -> Tuple[List[str], List[float]]:
        run_ids, values = [], []
        for run_id in sorted(runs):
            v = fn(runs[run_id])
            if v is not None:
                run_ids.append(run_id)
                values.append(v)
        return run_ids, values

    result: Dict = {
        "name_a":       name_a,
        "name_b":       name_b,
        "dataset":      dataset_label,
        "alpha":        alpha,
        "metrics":      {},
    }

    for metric_key, fn in [("total_ffa_mae", _run_mae), ("system_macro_f1", _run_macro_f1), ("weighted_f1", _run_weighted_f1)]:
        ids_a, vec_a = _build_vec(group_a_runs, fn)
        ids_b, vec_b = _build_vec(group_b_runs, fn)

        # DEBUG: Log F1 score computation
        if "f1" in metric_key.lower():
            logger.debug(f"  [{name_a} vs {name_b}, {dataset_label}] {metric_key}: "
                        f"n_a={len(vec_a)} (val={vec_a[:3] if vec_a else 'None'}), "
                        f"n_b={len(vec_b)} (val={vec_b[:3] if vec_b else 'None'})")

        if len(vec_a) < 2 or len(vec_b) < 2:
            result["metrics"][metric_key] = {
                "note": f"Nicht genug Runs: n_a={len(vec_a)}, n_b={len(vec_b)} (mind. 2 nötig)"
            }
            continue

        a = np.array(vec_a)
        b = np.array(vec_b)

        # Mann-Whitney-U Test (unabhängige Stichproben - Runs sind nicht gepaart)
        # Auch wenn gleich viele Runs: Sie sind zeitlich/methodisch unabhängig, keine echten Paare
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                w_stat, w_p = stats.mannwhitneyu(a, b, alternative="two-sided")
            except Exception:
                w_stat, w_p = float("nan"), float("nan")

        # Welch's t-test (unabhängige Stichproben - auch mit ungleichen Varianzen robust)
        # Runs sind unabhängig, nicht gepaart
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                t_stat, t_p = stats.ttest_ind(a, b, equal_var=False)  # Welch
            except Exception:
                t_stat, t_p = float("nan"), float("nan")

        # Cohen's d für unabhängige Stichproben (pooled)
        try:
            pooled_std = np.sqrt(((len(a)-1)*np.std(a, ddof=1)**2 + (len(b)-1)*np.std(b, ddof=1)**2) / (len(a) + len(b) - 2))
            if pooled_std > 0:
                cohens_d = round(float((np.mean(a) - np.mean(b)) / pooled_std), 4)
            else:
                cohens_d = float("nan")
        except Exception:
            cohens_d = float("nan")

        # Permutation test
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                def _stat(x, y):
                    return float(np.mean(x) - np.mean(y))
                perm_res = stats.permutation_test(
                    (a, b), _stat,
                    permutation_type="samples",
                    n_resamples=10_000,
                    alternative="two-sided",
                    random_state=42,
                )
                perm_p    = round(float(perm_res.pvalue), 6)
                perm_stat = round(float(perm_res.statistic), 4)
            except Exception:
                perm_p, perm_stat = float("nan"), float("nan")

        # Rank-biserial correlation  r = 1 - 2W / (n_a * n_b)  (Mann-Whitney U form)
        try:
            u_stat, _ = stats.mannwhitneyu(a, b, alternative="two-sided")
            r_rb = round(float(1 - 2 * u_stat / (len(a) * len(b))), 4)
        except Exception:
            r_rb = float("nan")

        result["metrics"][metric_key] = {
            "vec_a":          [round(v, 4) for v in vec_a],
            "vec_b":          [round(v, 4) for v in vec_b],
            "run_ids_a":      ids_a,
            "run_ids_b":      ids_b,
            "summary_a":      mean_std_summary(vec_a),
            "summary_b":      mean_std_summary(vec_b),
            "mean_diff":      round(float(np.mean(a)) - float(np.mean(b)), 4),
            "note":           f"positive → {name_a} höher; negative → {name_b} höher",
            "mannwhitneyu":   {"statistic": round(float(w_stat), 4), "p_raw": float(w_p)},
            "ttest":          {"statistic": round(float(t_stat), 4), "p_raw": float(t_p),
                               "cohens_d": cohens_d,
                               "paired": False},  # Immer unabhängig, Runs sind nicht gepaart
            "permutation":    {"statistic": perm_stat, "p_raw": perm_p},
            "p_adjusted_bh":  None,   # filled in externally after BH correction
            "significant":    None,   # filled in externally
            "rank_biserial_r": r_rb,
            "effect_label":   interpret_effect_size(r_rb) if not np.isnan(r_rb) else "n/a",
        }

    return result


def apply_bh_correction(comparisons: List[Dict], alpha: float = 0.05) -> None:
    """
    Apply Benjamini-Hochberg FDR correction across all p-values in a list
    of comparison dicts (as returned by statistical_testing_groups).
    Modifies dicts in-place.
    """
    # Collect all (comparison_idx, metric_key, test_key) → p_raw
    entries = []  # (comp_idx, metric_key, test_key)
    p_raws  = []
    for ci, comp in enumerate(comparisons):
        for mk, mv in comp.get("metrics", {}).items():
            if not isinstance(mv, dict):
                continue
            # ONLY Mann-Whitney-U (not ttest, not permutation)
            if "mannwhitneyu" in mv and "p_raw" in mv["mannwhitneyu"]:
                p = mv["mannwhitneyu"]["p_raw"]
                if not (p != p):  # not NaN
                    entries.append((ci, mk, "mannwhitneyu"))
                    p_raws.append(p)

    if not p_raws:
        return

    adjusted = _bh_correct(p_raws, alpha=alpha)

    for (ci, mk, tk), p_adj in zip(entries, adjusted):
        mv = comparisons[ci]["metrics"][mk]
        mv[tk]["p_adjusted_bh"] = p_adj
        # Set significance flag based on Mann-Whitney-U BH-adjusted p
        if tk == "mannwhitneyu":
            mv["p_adjusted_bh"] = p_adj
            mv["significant"]   = bool(p_adj < alpha)
        elif tk == "ttest":
            mv[tk]["p_adjusted_bh"] = p_adj


# ---------------------------------------------------------------------------
# Legacy wrapper kept for backward-compat (single-records comparison)
# ---------------------------------------------------------------------------
def statistical_testing(
    records_a: List[CriterionRecord],
    records_b: List[CriterionRecord],
    name_a: str = "Experiment A",
    name_b: str = "Experiment B",
) -> Dict:
    """Legacy: wraps statistical_testing_groups treating each records list as one 'run'."""
    return statistical_testing_groups(
        {"run1": records_a},
        {"run1": records_b},
        name_a=name_a,
        name_b=name_b,
        dataset_label="?",
    )


# ============================================================================
# CSV EXPORT
# ============================================================================

def save_csvs(
    records: List[CriterionRecord],
    metrics: Dict,
    output_dir: Path,
    experiment_name: str,
    dataset_label: str,
) -> Dict[str, Path]:
    """Save all four CSV files per spec §10."""
    import csv

    output_dir.mkdir(parents=True, exist_ok=True)
    saved = {}

    # 10.1 Step-level (criterion-level)
    step_path = output_dir / "step_level_metrics.csv"
    with open(step_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "experiment", "dataset", "assembly_id", "step_id", "step_description",
            "category", "field_name", "criterion_weight", "category_weight",
            "gt_option_id", "pred_option_id", "correct",
            "gt_ffa_value", "pred_ffa_value", "abs_error", "soft_score",
        ])
        writer.writeheader()
        for r in records:
            writer.writerow({
                "experiment":       experiment_name,
                "dataset":          dataset_label,
                "assembly_id":      r.assembly_id,
                "step_id":          r.step_id,
                "step_description": r.step_description,
                "category":         r.category,
                "field_name":       r.field_name,
                "criterion_weight": r.criterion_weight,
                "category_weight":  r.category_weight,
                "gt_option_id":     r.gt_option_id,
                "pred_option_id":   r.pred_option_id,
                "correct":          int(r.gt_option_id == r.pred_option_id),
                "gt_ffa_value":     r.gt_ffa_value,
                "pred_ffa_value":   r.pred_ffa_value,
                "abs_error":        r.abs_error,
                "soft_score":       round(1.0 - r.abs_error, 4),
            })
    saved["step_level"] = step_path

    # 10.2 Category-level
    cat_path = output_dir / "category_level_metrics.csv"
    with open(cat_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "experiment", "dataset", "category",
            "macro_f1", "weighted_f1", "balanced_accuracy",
            "accuracy", "macro_precision", "macro_recall",
            "mae", "rmse", "r2", "spearman_r", "n_samples",
        ])
        writer.writeheader()
        for sp in SUBPROCESSES:
            clf = metrics["classification"].get(sp, {})
            reg = metrics["regression"].get(sp, {})
            writer.writerow({
                "experiment":       experiment_name,
                "dataset":          dataset_label,
                "category":         sp,
                "macro_f1":         clf.get("macro_f1"),
                "weighted_f1":      clf.get("weighted_f1"),
                "balanced_accuracy":clf.get("balanced_accuracy"),
                "accuracy":         clf.get("accuracy"),
                "macro_precision":  clf.get("macro_precision"),
                "macro_recall":     clf.get("macro_recall"),
                "mae":              reg.get("mae"),
                "rmse":             reg.get("rmse"),
                "r2":               reg.get("r2"),
                "spearman_r":       reg.get("spearman_r"),
                "n_samples":        clf.get("n_samples"),
            })
    saved["category_level"] = cat_path

    # 10.3 Assembly-level
    asm_path = output_dir / "assembly_level_metrics.csv"
    with open(asm_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "experiment", "dataset", "assembly_id", "assembly_name",
            "gt_total_ffa", "pred_total_ffa", "abs_error", "soft_score",
            "n_steps", "n_criteria",
        ])
        writer.writeheader()
        for asm_id, asm_data in sorted(metrics["assembly_ffa"].items()):
            ae = asm_data.get("abs_error")
            writer.writerow({
                "experiment":    experiment_name,
                "dataset":       dataset_label,
                "assembly_id":   asm_id,
                "assembly_name": asm_data.get("name", display_assembly_name(asm_id)),
                "gt_total_ffa":  asm_data.get("gt_total_ffa"),
                "pred_total_ffa":asm_data.get("pred_total_ffa"),
                "abs_error":     ae,
                "soft_score":    round(1.0 - ae, 4) if ae is not None else None,
                "n_steps":       asm_data.get("n_steps"),
                "n_criteria":    asm_data.get("n_criteria"),
            })
    saved["assembly_level"] = asm_path

    # 10.4 Experiment summary
    summary = metrics["summary"]
    exp_path = output_dir / "experiment_summary.csv"
    with open(exp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "experiment", "dataset",
            "macro_f1", "weighted_f1", "balanced_accuracy",
            "total_ffa_mae", "total_ffa_rmse", "total_ffa_r2", "total_ffa_spearman",
            "criterion_mae", "criterion_rmse", "criterion_r2",
            "soft_score", "n_assemblies", "n_records",
        ])
        writer.writeheader()
        writer.writerow({
            "experiment":       experiment_name,
            "dataset":          dataset_label,
            "macro_f1":         summary.get("macro_f1"),
            "weighted_f1":      summary.get("weighted_f1"),
            "balanced_accuracy":summary.get("balanced_accuracy"),
            "total_ffa_mae":    summary.get("total_ffa_mae"),
            "total_ffa_rmse":   summary.get("total_ffa_rmse"),
            "total_ffa_r2":     summary.get("total_ffa_r2"),
            "total_ffa_spearman":summary.get("total_ffa_spearman"),
            "criterion_mae":    summary.get("criterion_mae"),
            "criterion_rmse":   summary.get("criterion_rmse"),
            "criterion_r2":     summary.get("criterion_r2"),
            "soft_score":       summary.get("soft_score"),
            "n_assemblies":     summary.get("n_assemblies"),
            "n_records":        summary.get("n_records"),
        })
    saved["experiment_summary"] = exp_path

    logger.info(f"  Saved CSVs to {output_dir}")
    return saved


# ============================================================================
# REPORTING – Category Performance Ranking
# ============================================================================

def generate_category_ranking_report(
    records: List[CriterionRecord],
    experiment_name: str,
    dataset_label: str,
) -> Tuple[str, Dict]:
    """
    Generate a table report showing FFA fields ranked by macro F1 (worst to best).
    
    Args:
        records: List of CriterionRecord from evaluation
        experiment_name: Name of the experiment
        dataset_label: "Eval Set" or "Test Set"
    
    Returns:
        (table_string, ranking_dict)
    """
    from collections import defaultdict
    
    if not records:
        return "", {"experiment": experiment_name, "dataset": dataset_label, "rankings": []}
    
    # Group by field_name
    gt_by_field: Dict[str, List[int]] = defaultdict(list)
    pred_by_field: Dict[str, List[int]] = defaultdict(list)
    
    for r in records:
        if r.category and r.field_name:  # Only valid records
            gt_by_field[r.field_name].append(r.gt_option_id)
            pred_by_field[r.field_name].append(r.pred_option_id)
    
    # Compute metrics per field
    rankings = []
    for field_name in sorted(gt_by_field.keys()):
        gt_ids = gt_by_field[field_name]
        pred_ids = pred_by_field[field_name]
        
        if not gt_ids or not pred_ids:
            continue
        
        field_metrics = _classification_metrics(gt_ids, pred_ids)
        macro_f1 = field_metrics.get("macro_f1")
        weighted_f1 = field_metrics.get("weighted_f1")
        bal_acc = field_metrics.get("balanced_accuracy")
        
        if macro_f1 is not None:
            rankings.append({
                "field_name": field_name,
                "macro_f1": macro_f1,
                "weighted_f1": weighted_f1,
                "balanced_accuracy": bal_acc,
            })
    
    # Sort by macro_f1 (worst first)
    rankings.sort(key=lambda x: x["macro_f1"])
    
    # Build table header and rows
    lines = []
    lines.append("")
    lines.append(f"  Field Performance Ranking  –  {experiment_name} / {dataset_label}")
    lines.append(f"  {'Rank':<6} {'Field Name':<30} {'Macro F1':<12} {'Weighted F1':<14} {'Bal. Acc.':<12}")
    lines.append(f"  {'-'*90}")
    
    for rank, item in enumerate(rankings, 1):
        field_display = item['field_name'].replace('_', ' ').title()[:28]
        macro_f1_str = f"{item['macro_f1']:.4f}" if item['macro_f1'] is not None else "N/A"
        w_f1_str = f"{item['weighted_f1']:.4f}" if item['weighted_f1'] is not None else "N/A"
        bal_acc_str = f"{item['balanced_accuracy']:.4f}" if item['balanced_accuracy'] is not None else "N/A"
        
        lines.append(
            f"  {rank:<6} {field_display:<30} {macro_f1_str:<12} {w_f1_str:<14} {bal_acc_str:<12}"
        )
    
    lines.append(f"  {'-'*90}")
    lines.append("")
    
    table_str = "\n".join(lines)
    return table_str, {"experiment": experiment_name, "dataset": dataset_label, "rankings": rankings}


# ============================================================================
# SHAPIRO-WILK NORMALITY TESTING
# ============================================================================

def compute_shapiro_wilk_normality_tests(
    records_per_group: Dict[str, Dict[str, Dict[str, List[CriterionRecord]]]],
    output_dir: Path,
    alpha: float = 0.05,
) -> Tuple[Path, List[Dict]]:
    """
    Compute Shapiro-Wilk normality test for abs_error values per (Assembly, Group, Dataset).
    
    The test checks if the distribution of prediction errors across runs follows a normal distribution.
    
    Args:
        records_per_group: Dict structure:
            {group_name: {run_id: {dataset_key: [CriterionRecord, ...]}}}
        output_dir: Directory to save the CSV results
        alpha: Significance level (default 0.05)
    
    Returns:
        Tuple of (Path to CSV file, List of result dictionaries)
    
    CSV columns:
        - Baugruppe (Assembly ID)
        - Experiment (Group name)
        - Dataset (eval/test)
        - Anzahl_Runs (number of runs with data)
        - Shapiro_Wilk_Statistic
        - Shapiro_Wilk_p_value
        - Ist_Normalverteilt (ja/nein)
    """
    import csv
    from collections import defaultdict
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect abs_error values per (assembly, group, dataset)
    # Structure: {(assembly_id, group_name, dataset_key): [abs_errors from multiple runs]}
    error_distributions: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    
    # Iterate through all groups
    for group_name, run_map in sorted(records_per_group.items()):
        # Iterate through all runs within group
        for run_id, ds_map in sorted(run_map.items()):
            # Iterate through all datasets (eval/test)
            for ds_key, records_list in sorted(ds_map.items()):
                if not records_list:
                    continue
                
                # For each assembly in this run × dataset
                assemblies_in_run = sorted(set(r.assembly_id for r in records_list))
                for asm_id in assemblies_in_run:
                    # Get all records for this assembly
                    asm_records = [r for r in records_list if r.assembly_id == asm_id]
                    if not asm_records:
                        continue
                    
                    # Compute total FFA error for this assembly
                    gt_total, pred_total = compute_assembly_ffa_from_records(asm_records)
                    if gt_total is not None and pred_total is not None:
                        abs_error = abs(gt_total - pred_total)
                        key = (asm_id, group_name, ds_key)
                        error_distributions[key].append(abs_error)
    
    # Perform Shapiro-Wilk test and collect results
    results = []
    
    for (asm_id, group_name, ds_key), errors in sorted(error_distributions.items()):
        n_runs = len(errors)
        
        # Shapiro-Wilk requires at least 3 samples
        if n_runs < 3:
            stat = None
            p_value = None
            is_normal = "n/a (n < 3)"
        else:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    stat, p_value = stats.shapiro(errors)
                    stat = round(float(stat), 6)
                    p_value = round(float(p_value), 6)
                    # Normal distribution if p > 0.05 (fail to reject H0)
                    is_normal = "ja" if p_value > alpha else "nein"
            except Exception as e:
                logger.warning(f"Shapiro-Wilk test failed for {asm_id}/{group_name}/{ds_key}: {e}")
                stat = None
                p_value = None
                is_normal = "Error"
        
        results.append({
            "Baugruppe": asm_id,
            "Experiment": group_name,
            "Dataset": ds_key,
            "Anzahl_Runs": n_runs,
            "Shapiro_Wilk_Statistic": stat,
            "Shapiro_Wilk_p_value": p_value,
            "Ist_Normalverteilt": is_normal,
        })
    
    # Save to CSV
    csv_path = output_dir / "shapiro_wilk_normality_test.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Baugruppe",
                "Experiment",
                "Dataset",
                "Anzahl_Runs",
                "Shapiro_Wilk_Statistic",
                "Shapiro_Wilk_p_value",
                "Ist_Normalverteilt",
            ],
        )
        writer.writeheader()
        writer.writerows(results)
    
    logger.info(f"  Saved Shapiro-Wilk normality tests to {csv_path}")
    return csv_path, results


# ============================================================================
# STATISTICAL TESTING – CSV EXPORT (Wilcoxon only)
# ============================================================================

def save_statistical_testing_csv(
    comparisons: List[Dict],
    output_dir: Path,
    dataset_label: str = "eval",
) -> Path:
    """
    Save statistical testing results (Wilcoxon only) to CSV.
    
    Args:
        comparisons: List of comparison dicts from statistical_testing_groups
        output_dir: Directory to save CSV
        dataset_label: "eval" or "test"
    
    Returns:
        Path to saved CSV
    
    CSV columns:
        - Vergleich (name_a vs name_b)
        - Dataset
        - Metrik
        - n_runs_a
        - n_runs_b
        - mean_a
        - std_a
        - mean_b
        - std_b
        - mean_diff
        - Wilcoxon_W_Statistic
        - Wilcoxon_p_raw
        - Wilcoxon_p_adjusted_BH
        - rank_biserial_r
        - Effekt_Größe
        - Signifikant
    """
    import csv
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rows = []
    
    for comp in comparisons:
        name_a = comp["name_a"]
        name_b = comp["name_b"]
        dataset_key = comp["dataset"]
        
        for metric_key, mv in comp.get("metrics", {}).items():
            # Skip if note without vec_a (not enough data)
            if "note" in mv and "vec_a" not in mv:
                rows.append({
                    "Vergleich": f"{name_a} vs {name_b}",
                    "Dataset": dataset_key,
                    "Metrik": metric_key,
                    "n_runs_a": None,
                    "n_runs_b": None,
                    "mean_a": None,
                    "std_a": None,
                    "mean_b": None,
                    "std_b": None,
                    "mean_diff": None,
                    "Wilcoxon_W_Statistic": None,
                    "Wilcoxon_p_raw": None,
                    "Wilcoxon_p_adjusted_BH": None,
                    "rank_biserial_r": None,
                    "Effekt_Größe": None,
                    "Signifikant": None,
                    "Note": mv.get("note", ""),
                })
                continue
            
            # Extract Wilcoxon stats
            w = mv.get("wilcoxon", {})
            w_stat = w.get("statistic", None)
            w_p_raw = w.get("p_raw", None)
            w_p_bh = mv.get("p_adjusted_bh", None)
            r_rb = mv.get("rank_biserial_r", None)
            eff = mv.get("effect_label", "")
            sig = "ja" if mv.get("significant") else ("nein" if mv.get("significant") is False else "?")
            
            # Extract summary stats
            sum_a = mv.get("summary_a", {})
            sum_b = mv.get("summary_b", {})
            
            rows.append({
                "Vergleich": f"{name_a} vs {name_b}",
                "Dataset": dataset_key,
                "Metrik": metric_key,
                "n_runs_a": sum_a.get("n"),
                "n_runs_b": sum_b.get("n"),
                "mean_a": sum_a.get("mean"),
                "std_a": sum_a.get("std"),
                "mean_b": sum_b.get("mean"),
                "std_b": sum_b.get("std"),
                "mean_diff": mv.get("mean_diff"),
                "Wilcoxon_W_Statistic": w_stat,
                "Wilcoxon_p_raw": w_p_raw,
                "Wilcoxon_p_adjusted_BH": w_p_bh,
                "rank_biserial_r": r_rb,
                "Effekt_Größe": eff,
                "Signifikant": sig,
                "Note": mv.get("note", ""),
            })
    
    # Save to CSV
    csv_path = output_dir / f"cross_E_stat_table_{dataset_label}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Vergleich",
                "Dataset",
                "Metrik",
                "n_runs_a",
                "n_runs_b",
                "mean_a",
                "std_a",
                "mean_b",
                "std_b",
                "mean_diff",
                "Wilcoxon_W_Statistic",
                "Wilcoxon_p_raw",
                "Wilcoxon_p_adjusted_BH",
                "rank_biserial_r",
                "Effekt_Größe",
                "Signifikant",
                "Note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    
    logger.info(f"  Saved statistical testing (Wilcoxon) to {csv_path}")
    return csv_path
