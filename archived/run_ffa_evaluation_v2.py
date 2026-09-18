"""
Run FFA Evaluation for Dual-Dataset Mode (Eval Set vs Test Set)

Evaluates all experiments against TWO datasets:
- Eval Set (#F58220): ffa_ground_truth_evaluierungsdaten
- Test Set (#179C7D): ffa_ground_truth_testdaten

Output Structure:
    data/experiments/ffa_experiments/evaluation/
    ├── eval_set/results.json
    ├── test_set/results.json
    ├── comparison/generalization_analysis.json
    └── [detailed per-assembly visualizations]

Usage:
    python run_ffa_evaluation_v2.py
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Load enum mapping globally
ENUM_MAPPING_FILE = Path("data/ground_truth/ffa_ground_truth_evaluierungsdaten/ffa_enum_mapping.json")
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
# DUAL-DATASET EVALUATION ORCHESTRATOR
# ============================================================================

def evaluate_experiment_against_dataset(
    exp_name: str,
    exp_dir: Path,
    ground_truth_root: Path,
    enum_cache_dir: Path,
    color: str = None
) -> Dict:
    """
    Evaluiert ein Experiment gegen ein Ground Truth Dataset.
    
    Args:
        exp_name: Experiment name
        exp_dir: Path zu experiment folder
        ground_truth_root: Path zu GT dataset (eval oder test)
        enum_cache_dir: Cache directory für enum conversions
        color: Hex color für dieses Dataset (optional)
    
    Returns:
        Dictionary mit Evaluierungs-Ergebnissen
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
    
    print(f"  Dataset result: {asm_count} assemblies, Macro F1 = {result['overall_macro_f1']:.3f} ± {result['overall_macro_f1_std']:.3f}")
    
    return result


def compute_generalization_analysis(eval_results: Dict, test_results: Dict, exp_name: str) -> Dict:
    """
    Vergleicht Eval Set vs Test Set Performance.
    Detektiert Overfitting und Assembly-spezifische Probleme.
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
    
    # Macro F1 Gap
    gap = analysis["eval_macro_f1"] - analysis["test_macro_f1"]
    analysis["macro_f1_gap"] = gap
    analysis["overfitting"] = gap > 0.05
    
    # Agreement rate (Assemblies present in both)
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
    Erstellt Output-Struktur für beide Datasets.
    """
    eval_set_dir = eval_root / "eval_set"
    test_set_dir = eval_root / "test_set"
    comparison_dir = eval_root / "comparison"
    
    eval_set_dir.mkdir(parents=True, exist_ok=True)
    test_set_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    
    # Save detailed results
    with open(eval_set_dir / "results.json", "w") as f:
        json.dump(all_results["eval_set"], f, indent=2, default=str)
    
    with open(test_set_dir / "results.json", "w") as f:
        json.dump(all_results["test_set"], f, indent=2, default=str)
    
    with open(comparison_dir / "generalization_analysis.json", "w") as f:
        json.dump(all_results["generalization"], f, indent=2, default=str)
    
    print(f"  ✓ Saved detailed results to eval_set/, test_set/, comparison/")


def run_ffa_evaluation_dual_dataset(
    experiments_root: Path,
    eval_set_path: Path = None,
    test_set_path: Path = None
) -> None:
    """
    Evaluiert alle Experiments gegen beide GT-Datasets (Eval + Test).
    """
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
    
    # Create evaluation root
    eval_root = experiments_root / "evaluation"
    enum_cache_dir = eval_root / "enum_cache"
    
    if eval_root.exists():
        print(f"⚠️  Clearing existing evaluation...")
        import shutil
        try:
            shutil.rmtree(eval_root)
        except Exception as e:
            logger.error(f"Failed to clear: {e}")
            return
    
    eval_root.mkdir(parents=True, exist_ok=True)
    enum_cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Discover experiments
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
    
    print(f"✓ Found {len(experiments)} experiments\n")
    
    # Main evaluation loop
    all_results = {
        "eval_set": {},
        "test_set": {},
        "generalization": {}
    }
    
    for exp_name, exp_dir in sorted(experiments.items()):
        print(f"{'─'*80}")
        print(f"Evaluating: {exp_name}")
        print(f"{'─'*80}\n")
        
        # Evaluate against eval set
        print(f"  [1/2] EVAL SET (#F58220)")
        eval_results = evaluate_experiment_against_dataset(
            exp_name, exp_dir, eval_set_path, enum_cache_dir, color="#F58220"
        )
        all_results["eval_set"][exp_name] = eval_results
        
        # Evaluate against test set
        print(f"\n  [2/2] TEST SET (#179C7D)")
        test_results = evaluate_experiment_against_dataset(
            exp_name, exp_dir, test_set_path, enum_cache_dir, color="#179C7D"
        )
        all_results["test_set"][exp_name] = test_results
        
        # Generalization analysis
        print(f"\n  [3/3] GENERALIZATION ANALYSIS")
        gen_analysis = compute_generalization_analysis(eval_results, test_results, exp_name)
        all_results["generalization"][exp_name] = gen_analysis
        
        print(f"  Eval Set Macro F1:  {eval_results.get('overall_macro_f1', 0):.3f}")
        print(f"  Test Set Macro F1:  {test_results.get('overall_macro_f1', 0):.3f}")
        print(f"  Overfitting Gap:    {gen_analysis.get('macro_f1_gap', 0):+.3f}")
        print(f"  Agreement Rate:     {gen_analysis.get('agreement_rate', 0):.1f}%\n")
    
    # Create visualizations
    print(f"{'─'*80}")
    print(f"Creating Visualizations...")
    print(f"{'─'*80}\n")
    
    create_dual_dataset_visualizations(eval_root, all_results, experiments)
    
    # Final report
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
# CLI
# ============================================================================

if __name__ == "__main__":
    experiments_root = Path("data/experiments/ffa_experiments")
    
    if not experiments_root.exists():
        logger.error("❌ data/experiments/ffa_experiments not found!")
        sys.exit(1)
    
    run_ffa_evaluation_dual_dataset(experiments_root)
