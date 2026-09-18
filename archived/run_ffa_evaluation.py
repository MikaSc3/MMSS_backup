"""
Run FFA Evaluation for FFA-Only Experiments

Neue Evaluation für data/experiments/ffa_experiments/ Structure
- Macro-Average Metriken (nicht Weighted)
- Confusion Matrices pro Assembly
- Per-Class Metrics
- Assembly Ranking
- Experiment Comparison

Structure expected:
    data/experiments/ffa_experiments/
    ├── exp1_name/
    │   └── Assembly_Name/
    │       ├── Assembly_Name_ffa_assessment_enum.json (predictions)
    │       └── ... other files
    └── exp2_name/
        └── Assembly_Name/
            ├── Assembly_Name_ffa_assessment_enum.json (predictions)
            └── ... other files

Usage:
    python run_ffa_evaluation.py
    
    Evaluates all experiments in data/experiments/ffa_experiments/
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import cm

from evaluation.ffa_metrics import (
    evaluate_experiment,
    rank_assemblies,
    create_class_distribution_analysis,
    load_ffa_data
)
from evaluation.ffa_visualization import (
    save_confusion_matrix,
    save_per_class_metrics_chart,
    save_assembly_summary_chart,
    save_class_distribution_heatmap,
    save_macro_comparison_chart,
    save_assembly_ranking_chart,
    save_step_overview_chart
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Load enum mapping globally
ENUM_MAPPING_FILE = Path("data/ground_truth/ffa_ground_truth/ffa_enum_mapping.json")
ENUM_MAPPING = None

def load_enum_mapping():
    """Lädt das FFA Enum Mapping."""
    global ENUM_MAPPING
    if ENUM_MAPPING_FILE.exists():
        with open(ENUM_MAPPING_FILE, 'r') as f:
            ENUM_MAPPING = json.load(f)
        print(f"✓ Loaded enum mapping with {len(ENUM_MAPPING)} fields")
        return ENUM_MAPPING
    else:
        logger.warning(f"Enum mapping not found at {ENUM_MAPPING_FILE}")
        return {}


# ============================================================================
# MAIN ORCHESTRATOR (DUAL DATASET MODE)
# ============================================================================

def run_ffa_evaluation(
    experiments_root: Path,
    eval_set_path: Path = None,
    test_set_path: Path = None
) -> None:
    """
    Orchestriert die komplette FFA Evaluation über alle Experimente mit ZWEI Datasets.
    
    Args:
        experiments_root: Path zu ffa_experiments/ folder mit exp1/, exp2/, etc.
        eval_set_path: Path zu ffa_ground_truth_evaluierungsdaten (#F58220)
        test_set_path: Path zu ffa_ground_truth_testdaten (#179C7D)
    """
    # Load enum mapping first
    load_enum_mapping()
    
    if eval_set_path is None:
        eval_set_path = Path(__file__).resolve().parent / "data" / "ground_truth" / "ffa_ground_truth_evaluierungsdaten"
    
    if test_set_path is None:
        test_set_path = Path(__file__).resolve().parent / "data" / "ground_truth" / "ffa_ground_truth_testdaten"
    
    print(f"\n{'='*80}")
    print(f"FFA EVALUATION (DUAL-DATASET MODE)")
    print(f"{'='*80}")
    print(f"Experiments Root: {experiments_root}")
    print(f"Eval Set (#F58220): {eval_set_path}")
    print(f"Test Set (#179C7D): {test_set_path}\n")
    
    # Create root evaluation directory
    eval_root = experiments_root / "evaluation"
    enum_cache_dir = eval_root / "enum_cache"
    
    if eval_root.exists():
        print(f"⚠️  Clearing existing evaluation: {eval_root}")
        import shutil
        try:
            shutil.rmtree(eval_root)
        except Exception as e:
            logger.error(f"Failed to clear: {e}")
            return
    
    eval_root.mkdir(parents=True, exist_ok=True)
    enum_cache_dir.mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # 1. DISCOVER ALL EXPERIMENT FOLDERS
    # ========================================================================
    
    experiments = {}
    for item in sorted(experiments_root.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        if item.name == "evaluation":
            continue
        experiments[item.name] = item
    
    if not experiments:
        logger.error("❌ No experiments found!")
        return
    
    print(f"✓ Found {len(experiments)} experiments: {', '.join(experiments.keys())}\n")
    
    # ========================================================================
    # 2. EVALUATE EACH EXPERIMENT AGAINST BOTH DATASETS
    # ========================================================================
    
    all_results = {
        "eval_set": {},
        "test_set": {},
        "generalization": {}
    }
    
    for exp_name, exp_dir in sorted(experiments.items()):
        print(f"{'─'*80}")
        print(f"Evaluating Experiment: {exp_name}")
        print(f"{'─'*80}")
        
        all_results["eval_set"][exp_name] = {}
        all_results["test_set"][exp_name] = {}
        
        # ====================================================================
        # 2a. EVALUATE AGAINST EVAL SET (#F58220)
        # ====================================================================
        
        print(f"\n  [1/2] EVAL SET (#F58220) - Evaluierungsdaten")
        print(f"  {'-'*76}")
        
        eval_results = evaluate_experiment_against_dataset(
            exp_name,
            exp_dir,
            eval_set_path,
            enum_cache_dir,
            color="#F58220"
        )
        all_results["eval_set"][exp_name] = eval_results
        
        # ====================================================================
        # 2b. EVALUATE AGAINST TEST SET (#179C7D)
        # ====================================================================
        
        print(f"\n  [2/2] TEST SET (#179C7D) - Testdaten")
        print(f"  {'-'*76}")
        
        test_results = evaluate_experiment_against_dataset(
            exp_name,
            exp_dir,
            test_set_path,
            enum_cache_dir,
            color="#179C7D"
        )
        all_results["test_set"][exp_name] = test_results
        
        # ====================================================================
        # 2c. COMPUTE GENERALIZATION ANALYSIS
        # ====================================================================
        
        gen_analysis = compute_generalization_analysis(
            eval_results,
            test_results,
            exp_name
        )
        all_results["generalization"][exp_name] = gen_analysis
        
        print(f"\n  [3/3] GENERALIZATION ANALYSIS")
        print(f"  {'-'*76}")
        print(f"  Eval Set Macro F1:  {eval_results.get('overall_macro_f1', 0):.3f}")
        print(f"  Test Set Macro F1:  {test_results.get('overall_macro_f1', 0):.3f}")
        print(f"  Overfitting Gap:    {gen_analysis.get('macro_f1_gap', 0):.3f}")
        print(f"  Agreement Rate:     {gen_analysis.get('agreement_rate', 0):.1f}%\n")
    
    # ========================================================================
    # 3. CREATE COMPARISON VISUALIZATIONS
    # ========================================================================
    
    print(f"\n{'='*80}")
    print(f"Creating Comparison Visualizations...")
    print(f"{'='*80}\n")
    
    create_dual_dataset_visualizations(
        eval_root,
        all_results,
        experiments
    )
    
    # ========================================================================
    # 4. FINAL REPORT
    # ========================================================================
    
    print(f"\n{'='*80}")
    print(f"EVALUATION COMPLETE")
    print(f"{'='*80}\n")
    
    print(f"📊 RESULTS OVERVIEW\n")
    
    for exp_name in sorted(all_results["eval_set"].keys()):
        eval_f1 = all_results["eval_set"][exp_name].get("overall_macro_f1", 0)
        test_f1 = all_results["test_set"][exp_name].get("overall_macro_f1", 0)
        gap = all_results["generalization"][exp_name].get("macro_f1_gap", 0)
        
        print(f"  {exp_name}:")
        print(f"    Eval Set (#F58220): {eval_f1:.3f}")
        print(f"    Test Set (#179C7D): {test_f1:.3f}")
        print(f"    Overfitting Gap:    {gap:+.3f}")
        print()
    
    print(f"📁 Results: {eval_root}\n")


# ============================================================================
# HELPER FUNCTIONS FOR DUAL-DATASET EVALUATION
# ============================================================================

def evaluate_experiment_against_dataset(
    exp_name: str,
    exp_dir: Path,
    ground_truth_root: Path,
    enum_cache_dir: Path,
    color: str = None
) -> Dict:
    """
    Evaluiert ein einzelnes Experiment gegen ein Ground Truth Dataset.
    """
    result = {
        "experiment": exp_name,
        "color": color,
        "assemblies": {},
        "overall_macro_f1": 0,
        "overall_macro_f1_std": 0,
        "num_assemblies": 0
    }
    
    # Find assemblies in experiment
    assemblies = [d for d in exp_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
    
    if not assemblies:
        logger.warning(f"  No assemblies found in {exp_name}")
        return result
    
    all_f1_scores = []
    asm_count = 0
    
    for asm_dir in sorted(assemblies):
        asm_name = asm_dir.name
        
        # Find FFA assessment files
        ffa_assessment_dir = asm_dir / "ffa_assessment"
        gt_file = ground_truth_root / f"{asm_name}_ffa_assessment_enum_gt.json"
        
        # Skip if GT doesn't exist (assembly not in this dataset)
        if not gt_file.exists():
            continue
        
        enum_file = None
        
        # Try to find prediction file
        if (ffa_assessment_dir / f"{asm_name}_ffa_assessment_enum.json").exists():
            enum_file = ffa_assessment_dir / f"{asm_name}_ffa_assessment_enum.json"
        elif (asm_dir / f"{asm_name}_ffa_assessment_enum.json").exists():
            enum_file = asm_dir / f"{asm_name}_ffa_assessment_enum.json"
        
        if not enum_file or not enum_file.exists():
            logger.warning(f"    ⚠️  No enum file found for {asm_name}")
            continue
        
        # Evaluate this assembly
        try:
            from evaluation.ffa_metrics import load_ffa_data, calculate_macro_metrics, calculate_per_class_metrics, calculate_confusion_matrix_data, extract_field_values
            
            predictions, ground_truth, step_names = load_ffa_data(enum_file, gt_file)
            
            eval_fields = [
                "nature_of_provision", "part_rigidity", "gripping_areas", "orientation_features", "surface_sensibility",
                "accuracy_of_target_position", "positioning_aids", "additional_orientation_by_rotation", "accessibility_to_joining_position",
                "positioning_motion", "positioning_tolerances", "stability_in_positioned_state", "feeding_of_joining_element", "fixing_of_mounted_part"
            ]
            
            asm_eval = {"assembly_name": asm_name, "fields": {}}
            f1_scores = []
            
            for field_name in eval_fields:
                y_pred, y_true = extract_field_values(predictions, ground_truth, field_name)
                
                if len(y_true) == 0 or len(y_pred) == 0:
                    continue
                
                metrics = calculate_macro_metrics(y_true, y_pred)
                per_class = calculate_per_class_metrics(y_true, y_pred)
                cm_data = calculate_confusion_matrix_data(y_true, y_pred)
                
                asm_eval["fields"][field_name] = {
                    "metrics": metrics,
                    "per_class": per_class,
                    "confusion_matrix": cm_data
                }
                
                f1_val = metrics.get("macro_f1", 0)
                f1_scores.append(f1_val)
            
            asm_eval["overall_macro_f1"] = np.mean(f1_scores) if f1_scores else 0
            result["assemblies"][asm_name] = asm_eval
            all_f1_scores.append(asm_eval["overall_macro_f1"])
            asm_count += 1
            
            print(f"    ✓ {asm_name}: {asm_eval['overall_macro_f1']:.3f}")
            
        except Exception as e:
            logger.warning(f"    ✗ Failed to evaluate {asm_name}: {e}")
    
    result["overall_macro_f1"] = np.mean(all_f1_scores) if all_f1_scores else 0
    result["overall_macro_f1_std"] = np.std(all_f1_scores) if all_f1_scores else 0
    result["num_assemblies"] = asm_count
    
    print(f"  Dataset: {asm_count} assemblies, Macro F1 = {result['overall_macro_f1']:.3f} ± {result['overall_macro_f1_std']:.3f}")
    
    return result


def compute_generalization_analysis(eval_results: Dict, test_results: Dict, exp_name: str) -> Dict:
    """
    Vergleicht Eval Set vs Test Set Performance.
    """
    analysis = {
        "experiment": exp_name,
        "eval_macro_f1": eval_results.get("overall_macro_f1", 0),
        "test_macro_f1": test_results.get("overall_macro_f1", 0),
        "macro_f1_gap": 0,
        "agreement_rate": 0,
        "overfitting": False,
        "assembly_analysis": {}
    }
    
    gap = analysis["eval_macro_f1"] - analysis["test_macro_f1"]
    analysis["macro_f1_gap"] = gap
    analysis["overfitting"] = gap > 0.05
    
    eval_asms = set(eval_results.get("assemblies", {}).keys())
    test_asms = set(test_results.get("assemblies", {}).keys())
    common_asms = eval_asms & test_asms
    
    if common_asms:
        agreements = []
        for asm_name in common_asms:
            eval_f1 = eval_results["assemblies"][asm_name].get("overall_macro_f1", 0)
            test_f1 = test_results["assemblies"][asm_name].get("overall_macro_f1", 0)
            agreement = 1 - abs(eval_f1 - test_f1)
            agreements.append(agreement)
            analysis["assembly_analysis"][asm_name] = {
                "eval_f1": eval_f1,
                "test_f1": test_f1,
                "agreement": agreement
            }
        
        analysis["agreement_rate"] = (np.mean(agreements) * 100) if agreements else 0
    
    return analysis


def create_dual_dataset_visualizations(eval_root: Path, all_results: Dict, experiments: Dict):
    """
    Erstellt Vergleichs-Visualisierungen zwischen Eval (#F58220) und Test (#179C7D) Set.
    """
    colors = {
        "eval": "#F58220",      # Orange
        "test": "#179C7D"       # Grün
    }
    
    eval_set_dir = eval_root / "eval_set"
    test_set_dir = eval_root / "test_set"
    comparison_dir = eval_root / "comparison"
    
    eval_set_dir.mkdir(parents=True, exist_ok=True)
    test_set_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"  Creating comparison visualizations...")
    
    # ========================================================================
    # 1. SAVE DETAILED JSON RESULTS
    # ========================================================================
    
    with open(eval_set_dir / "results.json", "w") as f:
        json.dump(all_results["eval_set"], f, indent=2, default=str)
    
    with open(test_set_dir / "results.json", "w") as f:
        json.dump(all_results["test_set"], f, indent=2, default=str)
    
    with open(comparison_dir / "generalization_analysis.json", "w") as f:
        json.dump(all_results["generalization"], f, indent=2, default=str)
    
    print(f"    ✓ Saved JSON results")
    
    # ========================================================================
    # 2. MACRO F1 COMPARISON CHART
    # ========================================================================
    
    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        experiments_list = sorted(all_results["eval_set"].keys())
        eval_f1_scores = [all_results["eval_set"][exp].get("overall_macro_f1", 0) for exp in experiments_list]
        test_f1_scores = [all_results["test_set"][exp].get("overall_macro_f1", 0) for exp in experiments_list]
        
        x = np.arange(len(experiments_list))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, eval_f1_scores, width, label="Eval Set (#F58220)", color=colors["eval"], alpha=0.8, edgecolor="black", linewidth=1.5)
        bars2 = ax.bar(x + width/2, test_f1_scores, width, label="Test Set (#179C7D)", color=colors["test"], alpha=0.8, edgecolor="black", linewidth=1.5)
        
        ax.set_xlabel("Experiments", fontsize=12, fontweight="bold")
        ax.set_ylabel("Macro F1 Score", fontsize=12, fontweight="bold")
        ax.set_title("FFA Evaluation: Eval Set vs Test Set Comparison", fontsize=14, fontweight="bold", pad=20)
        ax.set_xticks(x)
        ax.set_xticklabels(experiments_list, rotation=45, ha="right")
        ax.set_ylim([0, 1.0])
        ax.legend(fontsize=11, loc="upper left")
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        
        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.3f}',
                       ha='center', va='bottom', fontsize=9, fontweight="bold")
        
        plt.tight_layout()
        plt.savefig(comparison_dir / "01_macro_f1_comparison.png", dpi=150, bbox_inches="tight")
        plt.close()
        
        print(f"    ✓ Created: 01_macro_f1_comparison.png")
    except Exception as e:
        logger.warning(f"    ✗ Failed to create macro F1 comparison: {e}")
    
    # ========================================================================
    # 3. OVERFITTING GAP ANALYSIS
    # ========================================================================
    
    try:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        experiments_list = sorted(all_results["generalization"].keys())
        gaps = [all_results["generalization"][exp].get("macro_f1_gap", 0) for exp in experiments_list]
        
        colors_bars = ["#FF6B6B" if gap > 0.05 else "#4ECDC4" for gap in gaps]
        
        bars = ax.bar(range(len(experiments_list)), gaps, color=colors_bars, alpha=0.8, edgecolor="black", linewidth=1.5)
        
        ax.axhline(y=0.05, color="red", linestyle="--", linewidth=2, label="Overfitting Threshold (0.05)", alpha=0.7)
        ax.axhline(y=0, color="black", linestyle="-", linewidth=0.8)
        
        ax.set_xlabel("Experiments", fontsize=12, fontweight="bold")
        ax.set_ylabel("F1 Gap (Eval - Test)", fontsize=12, fontweight="bold")
        ax.set_title("Overfitting Gap Analysis: Eval Set vs Test Set", fontsize=14, fontweight="bold", pad=20)
        ax.set_xticks(range(len(experiments_list)))
        ax.set_xticklabels(experiments_list, rotation=45, ha="right")
        ax.legend(fontsize=11)
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        
        # Add value labels
        for i, (bar, gap) in enumerate(zip(bars, gaps)):
            ax.text(bar.get_x() + bar.get_width()/2., gap,
                   f'{gap:+.3f}',
                   ha='center', va='bottom' if gap > 0 else 'top', fontsize=9, fontweight="bold")
        
        plt.tight_layout()
        plt.savefig(comparison_dir / "02_overfitting_gap_analysis.png", dpi=150, bbox_inches="tight")
        plt.close()
        
        print(f"    ✓ Created: 02_overfitting_gap_analysis.png")
    except Exception as e:
        logger.warning(f"    ✗ Failed to create overfitting analysis: {e}")
    
    # ========================================================================
    # 4. DATASET SUMMARY HEATMAP
    # ========================================================================
    
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # Collect all assemblies and experiments
        all_exps = sorted(all_results["eval_set"].keys())
        all_asms_eval = set()
        all_asms_test = set()
        
        for exp in all_exps:
            all_asms_eval.update(all_results["eval_set"][exp].get("assemblies", {}).keys())
            all_asms_test.update(all_results["test_set"][exp].get("assemblies", {}).keys())
        
        all_asms = sorted(all_asms_eval | all_asms_test)
        
        # Create matrices
        eval_matrix = np.full((len(all_exps), len(all_asms)), np.nan)
        test_matrix = np.full((len(all_exps), len(all_asms)), np.nan)
        
        for i, exp in enumerate(all_exps):
            for j, asm in enumerate(all_asms):
                eval_f1 = all_results["eval_set"][exp].get("assemblies", {}).get(asm, {}).get("overall_macro_f1", np.nan)
                test_f1 = all_results["test_set"][exp].get("assemblies", {}).get(asm, {}).get("overall_macro_f1", np.nan)
                eval_matrix[i, j] = eval_f1
                test_matrix[i, j] = test_f1
        
        # Plot Eval Set Heatmap
        im1 = ax1.imshow(eval_matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax1.set_xticks(range(len(all_asms)))
        ax1.set_yticks(range(len(all_exps)))
        ax1.set_xticklabels(all_asms, rotation=45, ha="right", fontsize=9)
        ax1.set_yticklabels(all_exps, fontsize=10)
        ax1.set_title("Eval Set (#F58220) - Macro F1 per Assembly", fontsize=12, fontweight="bold", color=colors["eval"])
        ax1.set_ylabel("Experiments", fontsize=11)
        
        # Plot Test Set Heatmap
        im2 = ax2.imshow(test_matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax2.set_xticks(range(len(all_asms)))
        ax2.set_yticks(range(len(all_exps)))
        ax2.set_xticklabels(all_asms, rotation=45, ha="right", fontsize=9)
        ax2.set_yticklabels(all_exps, fontsize=10)
        ax2.set_title("Test Set (#179C7D) - Macro F1 per Assembly", fontsize=12, fontweight="bold", color=colors["test"])
        ax2.set_ylabel("Experiments", fontsize=11)
        
        # Colorbars
        plt.colorbar(im1, ax=ax1, label="Macro F1")
        plt.colorbar(im2, ax=ax2, label="Macro F1")
        
        plt.suptitle("Dataset Performance Heatmaps", fontsize=14, fontweight="bold", y=1.02)
        plt.tight_layout()
        plt.savefig(comparison_dir / "03_dataset_summary_heatmap.png", dpi=150, bbox_inches="tight")
        plt.close()
        
        print(f"    ✓ Created: 03_dataset_summary_heatmap.png")
    except Exception as e:
        logger.warning(f"    ✗ Failed to create heatmap: {e}")
    
    # ========================================================================
    # 5. EVAL SET DETAILED VISUALIZATIONS (PER EXPERIMENT & ASSEMBLY)
    # ========================================================================
    
    print(f"\n  Creating Eval Set (#F58220) detailed visualizations...")
    
    for exp_name, exp_data in all_results["eval_set"].items():
        exp_dir = eval_set_dir / exp_name
        exp_dir.mkdir(parents=True, exist_ok=True)
        
        for asm_name, asm_data in exp_data.get("assemblies", {}).items():
            asm_dir = exp_dir / asm_name
            asm_dir.mkdir(parents=True, exist_ok=True)
            
            # Save per-assembly metrics JSON
            metrics_file = asm_dir / "metrics.json"
            with open(metrics_file, 'w') as f:
                json.dump(asm_data, f, indent=2, default=str)
            
            # Create confusion matrices per field
            for field_name, field_data in asm_data.get("fields", {}).items():
                if "confusion_matrix" not in field_data:
                    continue
                
                try:
                    cm = field_data["confusion_matrix"]
                    fig, ax = plt.subplots(figsize=(8, 7))
                    
                    # Simple heatmap-style confusion matrix
                    im = ax.imshow(cm, cmap='Blues', aspect='auto')
                    ax.set_xlabel("Predicted", fontsize=11, fontweight="bold")
                    ax.set_ylabel("Actual", fontsize=11, fontweight="bold")
                    ax.set_title(f"{asm_name} - {field_name}\nConfusion Matrix (Eval Set)", fontsize=12, fontweight="bold", color=colors["eval"])
                    plt.colorbar(im, ax=ax, label="Count")
                    plt.tight_layout()
                    
                    cm_file = asm_dir / f"cm_{field_name}.png"
                    plt.savefig(cm_file, dpi=100, bbox_inches="tight")
                    plt.close()
                except Exception as e:
                    logger.warning(f"      Failed to create CM for {field_name}: {e}")
            
            # Create assembly summary (all fields F1 scores)
            try:
                fields_list = []
                f1_scores = []
                
                for field_name, field_data in asm_data.get("fields", {}).items():
                    if "metrics" in field_data:
                        f1 = field_data["metrics"].get("macro_f1", 0)
                        fields_list.append(field_name.replace("_", "\n"))
                        f1_scores.append(f1)
                
                if fields_list and f1_scores:
                    fig, ax = plt.subplots(figsize=(14, 6))
                    bars = ax.barh(range(len(fields_list)), f1_scores, color=colors["eval"], alpha=0.7, edgecolor="black")
                    ax.set_yticks(range(len(fields_list)))
                    ax.set_yticklabels(fields_list, fontsize=9)
                    ax.set_xlabel("Macro F1 Score", fontsize=11, fontweight="bold")
                    ax.set_title(f"{asm_name} - Field Performance (Eval Set)", fontsize=12, fontweight="bold", color=colors["eval"])
                    ax.set_xlim([0, 1.0])
                    ax.grid(axis="x", alpha=0.3, linestyle="--")
                    
                    # Add value labels
                    for i, (bar, score) in enumerate(zip(bars, f1_scores)):
                        ax.text(score, bar.get_y() + bar.get_height()/2., f'{score:.3f}',
                               va='center', ha='left', fontsize=9, fontweight="bold")
                    
                    plt.tight_layout()
                    summary_file = asm_dir / "summary.png"
                    plt.savefig(summary_file, dpi=100, bbox_inches="tight")
                    plt.close()
            except Exception as e:
                logger.warning(f"      Failed to create summary for {asm_name}: {e}")
    
    print(f"    ✓ Eval Set detailed visualizations created")
    
    # ========================================================================
    # 6. TEST SET DETAILED VISUALIZATIONS (PER EXPERIMENT & ASSEMBLY)
    # ========================================================================
    
    print(f"  Creating Test Set (#179C7D) detailed visualizations...")
    
    for exp_name, exp_data in all_results["test_set"].items():
        exp_dir = test_set_dir / exp_name
        exp_dir.mkdir(parents=True, exist_ok=True)
        
        for asm_name, asm_data in exp_data.get("assemblies", {}).items():
            asm_dir = exp_dir / asm_name
            asm_dir.mkdir(parents=True, exist_ok=True)
            
            # Save per-assembly metrics JSON
            metrics_file = asm_dir / "metrics.json"
            with open(metrics_file, 'w') as f:
                json.dump(asm_data, f, indent=2, default=str)
            
            # Create confusion matrices per field
            for field_name, field_data in asm_data.get("fields", {}).items():
                if "confusion_matrix" not in field_data:
                    continue
                
                try:
                    cm = field_data["confusion_matrix"]
                    fig, ax = plt.subplots(figsize=(8, 7))
                    
                    # Simple heatmap-style confusion matrix
                    im = ax.imshow(cm, cmap='Greens', aspect='auto')
                    ax.set_xlabel("Predicted", fontsize=11, fontweight="bold")
                    ax.set_ylabel("Actual", fontsize=11, fontweight="bold")
                    ax.set_title(f"{asm_name} - {field_name}\nConfusion Matrix (Test Set)", fontsize=12, fontweight="bold", color=colors["test"])
                    plt.colorbar(im, ax=ax, label="Count")
                    plt.tight_layout()
                    
                    cm_file = asm_dir / f"cm_{field_name}.png"
                    plt.savefig(cm_file, dpi=100, bbox_inches="tight")
                    plt.close()
                except Exception as e:
                    logger.warning(f"      Failed to create CM for {field_name}: {e}")
            
            # Create assembly summary (all fields F1 scores)
            try:
                fields_list = []
                f1_scores = []
                
                for field_name, field_data in asm_data.get("fields", {}).items():
                    if "metrics" in field_data:
                        f1 = field_data["metrics"].get("macro_f1", 0)
                        fields_list.append(field_name.replace("_", "\n"))
                        f1_scores.append(f1)
                
                if fields_list and f1_scores:
                    fig, ax = plt.subplots(figsize=(14, 6))
                    bars = ax.barh(range(len(fields_list)), f1_scores, color=colors["test"], alpha=0.7, edgecolor="black")
                    ax.set_yticks(range(len(fields_list)))
                    ax.set_yticklabels(fields_list, fontsize=9)
                    ax.set_xlabel("Macro F1 Score", fontsize=11, fontweight="bold")
                    ax.set_title(f"{asm_name} - Field Performance (Test Set)", fontsize=12, fontweight="bold", color=colors["test"])
                    ax.set_xlim([0, 1.0])
                    ax.grid(axis="x", alpha=0.3, linestyle="--")
                    
                    # Add value labels
                    for i, (bar, score) in enumerate(zip(bars, f1_scores)):
                        ax.text(score, bar.get_y() + bar.get_height()/2., f'{score:.3f}',
                               va='center', ha='left', fontsize=9, fontweight="bold")
                    
                    plt.tight_layout()
                    summary_file = asm_dir / "summary.png"
                    plt.savefig(summary_file, dpi=100, bbox_inches="tight")
                    plt.close()
            except Exception as e:
                logger.warning(f"      Failed to create summary for {asm_name}: {e}")
    
    print(f"    ✓ Test Set detailed visualizations created")
    print(f"  ✓ All comparison visualizations created!")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    experiments_root = Path("data/experiments/Final_Modelvariation")
    
    if not experiments_root.exists():
        logger.error("❌ data/experiments/ffa_experiments not found!")
        sys.exit(1)
    
    run_ffa_evaluation(experiments_root)

