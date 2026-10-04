"""
Generate comparison charts for comprehensive evaluation.

Standalone script to create per-assembly and overall accuracy comparison charts
after evaluation is complete.
"""

import json
import logging
from pathlib import Path
from typing import Dict
import matplotlib.pyplot as plt
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_comparison_charts(eval_root: Path) -> None:
    """
    Generates all comparison charts from existing evaluation results.
    
    Args:
        eval_root: Path to evaluation folder containing experiment results
    """
    eval_root = Path(eval_root)
    
    if not eval_root.exists():
        logger.error(f"Evaluation root not found: {eval_root}")
        return
    
    # Create comprehensive_eval directory
    comp_dir = eval_root / "comprehensive_eval"
    comp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"GENERATING COMPARISON CHARTS")
    print(f"{'='*70}")
    print(f"Evaluation root: {eval_root}")
    print(f"Output dir: {comp_dir}")
    
    # Collect accuracy data from each experiment
    experiment_accuracies = {}  # {exp_name: {assembly_name: accuracy}}
    all_assemblies = set()
    experiment_overall_accuracy = {}  # {exp_name: overall_accuracy}
    
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
            
            # Extract accuracy per assembly
            total_accuracy = 0
            count = 0
            
            for asm_name, asm_metrics in metrics.items():
                accuracy = asm_metrics.get("overall_accuracy_mean", 0)
                experiment_accuracies[exp_name][asm_name] = accuracy * 100  # Convert to percentage
                all_assemblies.add(asm_name)
                total_accuracy += accuracy
                count += 1
            
            # Calculate overall accuracy for this experiment
            if count > 0:
                experiment_overall_accuracy[exp_name] = (total_accuracy / count) * 100
            
            logger.info(f"Loaded metrics for {exp_name}: {count} assemblies, Overall Accuracy: {experiment_overall_accuracy[exp_name]:.1f}%")
        
        except Exception as e:
            logger.error(f"Failed to load metrics for {exp_dir.name}: {e}")
    
    if not experiment_accuracies or not all_assemblies:
        logger.warning("No assembly accuracy data found for comparison")
        return
    
    print(f"\nFound {len(experiment_accuracies)} experiments with {len(all_assemblies)} assemblies")
    
    # Generate per-assembly comparison chart
    create_per_assembly_comparison_chart(experiment_accuracies, all_assemblies, comp_dir)
    
    # Generate overall accuracy chart
    create_overall_accuracy_chart(experiment_overall_accuracy, comp_dir)
    
    print(f"\n{'='*70}")
    print(f"✓ Comparison charts generated successfully")
    print(f"{'='*70}\n")


def create_per_assembly_comparison_chart(
    experiment_accuracies: Dict[str, Dict[str, float]],
    all_assemblies: set,
    comp_dir: Path,
) -> None:
    """
    Erstellt gruppiertes Bar-Chart: Pro Assembly die Accuracies aller Experimente.
    """
    # Prepare data for grouped bar chart
    assemblies = sorted(all_assemblies)
    experiments = sorted(experiment_accuracies.keys())
    
    print(f"\n  Creating per-assembly comparison chart:")
    print(f"    Assemblies: {len(assemblies)}")
    print(f"    Experiments: {len(experiments)}")
    
    # Create grouped bar chart
    fig, ax = plt.subplots(figsize=(16, 7))
    
    x = np.arange(len(assemblies))
    width = 0.8 / len(experiments)  # Width of each bar
    colors = plt.cm.Set2(np.linspace(0, 1, len(experiments)))
    
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
    print(f"  ✓ Per-assembly comparison chart saved")


def create_overall_accuracy_chart(
    experiment_overall_accuracy: Dict[str, float],
    comp_dir: Path,
) -> None:
    """
    Erstellt Bar-Chart mit Overall Accuracy pro Experiment.
    """
    if not experiment_overall_accuracy:
        logger.warning("No overall accuracy data found")
        return
    
    print(f"\n  Creating overall accuracy comparison chart:")
    
    exp_names = list(experiment_overall_accuracy.keys())
    accuracies = list(experiment_overall_accuracy.values())
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    colors = plt.cm.viridis(np.linspace(0, 1, len(exp_names)))
    bars = ax.bar(exp_names, accuracies, color=colors, edgecolor='black', linewidth=1.5)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax.set_ylabel('Overall Accuracy (%)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Experiment', fontsize=12, fontweight='bold')
    ax.set_title('FFA Evaluation: Overall Accuracy Comparison', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 105)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    chart_file = comp_dir / "overall_accuracy_comparison.png"
    plt.savefig(chart_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved: {chart_file}")
    print(f"  ✓ Overall accuracy comparison chart saved")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        eval_root = sys.argv[1]
    else:
        # Default: look for latest evaluation run
        data_root = Path("data/experiments")
        runs = sorted(data_root.glob("run_*"), reverse=True)
        
        if runs:
            eval_root = runs[0] / "evaluation"
            print(f"Using latest run: {runs[0].name}")
        else:
            print("No evaluation runs found. Provide eval_root as argument.")
            sys.exit(1)
    
    generate_comparison_charts(eval_root)
