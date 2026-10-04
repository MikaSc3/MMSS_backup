"""
FFA Evaluation Visualizations

Erstellt Confusion Matrices, Metriken-Charts und Vergleiche.
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Tuple
from matplotlib.gridspec import GridSpec


def save_confusion_matrix(
    cm_data: Dict,
    output_path: Path,
    field_name: str,
    assembly_name: str
) -> None:
    """
    Speichert Confusion Matrix als PNG.
    
    Args:
        cm_data: Confusion Matrix Data von ffa_metrics
        output_path: Ziel-Datei
        field_name: Feldname
        assembly_name: Assembly-Name
    """
    cm = np.array(cm_data["confusion_matrix"])
    classes = cm_data["classes"]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Plot heatmap
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
                xticklabels=classes, yticklabels=classes,
                cbar_kws={'label': 'Count'})
    
    ax.set_xlabel('Predicted', fontsize=12, fontweight='bold')
    ax.set_ylabel('Actual', fontsize=12, fontweight='bold')
    ax.set_title(f'Confusion Matrix: {assembly_name} - {field_name}', 
                 fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_per_class_metrics_chart(
    per_class: Dict,
    output_path: Path,
    field_name: str,
    assembly_name: str
) -> None:
    """
    Speichert Per-Class Metriken als Chart.
    
    Args:
        per_class: Per-Class Metriken
        output_path: Ziel-Datei
        field_name: Feldname
        assembly_name: Assembly-Name
    """
    classes = sorted(per_class.keys())
    precisions = [per_class[c]["precision"] for c in classes]
    recalls = [per_class[c]["recall"] for c in classes]
    f1s = [per_class[c]["f1"] for c in classes]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(classes))
    width = 0.25
    
    ax.bar(x - width, precisions, width, label='Precision', color='#FF6B6B')
    ax.bar(x, recalls, width, label='Recall', color='#4ECDC4')
    ax.bar(x + width, f1s, width, label='F1-Score', color='#45B7D1')
    
    ax.set_xlabel('Class', fontsize=11, fontweight='bold')
    ax.set_ylabel('Score', fontsize=11, fontweight='bold')
    ax.set_title(f'Per-Class Metrics: {assembly_name} - {field_name}',
                 fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(classes)
    ax.set_ylim(0, 1.05)
    ax.legend(loc='lower right')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_assembly_summary_chart(
    assembly_eval: Dict,
    output_path: Path
) -> None:
    """
    Speichert Assembly-Zusammenfassung (alle Felder).
    
    Args:
        assembly_eval: Evaluation Result für eine Assembly
        output_path: Ziel-Datei
    """
    fields = []
    macro_f1s = []
    
    for field_name, field_data in assembly_eval["fields"].items():
        if "metrics" in field_data:
            fields.append(field_name.replace("_", "\n"))
            macro_f1s.append(field_data["metrics"]["macro_f1"])
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    colors = ['#2ecc71' if f > 0.7 else '#f39c12' if f > 0.5 else '#e74c3c' 
              for f in macro_f1s]
    bars = ax.bar(fields, macro_f1s, color=colors, edgecolor='black', linewidth=1)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_ylabel('Macro F1-Score', fontsize=12, fontweight='bold')
    ax.set_title(f'Assembly Summary: {assembly_eval["assembly_name"]}',
                 fontsize=14, fontweight='bold')
    ax.set_ylim(0, 1.1)
    ax.grid(axis='y', alpha=0.3)
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_class_distribution_heatmap(
    class_distributions: Dict[str, Dict],
    output_path: Path,
    assembly_name: str
) -> None:
    """
    Speichert Klassen-Verteilungs-Heatmap (zeigt Imbalance).
    
    Args:
        class_distributions: Dict von create_class_distribution_analysis()
        output_path: Ziel-Datei
        assembly_name: Assembly-Name
    """
    fields = list(class_distributions.keys())
    
    # Get all classes across all fields
    all_classes = set()
    for dist in class_distributions.values():
        all_classes.update(dist["class_distribution"].keys())
    
    all_classes = sorted(list(all_classes))
    
    # Build matrix
    data = []
    for field in fields:
        row = []
        for cls in all_classes:
            count = class_distributions[field]["class_distribution"].get(cls, 0)
            row.append(count)
        data.append(row)
    
    data = np.array(data)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    sns.heatmap(data, annot=True, fmt='d', cmap='YlOrRd', ax=ax,
                xticklabels=[f'Class {c}' for c in all_classes],
                yticklabels=[f.replace("_", " ") for f in fields],
                cbar_kws={'label': 'Sample Count'})
    
    ax.set_title(f'Class Distribution Heatmap: {assembly_name}',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Class', fontsize=12, fontweight='bold')
    ax.set_ylabel('Field', fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_macro_comparison_chart(
    experiments_results: Dict[str, Dict],
    output_path: Path,
    metric_type: str = "macro_f1"
) -> None:
    """
    Vergleicht Macro-F1 Scores über alle Experimente.
    
    Args:
        experiments_results: Dict von Experiment Results
        output_path: Ziel-Datei
        metric_type: "macro_f1" oder "micro_accuracy"
    """
    exp_names = list(experiments_results.keys())
    values = [experiments_results[e]["overall_macro_f1"] for e in exp_names]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6']
    bar_colors = [colors[i % len(colors)] for i in range(len(exp_names))]
    
    bars = ax.bar(exp_names, values, color=bar_colors, edgecolor='black', linewidth=1.5)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    ax.set_ylabel('Macro F1-Score', fontsize=12, fontweight='bold')
    ax.set_xlabel('Experiment', fontsize=12, fontweight='bold')
    ax.set_title('Macro F1-Score Comparison Across Experiments',
                 fontsize=14, fontweight='bold')
    ax.set_ylim(0, 1.1)
    ax.grid(axis='y', alpha=0.3)
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_assembly_ranking_chart(
    experiments_results: Dict[str, Dict],
    output_path: Path
) -> None:
    """
    Speichert Assembly-Ranking Chart für beste/schlechteste Assemblies.
    
    Args:
        experiments_results: Dict von Experiment Results
        output_path: Ziel-Datei
    """
    # Collect all assemblies and their scores
    assembly_scores = {}
    for exp_name, exp_data in experiments_results.items():
        for asm_name, asm_data in exp_data["assemblies"].items():
            if asm_name not in assembly_scores:
                assembly_scores[asm_name] = []
            f1 = asm_data.get("overall_macro_f1", 0)
            assembly_scores[asm_name].append(f1)
    
    # Calculate average per assembly
    avg_scores = {asm: np.mean(scores) for asm, scores in assembly_scores.items()}
    
    # Sort
    sorted_asms = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)
    asms = [a[0] for a in sorted_asms]
    scores = [a[1] for a in sorted_asms]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Color gradient: green (high) to red (low)
    colors = plt.cm.RdYlGn(np.linspace(0, 1, len(asms)))
    
    bars = ax.barh(asms, scores, color=colors, edgecolor='black', linewidth=1)
    
    # Add value labels
    for i, (bar, score) in enumerate(zip(bars, scores)):
        ax.text(score + 0.01, bar.get_y() + bar.get_height()/2,
                f'{score:.3f}', va='center', fontsize=10, fontweight='bold')
    
    ax.set_xlabel('Average Macro F1-Score', fontsize=12, fontweight='bold')
    ax.set_title('Assembly Ranking (Best to Worst)',
                 fontsize=14, fontweight='bold')
    ax.set_xlim(0, 1.15)
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def save_step_overview_chart(
    assembly_eval: Dict,
    output_path: Path
) -> None:
    """
    Speichert Übersicht der Step-Leistung.
    
    Args:
        assembly_eval: Assembly Evaluation
        output_path: Ziel-Datei
    """
    # For each step, calculate average performance across fields
    step_names = assembly_eval.get("step_names", [])
    num_steps = len(step_names)
    
    if num_steps == 0:
        return
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.text(0.5, 0.5, f'{assembly_eval["assembly_name"]}\n{num_steps} Steps',
            ha='center', va='center', fontsize=16, fontweight='bold',
            transform=ax.transAxes)
    
    ax.set_title(f'Step Overview: {assembly_eval["assembly_name"]}',
                 fontsize=14, fontweight='bold')
    ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
