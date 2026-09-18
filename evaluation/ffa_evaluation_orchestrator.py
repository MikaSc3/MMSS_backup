"""
FFA Evaluation Orchestrator

Orchestriert den kompletten Evaluations-Workflow für mehrere Experimente:
1. Auto-Discovery von allen Experimenten im Run-Ordner
2. Enum-Konvertierung (ffa_str_to_enum) für jedes Experiment
3. Detaillierte Evaluation (ffa_evaluation) pro Experiment
4. Cross-Experiment Comparison & Visualization
"""

import sys
from pathlib import Path

# Add parent directory to sys.path to allow absolute imports when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
import warnings

import matplotlib.pyplot as plt
import numpy as np

# Try relative imports first (when run as module), fall back to absolute imports
try:
    from .ffa_str_to_enum import convert_ffa_stripped_to_enum, create_ffa_enum_mapping
    from .ffa_evaluation import run_evaluation
except ImportError:
    from evaluation.ffa_str_to_enum import convert_ffa_stripped_to_enum, create_ffa_enum_mapping
    from evaluation.ffa_evaluation import run_evaluation

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')
warnings.filterwarnings('ignore')


# ============================================================================
# EXPERIMENT DISCOVERY
# ============================================================================

def discover_experiments_in_run(run_root: Path) -> Dict[str, Path]:
    """
    Findet alle Experiment-Ordner im Run-Verzeichnis.
    
    Args:
        run_root: z.B. data/experiments/run_2026-02-10_154526/
        
    Returns:
        Dict: {"exp1_baseline": Path(...), "exp2_other": Path(...), ...}
        
    Filtert automatisch 'evaluation' und andere nicht-Experiment-Ordner aus.
    """
    experiments = {}
    
    if not run_root.exists():
        logger.error(f"Run root not found: {run_root}")
        return experiments
    
    for item in sorted(run_root.iterdir()):
        if not item.is_dir():
            continue
        
        # Skip evaluation folders and other special folders
        if item.name in ['evaluation', 'logs', 'debug']:
            continue
        
        # Skip hidden/underscore folders
        if item.name.startswith('_'):
            continue
        
        # Check if this looks like an experiment (has subdirectories with assembly data)
        subdirs = [d for d in item.iterdir() if d.is_dir()]
        
        if subdirs:
            experiments[item.name] = item
            logger.info(f"Found experiment: {item.name} ({len(subdirs)} assemblies)")
    
    return experiments


# ============================================================================
# ENUM CONVERSION (ffa_str_to_enum integration)
# ============================================================================

def convert_experiment_to_enum(
    experiment_name: str,
    experiment_path: Path,
    eval_root: Path,
    ground_truth_root: Path = Path("data/ground_truth"),
) -> Path:
    """
    Konvertiert alle LLM-Predictions eines Experiments zu Enum-Form.
    
    Args:
        experiment_name: z.B. "exp1_baseline"
        experiment_path: Pfad zum Experiment-Ordner
        eval_root: evaluation/ Ordner im Run
        ground_truth_root: Pfad zu Ground-Truth Daten
        
    Returns:
        Path zum Experiment-Evaluation-Ordner
    """
    # Output direkt ins Experiment-Ordner
    enum_output_dir = eval_root / experiment_name
    enum_output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"ENUM CONVERSION: {experiment_name}")
    print(f"{'='*70}")
    print(f"Input: {experiment_path}")
    print(f"Output: {enum_output_dir}")
    
    # Create enum mapping once
    enum_mapping = create_ffa_enum_mapping()
    
    # Discover all assemblies in experiment
    assemblies = [
        d.name for d in experiment_path.iterdir()
        if d.is_dir() and not d.name.startswith('_')
    ]
    
    logger.info(f"Found {len(assemblies)} assemblies")
    
    converted_count = 0
    errors = []
    
    for assembly_name in sorted(assemblies):
        assembly_path = experiment_path / assembly_name
        
        # Look for ffa_assessment_stripped.json in ffa_assessment/ subdirectory
        stripped_file = assembly_path / "ffa_assessment" / "ffa_assessment_stripped.json"
        
        print(f"\n   Looking for: {assembly_name}")
        print(f"     Path: {stripped_file}")
        print(f"     Exists: {stripped_file.exists()}")
        
        if not stripped_file.exists():
            logger.warning(f"No stripped FFA file found: {stripped_file}")
            continue
        
        try:
            # Load stripped data
            with open(stripped_file, 'r', encoding='utf-8') as f:
                stripped_data = json.load(f)
            
            logger.info(f"  ✓ Loaded stripped data")
            
            # Convert to enum
            converted_data, conv_errors = convert_ffa_stripped_to_enum(
                stripped_data,
                enum_mapping,
                assembly_name
            )
            
            logger.info(f"  ✓ Converted to enum ({len(converted_data)} steps)")
            
            # Save enum version with correct name
            enum_file = enum_output_dir / f"{assembly_name}_ffa_assessment_enum.json"
            with open(enum_file, 'w', encoding='utf-8') as f:
                json.dump(converted_data, f, indent=2)
            
            logger.info(f"✓ {assembly_name}")
            logger.info(f"  Saved: {enum_file.name}")
            converted_count += 1
            errors.extend(conv_errors)
            
        except Exception as e:
            logger.error(f"✗ {assembly_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            errors.append(f"{assembly_name}: {e}")
    
    print(f"\n✓ Converted {converted_count}/{len(assemblies)} assemblies")
    
    if errors:
        print(f"\n⚠️  {len(errors)} errors encountered:")
        for err in errors[:5]:  # Show first 5
            print(f"  - {err}")
    
    return enum_output_dir


# ============================================================================
# EVALUATION (ffa_evaluation integration)
# ============================================================================

def evaluate_experiment(
    experiment_name: str,
    exp_eval_dir: Path,
    ground_truth_root: Path = Path("data/ground_truth"),
) -> Dict:
    """
    Führt detaillierte Evaluation für ein Experiment durch.
    
    Args:
        experiment_name: z.B. "exp1_baseline"
        exp_eval_dir: Pfad zum Experiment-Ordner
        ground_truth_root: Pfad zu Ground-Truth Daten
        
    Returns:
        Dict mit Summary-Daten
    """
    print(f"\n{'='*70}")
    print(f"COMPREHENSIVE EVALUATION: {experiment_name}")
    print(f"{'='*70}")
    print(f"Enum Files: {exp_eval_dir}")
    print(f"Ground Truth: {ground_truth_root}")
    
    # Save enum mapping (if not already there)
    enum_mapping = create_ffa_enum_mapping()
    enum_mapping_file = exp_eval_dir / "ffa_enum_mapping.json"
    if not enum_mapping_file.exists():
        with open(enum_mapping_file, 'w', encoding='utf-8') as f:
            json.dump(enum_mapping, f, indent=2)
        print(f"✓ Saved ffa_enum_mapping.json")
    
    # Run the comprehensive evaluation
    print(f"\nRunning comprehensive evaluation...")
    
    try:
        run_evaluation(exp_eval_dir)
        
        # Load summary
        metrics_file = exp_eval_dir / "evaluation_results" / "metrics" / "metrics_summary.json"
        
        if metrics_file.exists():
            with open(metrics_file, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            
            logger.info(f"✓ Evaluation complete")
            logger.info(f"  Overall Accuracy: {summary.get('overall_accuracy_weighted', 0):.1%}")
            logger.info(f"  Overall F1-Score: {summary.get('overall_f1_macro_weighted', 0):.3f}")
            
            return summary
        else:
            logger.warning(f"No summary found at {metrics_file}")
            return {"status": "no_metrics", "experiment_name": experiment_name}
    
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {"status": "error", "error": str(e), "experiment_name": experiment_name}


# ============================================================================
# CROSS-EXPERIMENT COMPARISON
# ============================================================================

def create_per_assembly_comparison_chart(
    eval_root: Path,
    comp_dir: Path,
) -> None:
    """
    Erstellt gruppierte Bar-Charts pro Assembly.
    """
    # Collect accuracy and F1 data from each experiment
    experiment_accuracies = {}
    experiment_f1_scores = {}
    all_assemblies = set()
    
    for exp_dir in sorted(eval_root.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name == "comprehensive_eval":
            continue
        
        # Load metrics_per_assembly.json
        metrics_file = exp_dir / "evaluation_results" / "metrics" / "metrics_per_assembly.json"
        
        if not metrics_file.exists():
            logger.warning(f"No metrics_per_assembly.json found in {exp_dir.name}")
            continue
        
        try:
            with open(metrics_file, 'r', encoding='utf-8') as f:
                metrics = json.load(f)
            
            exp_name = exp_dir.name
            experiment_accuracies[exp_name] = {}
            experiment_f1_scores[exp_name] = {}
            
            # Extract accuracy and F1 per assembly
            for asm_name, asm_metrics in metrics.items():
                accuracy = asm_metrics.get("overall_accuracy_mean", 0)
                f1_score = asm_metrics.get("overall_f1_macro_mean", 0)
                experiment_accuracies[exp_name][asm_name] = accuracy * 100
                experiment_f1_scores[exp_name][asm_name] = f1_score * 100
                all_assemblies.add(asm_name)
            
            logger.info(f"Loaded metrics for {exp_name}: {len(asm_metrics)} assemblies")
        
        except Exception as e:
            logger.error(f"Failed to load metrics for {exp_dir.name}: {e}")
    
    if not experiment_accuracies or not all_assemblies:
        logger.warning("No assembly accuracy data found for comparison")
        return
    
    # Prepare data for grouped bar chart
    assemblies = sorted(all_assemblies)
    experiments = sorted(experiment_accuracies.keys())
    
    print(f"\n  Assemblies: {len(assemblies)}")
    print(f"  Experiments: {len(experiments)}")
    
    # Custom color palette
    custom_colors = ['#F58220', '#179C7D', '#005B7F']
    colors = [custom_colors[i % len(custom_colors)] for i in range(len(experiments))]
    
    # ===== ACCURACY CHART =====
    fig, ax = plt.subplots(figsize=(16, 7))
    
    x = np.arange(len(assemblies))
    width = 0.8 / len(experiments)
    
    # Create bars for each experiment
    for idx, exp_name in enumerate(experiments):
        accuracies = [
            experiment_accuracies[exp_name].get(asm, 0)
            for asm in assemblies
        ]
        
        offset = width * (idx - len(experiments) / 2 + 0.5)
        bars = ax.bar(x + offset, accuracies, width, label=exp_name, 
                      color=colors[idx], edgecolor='black', linewidth=1.0)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.0f}%',
                        ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Customize chart
    ax.set_ylabel('Accuracy (%)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Assembly', fontsize=12, fontweight='bold')
    ax.set_title('FFA Evaluation: Per-Assembly Accuracy Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(assemblies, rotation=45, ha='right')
    ax.set_ylim(0, 105)
    ax.legend(loc='upper right', fontsize=10, framealpha=0.95)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    
    chart_file = comp_dir / "per_assembly_accuracy_comparison.png"
    plt.savefig(chart_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved: {chart_file}")
    print(f"✓ Per-assembly accuracy comparison chart saved")
    
    # ===== F1-SCORE CHART =====
    fig, ax = plt.subplots(figsize=(16, 7))
    
    x = np.arange(len(assemblies))
    width = 0.8 / len(experiments)
    
    # Create bars for each experiment
    for idx, exp_name in enumerate(experiments):
        f1_scores = [
            experiment_f1_scores[exp_name].get(asm, 0)
            for asm in assemblies
        ]
        
        offset = width * (idx - len(experiments) / 2 + 0.5)
        bars = ax.bar(x + offset, f1_scores, width, label=exp_name, 
                      color=colors[idx], edgecolor='black', linewidth=1.0)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.0f}%',
                        ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Customize chart
    ax.set_ylabel('F1-Score (%)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Assembly', fontsize=12, fontweight='bold')
    ax.set_title('FFA Evaluation: Per-Assembly F1-Score Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(assemblies, rotation=45, ha='right')
    ax.set_ylim(0, 105)
    ax.legend(loc='upper right', fontsize=10, framealpha=0.95)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    
    chart_file = comp_dir / "per_assembly_f1_comparison.png"
    plt.savefig(chart_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved: {chart_file}")
    print(f"✓ Per-assembly F1-score comparison chart saved")


def create_comparison_report(
    eval_root: Path,
    experiment_summaries: Dict[str, Dict],
) -> None:
    """
    Erstellt aggregierte Vergleiche zwischen Experimenten.
    """
    comp_dir = eval_root / "comprehensive_eval"
    comp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"COMPREHENSIVE COMPARISON")
    print(f"{'='*70}")
    
    # Prepare comparison data
    comparison_data = {
        "timestamp": datetime.now().isoformat(),
        "total_experiments": len(experiment_summaries),
        "experiments": {}
    }
    
    exp_names = []
    exp_accuracies = []
    exp_f1_scores = []
    
    for exp_name, summary in sorted(experiment_summaries.items()):
        # Extract accuracy from metrics_summary
        if isinstance(summary, dict) and "overall_accuracy_weighted" in summary:
            avg_acc = summary.get("overall_accuracy_weighted", 0)
        else:
            avg_acc = summary.get("average_accuracy", 0)
        
        # Extract F1 score
        avg_f1 = summary.get("overall_f1_macro_weighted", 0)
        
        comparison_data["experiments"][exp_name] = {
            "overall_accuracy": avg_acc,
            "overall_f1_score": avg_f1,
            "total_samples": summary.get("total_samples", 0),
            "fields_evaluated": summary.get("fields_evaluated", 0)
        }
        
        exp_names.append(exp_name)
        exp_accuracies.append(avg_acc * 100)
        exp_f1_scores.append(avg_f1)
        
        logger.info(f"{exp_name}: Accuracy={avg_acc:.1%}, F1={avg_f1:.3f}")
    
    # Save comparison JSON
    comp_json = comp_dir / "overall_accuracy_comparison.json"
    with open(comp_json, 'w', encoding='utf-8') as f:
        json.dump(comparison_data, f, indent=2)
    
    logger.info(f"Saved: {comp_json}")
    
    # Create overall accuracy bar chart
    if exp_names and exp_accuracies:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Use green color for overall accuracy
        colors = ['#179C7D'] * len(exp_names)
        bars = ax.bar(exp_names, exp_accuracies, color=colors, edgecolor='black', linewidth=1.5)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%',
                    ha='center', va='bottom', fontweight='bold')
        
        ax.set_ylabel('Overall Accuracy (%)', fontsize=12, fontweight='bold')
        ax.set_xlabel('Experiment', fontsize=12, fontweight='bold')
        ax.set_title('FFA Evaluation: Overall Experiment Comparison', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 105)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        
        chart_file = comp_dir / "overall_accuracy_comparison.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Saved: {chart_file}")
    
    # Create overall F1 bar chart
    if exp_names and exp_f1_scores:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Use orange color for overall F1
        colors = ['#F58220'] * len(exp_names)
        bars = ax.bar(exp_names, [f1 * 100 for f1 in exp_f1_scores], color=colors, edgecolor='black', linewidth=1.5)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%',
                    ha='center', va='bottom', fontweight='bold')
        
        ax.set_ylabel('F1-Score (%)', fontsize=12, fontweight='bold')
        ax.set_xlabel('Experiment', fontsize=12, fontweight='bold')
        ax.set_title('FFA Evaluation: Overall F1-Score Comparison', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 105)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        chart_file = comp_dir / "overall_f1_comparison.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Saved: {chart_file}")
    
    # Create per-assembly grouped bar chart
    print(f"\nGenerating per-assembly comparison chart...")
    create_per_assembly_comparison_chart(eval_root, comp_dir)
    
    print(f"\n✓ Comparison report created in {comp_dir}")


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def run_evaluation_orchestrator(run_root: Path) -> None:
    """
    Orchestriert den kompletten Evaluations-Workflow.
    """
    print(f"\n{'='*70}")
    print(f"FFA EVALUATION ORCHESTRATOR")
    print(f"{'='*70}")
    print(f"Run Root: {run_root}\n")
    
    # Create evaluation directory
    eval_root = run_root / "evaluation"
    
    # Clear existing evaluation folder if it exists
    if eval_root.exists():
        print(f"⚠️  Clearing existing evaluation folder: {eval_root}")
        import shutil
        try:
            shutil.rmtree(eval_root)
            print(f"✓ Removed old evaluation results")
        except Exception as e:
            logger.error(f"Failed to remove evaluation folder: {e}")
            return
    
    eval_root.mkdir(parents=True, exist_ok=True)
    
    ground_truth_root = Path("data/ground_truth/ffa_ground_truth")
    
    # Step 1: Discover experiments
    experiments = discover_experiments_in_run(run_root)
    
    if not experiments:
        logger.error("No experiments found!")
        return
    
    print(f"\nFound {len(experiments)} experiments\n")
    
    # Step 2: Convert each experiment to enum
    enum_dirs = {}
    for exp_name, exp_path in sorted(experiments.items()):
        exp_eval_dir = convert_experiment_to_enum(
            exp_name,
            exp_path,
            eval_root,
            ground_truth_root
        )
        enum_dirs[exp_name] = exp_eval_dir
    
    # Step 3: Evaluate each experiment
    experiment_summaries = {}
    for exp_name, exp_eval_dir in sorted(enum_dirs.items()):
        summary = evaluate_experiment(
            exp_name,
            exp_eval_dir,
            ground_truth_root
        )
        experiment_summaries[exp_name] = summary
    
    # Step 4: Create comprehensive comparison
    create_comparison_report(eval_root, experiment_summaries)
    
    print(f"\n{'='*70}")
    print(f"✅ EVALUATION COMPLETED")
    print(f"{'='*70}")
    print(f"Results: {eval_root}\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        run_root = Path(sys.argv[1])
    else:
        # Use latest run directory
        experiments_dir = Path("data/experiments")
        run_dirs = sorted([d for d in experiments_dir.iterdir() if d.is_dir() and d.name.startswith("run_")])
        
        if not run_dirs:
            print("❌ No run directories found!")
            sys.exit(1)
        
        run_root = run_dirs[-1]
        print(f"Using latest run: {run_root.name}")
    
    run_evaluation_orchestrator(run_root)
