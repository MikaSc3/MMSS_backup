"""
Standalone test script for FFA post-processing node.
Tests metrics calculation and plot generation.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add agent paths
sys.path.insert(0, str(Path(__file__).parent))

from evaluation.ffa_evaluator import (
    CriterionRecord,
    FIELD_TO_SUBPROCESS,
    SUBPROCESSES,
    _parse_assessment_file,
    CATEGORY_WEIGHT,
)
from evaluation.ffa_scoring import (
    resolve_ffa_value,
    resolve_option_id,
    get_criterion_weight,
)
from evaluation.ffa_plots import _step_ffa_from_records, _COLOR_GT


def create_criterion_records_from_gt(
    assembly_id: str,
    gt_file: Path,
) -> list:
    """Create CriterionRecords from GT assessment file (no prediction needed)."""
    records = []
    
    try:
        gt_steps = _parse_assessment_file(gt_file)
    except Exception as e:
        print(f"  ERROR loading GT file: {e}")
        return []
    
    for step_key, step_data in gt_steps.items():
        step_id = str(step_data.get("step_id", step_key))
        step_desc = step_data.get("step_description", step_id)
        assessment = step_data.get("assessment", {})
        
        for sp in SUBPROCESSES:
            sp_data = assessment.get(sp, {})
            
            for field_name, gt_id in sp_data.items():
                if field_name not in FIELD_TO_SUBPROCESS:
                    continue
                
                gt_ffa = resolve_ffa_value(field_name, gt_id)
                if gt_ffa is None:
                    continue
                
                gt_opt_id = resolve_option_id(field_name, gt_id)
                if gt_opt_id is None:
                    continue
                
                records.append(CriterionRecord(
                    assembly_id=assembly_id,
                    step_id=step_id,
                    step_description=step_desc,
                    category=sp,
                    field_name=field_name,
                    criterion_weight=get_criterion_weight(field_name),
                    category_weight=CATEGORY_WEIGHT,
                    gt_option_id=gt_opt_id,
                    pred_option_id=gt_opt_id,  # use GT as "prediction" too
                    gt_ffa_value=float(gt_ffa),
                    pred_ffa_value=float(gt_ffa),  # same as GT for now
                    abs_error=0.0,
                    run_id="",
                ))
    
    return records


def calculate_metrics(records: list) -> dict:
    """Calculate assembly-level and step-level metrics."""
    if not records:
        return {}
    
    # Assembly level
    gt_ffa_vals = [r.gt_ffa_value for r in records]
    assembly_ffa_gt = float(np.mean(gt_ffa_vals)) if gt_ffa_vals else 0.0
    
    # Per subprocess
    sp_ffas = defaultdict(list)
    for r in records:
        sp_ffas[r.category].append(r.gt_ffa_value)
    
    subprocess_metrics = {
        sp: float(np.mean(vals)) if vals else 0.0
        for sp, vals in sp_ffas.items()
    }
    
    # Per step
    step_metrics = _step_ffa_from_records(records, use_gt=True)
    
    return {
        "assembly_ffa_gt": assembly_ffa_gt,
        "subprocess_metrics": subprocess_metrics,
        "step_metrics": step_metrics,
        "n_records": len(records),
    }


def save_step_level_csv(records: list, output_path: Path) -> None:
    """Save step-level metrics to CSV."""
    step_metrics = _step_ffa_from_records(records, use_gt=True)
    
    rows = []
    for step_id in sorted(step_metrics.keys(), key=lambda x: int(x) if x.isdigit() else x):
        rows.append({
            "step_id": step_id,
            "ffa_score": step_metrics[step_id],
        })
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"✓ Saved step_level_metrics: {output_path}")


def save_assembly_level_json(metrics: dict, output_path: Path) -> None:
    """Save assembly-level metrics to JSON."""
    data = {
        "assembly_ffa_gt": metrics.get("assembly_ffa_gt", 0.0),
        "subprocess_metrics": metrics.get("subprocess_metrics", {}),
        "n_records": metrics.get("n_records", 0),
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Saved assembly_level_metrics: {output_path}")


def save_step_level_plot(records: list, assembly_name: str, output_path: Path) -> None:
    """Save a minimal per-step FFA plot using run_evaluation visual style."""
    step_metrics = _step_ffa_from_records(records, use_gt=True)
    if not step_metrics:
        print("⚠ No step metrics found, skipping plot generation")
        return

    step_ids = sorted(step_metrics.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))
    x = list(range(1, len(step_ids) + 1))
    y = [step_metrics[sid] for sid in step_ids]

    fig, ax = plt.subplots(figsize=(max(7, len(step_ids) * 1.2 + 2), 5))
    fig.suptitle(f"{assembly_name}  -  FFA per Step", fontsize=11, fontweight="bold")

    # Match run_evaluation GT style: green line + filled dots with white edge.
    ax.plot(x, y, color=_COLOR_GT, linewidth=2.0, zorder=6)
    ax.scatter(x, y, color=_COLOR_GT, s=70, zorder=7, edgecolors="white", linewidths=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels([f"Step {sid}" for sid in step_ids], fontsize=8.5, rotation=0)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Assembly Step", fontsize=10)
    ax.set_ylabel("FFA Score", fontsize=10)
    ax.grid(True, axis="y", linestyle="-", alpha=0.22)
    ax.grid(False, axis="x")
    ax.margins(x=0.03)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    print(f"✓ Saved step_level_plot: {output_path}")


def main():
    # Test path
    test_dir = Path("data/experiments/final_ffa_for_eval/End_to_End_final_System/Stehlager_Sicherungsring")
    
    # Try to find FFA assessment file
    ffa_file = test_dir / "ffa_assessment" / "ffa_assessment_enum_gt.json"
    if not ffa_file.exists():
        # Fallback: use regular ffa_assessment.json if enum_gt doesn't exist
        ffa_file = test_dir / "ffa_assessment" / "ffa_assessment.json"
    
    if not ffa_file.exists():
        print(f"✗ FFA assessment file not found in: {test_dir / 'ffa_assessment'}")
        sys.exit(1)
    
    print(f"[test_ffa_post_processing] Testing on: {test_dir}")
    print(f"[test_ffa_post_processing] FFA file: {ffa_file}")
    
    # Create records
    print("\n[1] Creating CriterionRecords from GT...")
    records = create_criterion_records_from_gt("Stehlager_Sicherungsring", ffa_file)
    print(f"  → Created {len(records)} records")
    
    if not records:
        print("✗ No records created!")
        sys.exit(1)
    
    # Calculate metrics
    print("\n[2] Calculating metrics...")
    metrics = calculate_metrics(records)
    print(f"  Assembly FFA (GT): {metrics['assembly_ffa_gt']:.3f}")
    print(f"  Subprocess metrics: {metrics['subprocess_metrics']}")
    print(f"  Step metrics: {metrics['step_metrics']}")
    
    # Save outputs
    output_dir = test_dir / "ffa_report" / "metrics"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n[3] Saving outputs to: {output_dir}")
    save_step_level_csv(records, output_dir / "Stehlager_Sicherungsring_step_level_metrics.csv")
    save_assembly_level_json(metrics, output_dir / "assembly_level_metrics.json")
    save_step_level_plot(records, "Stehlager_Sicherungsring", output_dir / "Stehlager_Sicherungsring_step_level_metrics.png")
    
    print("\n✓ Test completed successfully!")


if __name__ == "__main__":
    main()
