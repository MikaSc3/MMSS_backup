"""
Cross-Experiment Metrics and Combined Ranking.

Generates CSV files for cross-experiment comparison with combined metric ranking.
"""

import csv
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def save_cross_experiment_csv(
    cross_metrics: Dict,
    group_summary: Dict,
    output_dir: Path,
    dataset_key: str = "eval",
    dataset_label: str = "Eval Set (#F582)",
) -> Optional[Path]:
    """
    Save cross-experiment comparison CSV with combined metric ranking.
    
    Formula:
        Combined = 0.33 * Norm(MAE) + 0.33 * Norm(STD) + 0.33 * Norm(F1)
    
    Where:
        - Norm(MAE) = (max_MAE - value) / (max_MAE - min_MAE)  [inverted: lower=better]
        - Norm(STD) = (max_STD - value) / (max_STD - min_STD)  [inverted: lower=better]
        - Norm(F1) = (value - min_F1) / (max_F1 - min_F1)      [direct: higher=better]
    
    Args:
        cross_metrics: Dict of experiment results {exp_name: {ds_key: {summary: {...}}}}
        group_summary: Dict with mean/std across runs {group_name: {ds_key: {...}}}
        output_dir: Directory to save CSV
        dataset_key: "eval" or "test"
        dataset_label: Display label for dataset
    
    Returns:
        Path to saved CSV file, or None if no data
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect metrics per run, then aggregate by experiment group
    metrics_by_run = {}  # {exp_name: {"mae": float, "f1": float, ...}}
    
    for exp_name in sorted(cross_metrics.keys()):
        ds_map = cross_metrics[exp_name]
        summary = ds_map.get(dataset_key, {}).get("summary", {})
        
        if not summary:
            continue
        
        mae = summary.get("total_ffa_mae")
        f1 = summary.get("system_macro_f1")
        f1_per_criterion = summary.get("macro_f1_per_criterion")
        
        if mae is not None and f1 is not None:
            metrics_by_run[exp_name] = {
                "mae": mae,
                "f1": f1,
                "f1_per_criterion": f1_per_criterion,
            }
    
    if not metrics_by_run:
        return None
    
    # Aggregate by experiment group (mean of runs, std from group_summary)
    metrics_by_group = {}  # {group_name: {"mae": float, "f1": float, "std": float, "n_runs": int}}
    
    for exp_name, metrics in metrics_by_run.items():
        # Extract group name from exp_name (format: "group_name__run_id" or just "group_name")
        if "__" in exp_name:
            group_name = exp_name.split("__")[0]
        else:
            group_name = exp_name
        
        if group_name not in metrics_by_group:
            metrics_by_group[group_name] = {
                "f1_values": [],
                "mae_values": [],
                "f1_per_criterion": metrics.get("f1_per_criterion"),
            }
        
        metrics_by_group[group_name]["f1_values"].append(metrics["f1"])
        metrics_by_group[group_name]["mae_values"].append(metrics["mae"])
    
    # Compute mean ± std per group
    aggregated = {}
    for group_name, data in metrics_by_group.items():
        f1_vals = data["f1_values"]
        mae_vals = data["mae_values"]
        
        import numpy as np
        mean_f1 = float(np.mean(f1_vals)) if f1_vals else None
        mean_mae = float(np.mean(mae_vals)) if mae_vals else None
        std_f1 = float(np.std(f1_vals, ddof=1)) if len(f1_vals) > 1 else 0.0
        std_mae = float(np.std(mae_vals, ddof=1)) if len(mae_vals) > 1 else 0.0
        
        # Get std from group_summary if available
        std_from_group_summary = None
        if group_name in group_summary and dataset_key in group_summary[group_name]:
            std_dict = group_summary[group_name].get(dataset_key, {})
            mae_std_dict = std_dict.get("total_ffa_mae", {})
            std_from_group_summary = mae_std_dict.get("std")
        
        aggregated[group_name] = {
            "mean_f1": mean_f1,
            "mean_mae": mean_mae,
            "std_f1": std_f1,
            "std_mae": std_mae,
            "std_from_group_summary": std_from_group_summary,
            "f1_per_criterion": data["f1_per_criterion"],
            "n_runs": len(f1_vals),
        }
    
    if not aggregated:
        return None
    
    # Compute min/max for normalization
    means_mae = [m["mean_mae"] for m in aggregated.values() if m["mean_mae"] is not None]
    means_f1 = [m["mean_f1"] for m in aggregated.values() if m["mean_f1"] is not None]
    stds_mae = [m["std_from_group_summary"] or m["std_mae"] for m in aggregated.values() if (m["std_from_group_summary"] or m["std_mae"]) is not None]
    
    mae_min = min(means_mae) if means_mae else 0
    mae_max = max(means_mae) if means_mae else 1
    f1_min = min(means_f1) if means_f1 else 0
    f1_max = max(means_f1) if means_f1 else 1
    std_min = min(stds_mae) if stds_mae else 0
    std_max = max(stds_mae) if stds_mae else 1
    
    # Compute combined metrics and rankings
    combined_by_group = {}
    for group_name, metrics in aggregated.items():
        mean_mae = metrics["mean_mae"]
        mean_f1 = metrics["mean_f1"]
        std_val = metrics["std_from_group_summary"] or metrics["std_mae"]
        f1_per_criterion = metrics["f1_per_criterion"]
        
        # Normalize
        norm_mae = (mae_max - mean_mae) / (mae_max - mae_min) if mae_max > mae_min else 0.5
        norm_f1 = (mean_f1 - f1_min) / (f1_max - f1_min) if f1_max > f1_min else 0.5
        norm_std = (std_max - std_val) / (std_max - std_min) if std_max > std_min else 0.5
        
        combined = 0.33 * norm_mae + 0.33 * norm_std + 0.33 * norm_f1
        combined_by_group[group_name] = {
            "mean_mae": mean_mae,
            "mean_f1": mean_f1,
            "std_mae": std_val,
            "f1_per_criterion": f1_per_criterion,
            "norm_mae": norm_mae,
            "norm_f1": norm_f1,
            "norm_std": norm_std,
            "combined": combined,
            "n_runs": metrics["n_runs"],
        }
    
    # Rank by combined metric
    ranked = sorted(
        combined_by_group.items(),
        key=lambda x: x[1]["combined"],
        reverse=True,
    )
    
    # Save to CSV
    csv_filename = f"cross_E_ffa_deviation_{dataset_key}.csv"
    csv_path = output_dir / csv_filename
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rank",
            "experiment",
            "n_runs",
            "dataset",
            "system_macro_f1_mean",
            "system_macro_f1_std",
            "macro_f1_per_criterion",
            "total_ffa_mae_mean",
            "std_ffa_mae",
            "combined_metric",
        ])
        writer.writeheader()
        
        for rank_num, (group_name, metrics) in enumerate(ranked, 1):
            writer.writerow({
                "rank": rank_num,
                "experiment": group_name,
                "n_runs": metrics["n_runs"],
                "dataset": dataset_label,
                "system_macro_f1_mean": round(metrics["mean_f1"], 4),
                "system_macro_f1_std": round(metrics.get("std_f1", 0), 4),
                "macro_f1_per_criterion": round(metrics.get("f1_per_criterion", 0), 4) if metrics.get("f1_per_criterion") is not None else "",
                "total_ffa_mae_mean": round(metrics["mean_mae"], 4),
                "std_ffa_mae": round(metrics["std_mae"], 4),
                "combined_metric": round(metrics["combined"], 4),
            })
    
    return csv_path
