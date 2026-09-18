"""
FFA Plots – All Visualizations per Evaluation Specification

§9.1 Within-experiment plots (per experiment × dataset):
  A) Total FFA MAE bar
  B) Category-level MAE grouped bar
  C) Macro F1 per category grouped bar
  D) Confusion matrices (heatmaps, viridis)
  E) Assembly-level scatter (pred vs GT)

§9.2 Cross-experiment plots:
  A) Total FFA MAE line plot
  B) Macro F1 line plot
  C) Category heatmap (Experiment × Category)
  D) Per-assembly variation: SD strip plot + sorted SD bar (new)

Colors:
  Eval Set  → #F58220
  Test Set  → #179C7D
  Colormap  → viridis (all confusion matrices and heatmaps)
"""

from __future__ import annotations

import logging
import math
import re
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")   # headless rendering
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.colors as mcolors
import numpy as np

from evaluation.ffa_evaluator import display_assembly_name
from evaluation.ffa_scoring import load_scoring_mapping

logger = logging.getLogger(__name__)

# Custom color scheme
# Red (bad) → Yellow (medium) → Green (good)
_CMAP_PERFORMANCE = mcolors.LinearSegmentedColormap.from_list(
    "performance",
    ["#F58220", "#FDB913", "#179C7D"]  # Red, Yellow, Green
)

# Reversed for MAE (high error → low error)
_CMAP_PERFORMANCE_REV = mcolors.LinearSegmentedColormap.from_list(
    "performance_rev",
    ["#179C7D", "#FDB913", "#F58220"]  # Green, Yellow, Red (reversed)
)

# White to Green for confusion matrices (low count → high count)
_CMAP_WHITE_GREEN = mcolors.LinearSegmentedColormap.from_list(
    "white_green",
    ["#FFFFFF", "#179C7D"]  # White to Green (#179C7D)
)

# Experiment colors for cross-experiment FFA comparison
_EXPERIMENT_COLORS = [
    "#3A6779",  # Exp 1: Dark teal
    "#008598",  # Exp 2: Medium teal
    "#B2D235",  # Exp 3: Yellow-green
    "#39C1CD",  # Exp 4: Cyan
    "#595959",  # Exp 5: Gray
]
_COLOR_GT = "#179C7D"  # Ground Truth: Green
_COLOR_GT_RECT = "#FF9500"  # Ground Truth Rectangle: Orange

# Load mapping once at module level
_MAPPING_CACHE = None

def _get_mapping():
    """Lazy-load the FFA scoring mapping."""
    global _MAPPING_CACHE
    if _MAPPING_CACHE is None:
        _MAPPING_CACHE = load_scoring_mapping()
    return _MAPPING_CACHE

def _get_field_option_ids(field_name: str) -> List[int]:
    """Get all available option IDs for a field from the mapping file."""
    mapping = _get_mapping()
    # Search all subprocesses for the field
    for subprocess in ["separation", "handling", "positioning", "joining"]:
        if subprocess in mapping and field_name in mapping[subprocess]:
            options = mapping[subprocess][field_name].get("options", {})
            # Convert option keys to integers and sort
            return sorted([int(k) for k in options.keys()])
    logger.warning(f"Field '{field_name}' not found in mapping")
    return []

# Brand colors
COLOR_EVAL = "#F58220"
COLOR_TEST = "#179C7D"
CATEGORY_COLORS = {
    "separation":  "#4C72B0",
    "handling":    "#DD8452",
    "positioning": "#55A868",
    "joining":     "#C44E52",
}
SUBPROCESSES = ["separation", "handling", "positioning", "joining"]
CMAP = "viridis"


def _savefig(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"  Saved: {path.name}")


# ============================================================================
# §9.1-A  Total FFA MAE – single bar per dataset
# ============================================================================

def plot_total_ffa_mae_bar(
    metrics_by_dataset: Dict[str, Dict],   # {"Eval Set": metrics, "Test Set": metrics}
    experiment_name: str,
    output_dir: Path,
) -> Path:
    """Bar: x=dataset, y=MAE(total_ffa)."""
    labels, values, colors = [], [], []
    for ds_label, m in metrics_by_dataset.items():
        mae = m.get("summary", {}).get("total_ffa_mae")
        if mae is None:
            continue
        labels.append(ds_label)
        values.append(mae)
        colors.append(COLOR_EVAL if "eval" in ds_label.lower() else COLOR_TEST)

    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.8, width=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                f"{val:.3f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_ylim(0, max(values) * 1.3 + 0.02)
    ax.set_ylabel("MAE (Total FFA)", fontsize=12)
    ax.set_title(f"Total FFA MAE\n{experiment_name}", fontsize=12, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "A_total_ffa_mae.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.1-B  Category-Level MAE – grouped bar
# ============================================================================

def plot_category_mae(
    metrics_by_dataset: Dict[str, Dict],
    experiment_name: str,
    output_dir: Path,
) -> Path:
    """Grouped bar: x=category, bars=datasets."""
    ds_labels = list(metrics_by_dataset.keys())
    ds_colors = [COLOR_EVAL if "eval" in d.lower() else COLOR_TEST for d in ds_labels]

    x = np.arange(len(SUBPROCESSES))
    width = 0.35 if len(ds_labels) == 2 else 0.6 / len(ds_labels)

    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (ds_label, color) in enumerate(zip(ds_labels, ds_colors)):
        values = []
        for sp in SUBPROCESSES:
            mae = metrics_by_dataset[ds_label].get("regression", {}).get(sp, {}).get("mae")
            values.append(mae if mae is not None else 0.0)
        offset = (i - (len(ds_labels) - 1) / 2) * width
        bars = ax.bar(x + offset, values, width, label=ds_label, color=color,
                      edgecolor="black", linewidth=0.6)
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                        f"{val:.3f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels([s.capitalize() for s in SUBPROCESSES], fontsize=11)
    ax.set_ylabel("MAE (FFA value)", fontsize=11)
    ax.set_title(f"Category-Level MAE\n{experiment_name}", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "B_category_mae.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.1-C  Macro F1 per Category – grouped bar
# ============================================================================

def plot_category_macro_f1(
    metrics_by_dataset: Dict[str, Dict],
    experiment_name: str,
    output_dir: Path,
) -> Path:
    """Grouped bar: x=category, bars=datasets (Macro F1)."""
    ds_labels = list(metrics_by_dataset.keys())
    ds_colors = [COLOR_EVAL if "eval" in d.lower() else COLOR_TEST for d in ds_labels]

    x = np.arange(len(SUBPROCESSES))
    width = 0.35 if len(ds_labels) == 2 else 0.6 / len(ds_labels)

    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (ds_label, color) in enumerate(zip(ds_labels, ds_colors)):
        values = []
        for sp in SUBPROCESSES:
            f1 = metrics_by_dataset[ds_label].get("classification", {}).get(sp, {}).get("macro_f1")
            values.append(f1 if f1 is not None else 0.0)
        offset = (i - (len(ds_labels) - 1) / 2) * width
        bars = ax.bar(x + offset, values, width, label=ds_label, color=color,
                      edgecolor="black", linewidth=0.6)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels([s.capitalize() for s in SUBPROCESSES], fontsize=11)
    ax.set_ylabel("Macro F1", fontsize=11)
    ax.set_ylim(0, 1.15)
    ax.axhline(1.0, color="gray", linewidth=0.7, linestyle="--")
    ax.set_title(f"Category Macro F1\n{experiment_name}", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "C_category_macro_f1.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.1-D  Confusion Matrices
# ============================================================================

def plot_confusion_matrices(
    metrics_by_dataset: Dict[str, Dict],
    experiment_name: str,
    output_dir: Path,
    mapping: Optional[Dict] = None,
) -> List[Path]:
    """One heatmap per category × dataset."""
    saved = []

    for sp in SUBPROCESSES:
        n_ds = len(metrics_by_dataset)
        fig, axes = plt.subplots(1, n_ds, figsize=(6 * n_ds, 5), squeeze=False)

        for ax_idx, (ds_label, m) in enumerate(metrics_by_dataset.items()):
            ax = axes[0][ax_idx]
            clf = m.get("classification", {}).get(sp, {})
            cm = clf.get("confusion_matrix")
            labels = clf.get("labels", [])

            if not cm or not labels:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{sp.capitalize()} – {ds_label}")
                continue

            cm_arr = np.array(cm)
            im = ax.imshow(cm_arr, cmap=_CMAP_WHITE_GREEN, aspect="auto")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

            ax.set_xticks(range(len(labels)))
            ax.set_yticks(range(len(labels)))
            ax.set_xticklabels([f"Pred:{l}" for l in labels], rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels([f"GT:{l}" for l in labels], fontsize=8)

            # Annotate cells
            for i in range(cm_arr.shape[0]):
                for j in range(cm_arr.shape[1]):
                    bg = cm_arr[i, j] / (cm_arr.max() + 1e-9)
                    txt_color = "white" if bg > 0.5 else "black"
                    ax.text(j, i, str(cm_arr[i, j]), ha="center", va="center",
                            color=txt_color, fontsize=9, fontweight="bold")

            f1 = clf.get("macro_f1", float("nan"))
            ax.set_title(f"{sp.capitalize()} | {ds_label}\nMacro F1: {f1:.3f}", fontsize=10)
            ax.set_xlabel("Predicted")
            ax.set_ylabel("Ground Truth")

        fig.suptitle(f"Confusion Matrices – {experiment_name}", fontsize=12, fontweight="bold")
        fig.tight_layout()

        path = output_dir / f"D_confusion_{sp}.png"
        _savefig(fig, path)
        saved.append(path)

    return saved


# ============================================================================
# §9.1-D+ Detailed Confusion Matrices per Category (from CriterionRecords)
# ============================================================================

def plot_detailed_confusion_matrices(
    records_by_dataset: Dict[str, List],  # {ds_label: [CriterionRecord, ...]}
    experiment_name: str,
    output_dir: Path,
) -> List[Path]:
    """
    Large, dedicated confusion matrices per category × dataset.
    Aggregates all fields within a category for clearer visualization.
    """
    from evaluation.ffa_evaluator import FIELD_TO_SUBPROCESS
    from sklearn.metrics import confusion_matrix
    
    saved = []
    
    for sp in SUBPROCESSES:
        # Get all fields for this subprocess
        fields_in_sp = [f for f, (sp_key, _) in FIELD_TO_SUBPROCESS.items() if sp_key == sp]
        
        if not fields_in_sp:
            continue
        
        n_ds = len(records_by_dataset)
        fig, axes = plt.subplots(1, n_ds, figsize=(8 * n_ds, 7), squeeze=False)
        
        for ax_idx, (ds_label, records) in enumerate(records_by_dataset.items()):
            ax = axes[0][ax_idx]
            
            if not records:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{sp.capitalize()} – {ds_label}")
                continue
            
            # Filter records for this subprocess
            sp_records = [r for r in records if r.category == sp]
            
            if not sp_records:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{sp.capitalize()} – {ds_label}")
                continue
            
            # Pair up GT and Pred IDs - only use records where both exist
            paired_records = [(r.gt_option_id, r.pred_option_id) for r in sp_records 
                              if r.gt_option_id is not None and r.pred_option_id is not None]
            
            if not paired_records:
                ax.text(0.5, 0.5, "No predictions", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{sp.capitalize()} – {ds_label}")
                continue
            
            gt_ids = [pair[0] for pair in paired_records]
            pred_ids = [pair[1] for pair in paired_records]
            
            # Get all available option IDs for all fields in this subprocess from the mapping
            all_labels_set = set()
            for field in fields_in_sp:
                all_labels_set.update(_get_field_option_ids(field))
            all_labels = sorted(all_labels_set) if all_labels_set else sorted(set(gt_ids))
            
            # Compute confusion matrix
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='A single label was found')
                cm = confusion_matrix(gt_ids, pred_ids, labels=all_labels)
            cm_arr = np.array(cm)
            
            # Plot heatmap
            im = ax.imshow(cm_arr, cmap=_CMAP_WHITE_GREEN, aspect="auto")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            
            ax.set_xticks(range(len(all_labels)))
            ax.set_yticks(range(len(all_labels)))
            ax.set_xticklabels([f"P:{l}" for l in all_labels], rotation=45, ha="right", fontsize=9)
            ax.set_yticklabels([f"GT:{l}" for l in all_labels], fontsize=9)
            
            # Annotate cells
            for i in range(cm_arr.shape[0]):
                for j in range(cm_arr.shape[1]):
                    bg = cm_arr[i, j] / (cm_arr.max() + 1e-9)
                    txt_color = "white" if bg > 0.5 else "black"
                    ax.text(j, i, str(cm_arr[i, j]), ha="center", va="center",
                            color=txt_color, fontsize=9, fontweight="bold")
            
            # Compute macro F1 for this category
            from sklearn.metrics import f1_score
            macro_f1 = f1_score(gt_ids, pred_ids, average="macro", labels=all_labels, zero_division=0)
            
            ax.set_title(f"{sp.capitalize()} | {ds_label}\nMacro F1: {macro_f1:.3f}", fontsize=11)
            ax.set_xlabel("Predicted Option ID", fontsize=10)
            ax.set_ylabel("Ground Truth Option ID", fontsize=10)
        
        fig.suptitle(f"Detailed Confusion Matrix – {sp.capitalize()} – {experiment_name}", 
                     fontsize=12, fontweight="bold")
        fig.tight_layout()
        
        path = output_dir / f"D+_detailed_confusion_{sp}.png"
        _savefig(fig, path)
        saved.append(path)
        logger.info(f"      Saved: {path.name}")
    
    return saved


# ============================================================================
# §9.1-D++ Field-Level Confusion Matrices (Per Individual Field)
# ============================================================================

def plot_field_level_confusion_matrices(
    records_by_dataset: Dict[str, List],  # {ds_label: [CriterionRecord, ...]}
    experiment_name: str,
    output_dir: Path,
) -> List[Path]:
    """
    Individual confusion matrix for each of the 14 FFA fields.
    Shows eval and test set side-by-side. Plots numbered 01–14 in order.
    Saves to <output_dir>/confusion_matrices/
    """
    from evaluation.ffa_evaluator import FIELD_TO_SUBPROCESS
    from sklearn.metrics import confusion_matrix, f1_score
    
    # Define fields in order with German labels
    FIELD_LABELS = [
        ("nature_of_provision",                  "01 Bereitstellungsart der Fügeteile"),
        ("part_rigidity",                        "02 Steifigkeit"),
        ("gripping_areas",                       "03 Greifflächen"),
        ("orientation_features",                 "04 Orientierungsmerkmale"),
        ("surface_sensibility",                  "05 Oberflächenempfindlichkeit"),
        ("accuracy_of_target_position",          "06 Genauigkeit Zielposition"),
        ("positioning_aids",                     "07 Positionierhilfen an den Bauteilen"),
        ("additional_orientation_by_rotation",   "08 Zusätzliche Orientierung durch Rotation"),
        ("accessibility_to_joining_position",    "09 Zugänglichkeit zur Fügestelle"),
        ("positioning_motion",                   "10 Fügebewegung"),
        ("positioning_tolerances",               "11 Fügetoleranzen"),
        ("stability_in_positioned_state",        "12 Haltestabilität im positionierten Zustand"),
        ("feeding_of_joining_element",           "13 Zuführung des Verbindungselements"),
        ("fixing_of_mounted_part",               "14 Befestigung des Fügeteils"),
    ]
    
    output_subdir = output_dir / "confusion_matrices"
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    saved = []
    
    for field_name, field_label in FIELD_LABELS:
        n_ds = len(records_by_dataset)
        fig, axes = plt.subplots(1, n_ds, figsize=(8 * n_ds, 7), squeeze=False)
        
        for ax_idx, (ds_label, records) in enumerate(records_by_dataset.items()):
            ax = axes[0][ax_idx]
            
            if not records:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{field_label} – {ds_label}")
                continue
            
            # Filter records for this field
            field_records = [r for r in records if r.field_name == field_name]
            
            if not field_records:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{field_label} – {ds_label}")
                continue
            
            # Pair up GT and Pred IDs - only use records where both exist
            paired_records = [(r.gt_option_id, r.pred_option_id) for r in field_records 
                              if r.gt_option_id is not None and r.pred_option_id is not None]
            
            if not paired_records:
                ax.text(0.5, 0.5, "No predictions", ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{field_label} – {ds_label}")
                continue
            
            gt_ids = [pair[0] for pair in paired_records]
            pred_ids = [pair[1] for pair in paired_records]
            
            # Get all available option IDs for this field from the mapping
            all_labels = _get_field_option_ids(field_name)
            if not all_labels:  # Fallback if field not found in mapping
                all_labels = sorted(set(gt_ids))
            
            # Compute confusion matrix
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='A single label was found')
                cm = confusion_matrix(gt_ids, pred_ids, labels=all_labels)
            cm_arr = np.array(cm)
            
            # Plot heatmap
            im = ax.imshow(cm_arr, cmap=_CMAP_WHITE_GREEN, aspect="auto")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            
            ax.set_xticks(range(len(all_labels)))
            ax.set_yticks(range(len(all_labels)))
            ax.set_xticklabels([f"P:{l}" for l in all_labels], rotation=45, ha="right", fontsize=9)
            ax.set_yticklabels([f"GT:{l}" for l in all_labels], fontsize=9)
            
            # Annotate cells
            for i in range(cm_arr.shape[0]):
                for j in range(cm_arr.shape[1]):
                    bg = cm_arr[i, j] / (cm_arr.max() + 1e-9)
                    txt_color = "white" if bg > 0.5 else "black"
                    ax.text(j, i, str(cm_arr[i, j]), ha="center", va="center",
                            color=txt_color, fontsize=9, fontweight="bold")
            
            # Compute macro F1
            macro_f1 = f1_score(gt_ids, pred_ids, average="macro", labels=all_labels, zero_division=0)
            
            ax.set_title(f"{ds_label}\nMacro F1: {macro_f1:.4f}", fontsize=11, fontweight="bold")
            ax.set_xlabel("Predicted Option ID", fontsize=10)
            ax.set_ylabel("Ground Truth Option ID", fontsize=10)
        
        fig.suptitle(f"Field-Level Confusion Matrix – {field_label} – {experiment_name}", 
                     fontsize=12, fontweight="bold")
        fig.tight_layout()
        
        # Save with numbered prefix
        path = output_subdir / f"{field_label.split()[0]}_{field_name}.png"
        _savefig(fig, path)
        saved.append(path)
        logger.info(f"      Saved: {path.name}")
    
    return saved


# ============================================================================
# §9.1-E  Assembly-Level Scatter (Pred vs GT total FFA)
# ============================================================================

def plot_assembly_scatter(
    metrics_by_dataset: Dict[str, Dict],
    experiment_name: str,
    output_dir: Path,
) -> Path:
    """Scatter: x=GT total FFA, y=Pred total FFA, per assembly per dataset."""
    fig, ax = plt.subplots(figsize=(6, 5))

    ax.plot([0, 1], [0, 1], color="gray", linestyle="--", linewidth=1, label="Perfect agreement")

    for ds_label, m in metrics_by_dataset.items():
        color = COLOR_EVAL if "eval" in ds_label.lower() else COLOR_TEST
        asm_ffa = m.get("assembly_ffa", {})
        xs, ys, names = [], [], []
        for asm_id, data in asm_ffa.items():
            gt = data.get("gt_total_ffa")
            pr = data.get("pred_total_ffa")
            if gt is not None and pr is not None:
                xs.append(gt)
                ys.append(pr)
                names.append(asm_id)

        ax.scatter(xs, ys, color=color, s=80, edgecolors="black", linewidths=0.5,
                   label=ds_label, zorder=5)
        for x_pt, y_pt, name in zip(xs, ys, names):
            ax.annotate(name, (x_pt, y_pt), textcoords="offset points", xytext=(5, 4),
                        fontsize=7, color=color)

    mae_eval = metrics_by_dataset.get(next((k for k in metrics_by_dataset if "eval" in k.lower()), ""), {}).get("summary", {}).get("total_ffa_mae")
    mae_test = metrics_by_dataset.get(next((k for k in metrics_by_dataset if "test" in k.lower()), ""), {}).get("summary", {}).get("total_ffa_mae")
    subtitle = ""
    if mae_eval is not None:
        subtitle += f"Eval MAE={mae_eval:.3f}"
    if mae_test is not None:
        subtitle += f"  Test MAE={mae_test:.3f}"

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("GT Total FFA", fontsize=11)
    ax.set_ylabel("Predicted Total FFA", fontsize=11)
    ax.set_title(f"Assembly FFA: Predicted vs. Ground Truth\n{experiment_name}\n{subtitle}",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "E_assembly_scatter.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.2-A  Cross-Experiment Total FFA MAE Line Plot
# ============================================================================

def plot_cross_experiment_mae(
    cross_metrics: Dict[str, Dict[str, Dict]],  # {exp_name: {"eval": metrics, "test": metrics}}
    output_dir: Path,
) -> Path:
    """Vertical bar plot: x=experiment, y=MAE total FFA, bars=eval/test."""
    exp_names = sorted(cross_metrics.keys())

    eval_mae = [cross_metrics[e].get("eval", {}).get("summary", {}).get("total_ffa_mae") for e in exp_names]
    test_mae = [cross_metrics[e].get("test", {}).get("summary", {}).get("total_ffa_mae") for e in exp_names]

    fig, ax = plt.subplots(figsize=(max(8, len(exp_names) * 2.5), 4.5))
    x = np.arange(len(exp_names))
    width = 0.35

    eval_vals = [v if v is not None else 0 for v in eval_mae]
    test_vals = [v if v is not None else 0 for v in test_mae]

    bars1 = ax.bar(x - width/2, eval_vals, width, label="Eval Set", color=COLOR_EVAL, alpha=0.8)
    bars2 = ax.bar(x + width/2, test_vals, width, label="Test Set", color=COLOR_TEST, alpha=0.8)

    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(f"{height:.4f}",
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3), textcoords="offset points",
                           ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("Experiment", fontsize=11)
    ax.set_ylabel("MAE (Total FFA)", fontsize=11)
    ax.set_title("Total FFA MAE – Cross-Experiment Comparison", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_names, rotation=20, ha="right", fontsize=9)
    ax.legend(fontsize=10, loc="upper right")
    ax.set_ylim(bottom=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "cross_A_total_ffa_mae.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.2-B  Cross-Experiment Macro F1 Line Plot
# ============================================================================

def plot_cross_experiment_f1(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
) -> Path:
    """Vertical bar plot: x=experiment, y=Macro F1, bars=eval/test."""
    exp_names = sorted(cross_metrics.keys())

    eval_f1 = [cross_metrics[e].get("eval", {}).get("summary", {}).get("system_macro_f1") for e in exp_names]
    test_f1 = [cross_metrics[e].get("test", {}).get("summary", {}).get("system_macro_f1") for e in exp_names]

    fig, ax = plt.subplots(figsize=(max(8, len(exp_names) * 2.5), 4.5))
    x = np.arange(len(exp_names))
    width = 0.35

    eval_vals = [v if v is not None else 0 for v in eval_f1]
    test_vals = [v if v is not None else 0 for v in test_f1]

    bars1 = ax.bar(x - width/2, eval_vals, width, label="Eval Set", color=COLOR_EVAL, alpha=0.8)
    bars2 = ax.bar(x + width/2, test_vals, width, label="Test Set", color=COLOR_TEST, alpha=0.8)

    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(f"{height:.4f}",
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3), textcoords="offset points",
                           ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("Experiment", fontsize=11)
    ax.set_ylabel("Macro F1", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.7)
    ax.set_title("Macro F1 – Cross-Experiment Comparison", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_names, rotation=20, ha="right", fontsize=9)
    ax.legend(fontsize=10, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    path = output_dir / "cross_B_macro_f1.png"
    _savefig(fig, path)
    return path


# ============================================================================
# §9.2-B+ Cross-Experiment Macro F1 vs Weighted F1 Comparison
# ============================================================================

def plot_cross_experiment_f1_comparison(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
) -> Path:
    """
    Bar chart: 4 bars per experiment (Eval+Test × Macro+Weighted F1).
    Shows minority class impact by comparing Macro F1 vs Weighted F1.
    """
    exp_names = sorted(cross_metrics.keys())
    
    # Collect data: {exp_name: {metric_ds: value}}
    eval_macro = []
    eval_weighted = []
    test_macro = []
    test_weighted = []
    
    for exp_name in exp_names:
        eval_summary = cross_metrics[exp_name].get("eval", {}).get("summary", {})
        test_summary = cross_metrics[exp_name].get("test", {}).get("summary", {})
        
        eval_macro.append(eval_summary.get("system_macro_f1") or 0)
        eval_weighted.append(eval_summary.get("weighted_f1") or 0)
        test_macro.append(test_summary.get("system_macro_f1") or 0)
        test_weighted.append(test_summary.get("weighted_f1") or 0)
    
    if not any(eval_macro + eval_weighted + test_macro + test_weighted):
        logger.warning("  No F1 data for comparison")
        return output_dir / "cross_B+_macro_weighted_f1.png"
    
    # Colors
    COLOR_EVAL_MACRO = "#F58220"      # Eval Set – Macro F1
    COLOR_EVAL_WEIGHTED = "#C76009"   # Eval Set – Weighted F1
    COLOR_TEST_MACRO = "#179C7D"      # Test Set – Macro F1
    COLOR_TEST_WEIGHTED = "#11755E"   # Test Set – Weighted F1
    
    fig, ax = plt.subplots(figsize=(max(10, len(exp_names) * 2.5), 4.5))
    x = np.arange(len(exp_names))
    width = 0.2  # 4 bars per group
    
    bars1 = ax.bar(x - 1.5*width, eval_macro, width, label="Eval Macro F1", color=COLOR_EVAL_MACRO, alpha=0.85)
    bars2 = ax.bar(x - 0.5*width, eval_weighted, width, label="Eval Weighted F1", color=COLOR_EVAL_WEIGHTED, alpha=0.85)
    bars3 = ax.bar(x + 0.5*width, test_macro, width, label="Test Macro F1", color=COLOR_TEST_MACRO, alpha=0.85)
    bars4 = ax.bar(x + 1.5*width, test_weighted, width, label="Test Weighted F1", color=COLOR_TEST_WEIGHTED, alpha=0.85)
    
    # Add value labels on bars
    for bars in [bars1, bars2, bars3, bars4]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(f"{height:.3f}",
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 2), textcoords="offset points",
                           ha="center", va="bottom", fontsize=6.5)
    
    ax.set_ylabel("F1 Score", fontsize=11)
    ax.set_xlabel("Experiment", fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.7)
    ax.set_title("Macro F1 vs Weighted F1 – Minority Class Impact (Eval & Test)", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(exp_names, rotation=20, ha="right", fontsize=9)
    ax.legend(fontsize=9, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    
    path = output_dir / "cross_B+_macro_weighted_f1.png"
    _savefig(fig, path)
    logger.info(f"      Saved: {path.name}")
    return path


# ============================================================================
# §9.2-C  Category Heatmap (Experiment × Category)
# ============================================================================

def plot_category_heatmap(
    cross_metrics: Dict[str, Dict[str, Dict]],
    metric_key: str,          # "macro_f1" or "mae"
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """Matrix heatmap: rows=experiments, columns=categories, value=metric."""
    exp_names = sorted(cross_metrics.keys())
    n_exp = len(exp_names)
    n_cat = len(SUBPROCESSES)

    matrix = np.full((n_exp, n_cat), fill_value=np.nan)

    for i, exp_name in enumerate(exp_names):
        ds_metrics = cross_metrics[exp_name].get(dataset_key, {})
        for j, sp in enumerate(SUBPROCESSES):
            if metric_key == "macro_f1":
                val = ds_metrics.get("classification", {}).get(sp, {}).get("macro_f1")
            else:
                val = ds_metrics.get("regression", {}).get(sp, {}).get("mae")
            if val is not None:
                matrix[i, j] = val

    fig, ax = plt.subplots(figsize=(max(6, n_cat * 1.8), max(3, n_exp * 1.2)))
    
    # Use custom performance colormap for F1, reversed for MAE
    if metric_key == "macro_f1":
        # Custom: Red (bad/low F1) → Yellow → Green (good/high F1)
        im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE, aspect="auto", vmin=0, vmax=1)
        label_text = "Macro F1 (Green=Good)"
    else:
        # Custom: Red (bad/high MAE) → Yellow → Green (good/low MAE)
        im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE_REV, aspect="auto", vmin=0, vmax=1)
        label_text = "MAE (Green=Low Error)"
    
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label=label_text)

    ax.set_xticks(range(n_cat))
    ax.set_xticklabels([s.capitalize() for s in SUBPROCESSES], fontsize=11)
    ax.set_yticks(range(n_exp))
    ax.set_yticklabels(exp_names, fontsize=9)

    # Adaptive text color based on median
    valid_vals = matrix[~np.isnan(matrix)]
    threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5

    for i in range(n_exp):
        for j in range(n_cat):
            v = matrix[i, j]
            if not np.isnan(v):
                # For F1: low values (red) get white text, high values (green) get black
                # For MAE: high values (red) get white text, low values (green) get black
                if metric_key == "macro_f1":
                    txt_col = "white" if v < threshold else "black"
                else:
                    txt_col = "white" if v > threshold else "black"
                ax.text(j, i, f"{v:.3f}", ha="center", va="center",
                        color=txt_col, fontsize=9, fontweight="bold")

    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    metric_title = "Macro F1" if metric_key == "macro_f1" else "MAE"
    ax.set_title(f"Category Heatmap – {metric_title} ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()

    path = output_dir / f"cross_C_heatmap_{metric_key}_{dataset_key}.png"
    _savefig(fig, path)
    return path


def plot_field_heatmap(
    cross_records: Dict[str, Dict[str, List]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """Field-level heatmap: rows=experiments, columns=FFA fields (14), value=macro_f1."""
    from collections import defaultdict
    from evaluation.ffa_scoring import FFA_FIELD_ORDER
    
    exp_names = sorted(cross_records.keys())
    n_exp = len(exp_names)
    
    # Use the standard FFA field evaluation order (1-14)
    all_fields = FFA_FIELD_ORDER
    n_fields = len(all_fields)
    
    # Build matrix: experiments × fields
    matrix = np.full((n_exp, n_fields), fill_value=np.nan)
    
    for i, exp_name in enumerate(exp_names):
        records = cross_records.get(exp_name, {}).get(dataset_key, [])
        if not records:
            continue
        
        # Group by field_name
        gt_by_field: Dict[str, List[int]] = defaultdict(list)
        pred_by_field: Dict[str, List[int]] = defaultdict(list)
        
        for r in records:
            if r.field_name and r.gt_option_id is not None and r.pred_option_id is not None:
                gt_by_field[r.field_name].append(r.gt_option_id)
                pred_by_field[r.field_name].append(r.pred_option_id)
        
        # Compute macro F1 per field
        for j, field_name in enumerate(all_fields):
            gt_ids = gt_by_field.get(field_name, [])
            pred_ids = pred_by_field.get(field_name, [])
            
            if gt_ids and pred_ids:
                from evaluation.ffa_evaluator import _classification_metrics
                metrics = _classification_metrics(gt_ids, pred_ids)
                macro_f1 = metrics.get("macro_f1")
                if macro_f1 is not None:
                    matrix[i, j] = macro_f1
    
    # Create figure (wider for 14 fields)
    fig, ax = plt.subplots(figsize=(min(18, n_fields * 1.2), max(3, n_exp * 1.2)))
    # Use custom performance colormap: Red (bad/low F1) → Yellow (medium) → Green (good/high F1)
    im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE, aspect="auto", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Macro F1 (Green=Good)")
    
    # Format field labels (shorter for space)
    field_labels = [f.replace("_", "\n") for f in all_fields]
    ax.set_xticks(range(n_fields))
    ax.set_xticklabels(field_labels, fontsize=8, rotation=45, ha="right")
    ax.set_yticks(range(n_exp))
    ax.set_yticklabels(exp_names, fontsize=9)
    
    # Add values
    for i in range(n_exp):
        for j in range(n_fields):
            v = matrix[i, j]
            if not np.isnan(v):
                # For custom colormap: high F1 (green, light) → black text, low F1 (red, dark) → white text
                # Use median to determine threshold
                valid_vals = matrix[~np.isnan(matrix)]
                threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5
                txt_col = "white" if v < threshold else "black"
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color=txt_col, fontsize=7, fontweight="bold")
    
    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    ax.set_title(f"Field-Level Heatmap – Macro F1 ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()
    
    path = output_dir / f"cross_C_field_heatmap_{dataset_key}.png"
    _savefig(fig, path)
    return path


def plot_field_heatmap_aggregated(
    cross_records: Dict[str, Dict[str, List]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """
    Field-level heatmap aggregated by configuration (not by individual runs):
    - For each config (GPT-4o, GPT-4.1, GPT-5.4), for each field:
      - Collect ALL records from ALL runs of that config
      - Calculate macro F1 per run
      - Average F1 across all runs
      - Calculate 95% CI on the F1 values
    """
    import re
    from collections import defaultdict
    from evaluation.ffa_scoring import FFA_FIELD_ORDER
    
    # Group experiments by config name (strip _run\d+ suffix)
    config_runs: Dict[str, List[str]] = defaultdict(list)
    for exp_name in sorted(cross_records.keys()):
        config_name = re.sub(r"_run\d+$", "", exp_name, flags=re.IGNORECASE)
        config_runs[config_name].append(exp_name)
    
    config_names = sorted(config_runs.keys())
    n_configs = len(config_names)
    
    # Use the standard FFA field evaluation order (1-14)
    all_fields = FFA_FIELD_ORDER
    n_fields = len(all_fields)
    
    # Build matrix: configs × fields
    matrix = np.full((n_configs, n_fields), fill_value=np.nan)
    ci_matrix = np.full((n_configs, n_fields), fill_value=np.nan)  # For 95% CI
    
    for i, config_name in enumerate(config_names):
        run_exp_names = config_runs[config_name]
        
        # For each field, calculate F1 per run, then average
        for j, field_name in enumerate(all_fields):
            f1_scores_per_run = []
            
            # Collect F1 from each run of this config
            for exp_name in sorted(run_exp_names):
                records = cross_records.get(exp_name, {}).get(dataset_key, [])
                if not records:
                    continue
                
                # Filter records for this field
                field_records = [rec for rec in records if rec.field_name == field_name]
                
                if field_records:
                    gt_ids = [rec.gt_option_id for rec in field_records 
                              if rec.gt_option_id is not None]
                    pred_ids = [rec.pred_option_id for rec in field_records 
                                if rec.pred_option_id is not None]
                    
                    if gt_ids and pred_ids:
                        from evaluation.ffa_evaluator import _classification_metrics
                        metrics = _classification_metrics(gt_ids, pred_ids)
                        macro_f1 = metrics.get("macro_f1")
                        if macro_f1 is not None:
                            f1_scores_per_run.append(macro_f1)
            
            # Average F1 across runs for this field
            if f1_scores_per_run:
                mean_f1 = np.mean(f1_scores_per_run)
                std_f1 = np.std(f1_scores_per_run, ddof=0) if len(f1_scores_per_run) > 1 else 0
                se = std_f1 / np.sqrt(len(f1_scores_per_run))
                ci = 1.96 * se
                
                matrix[i, j] = mean_f1
                ci_matrix[i, j] = ci
    
    # Create figure
    fig, ax = plt.subplots(figsize=(min(20, n_fields * 1.2), max(3, n_configs * 1.5)))
    # Use custom performance colormap
    im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE, aspect="auto", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Macro F1 (Green=Good)")
    
    # Format field labels
    field_labels = [f.replace("_", "\n") for f in all_fields]
    
    ax.set_xticks(range(n_fields))
    ax.set_xticklabels(field_labels, fontsize=8, rotation=45, ha="right")
    ax.set_yticks(range(n_configs))
    ax.set_yticklabels(config_names, fontsize=9)
    
    # Add values with CI for fields
    for i in range(n_configs):
        for j in range(n_fields):
            v = matrix[i, j]
            ci = ci_matrix[i, j]
            if not np.isnan(v):
                valid_vals = matrix[~np.isnan(matrix)]
                threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5
                txt_col = "white" if v < threshold else "black"
                ci_str = f"±{ci:.2f}" if not np.isnan(ci) else ""
                ax.text(j, i, f"{v:.2f}\n{ci_str}", ha="center", va="center",
                        color=txt_col, fontsize=7, fontweight="bold")
    
    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    ax.set_title(f"Field-Level Heatmap (Config-Aggregated) – Macro F1 ± 95% CI ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()
    
    path = output_dir / f"cross_C_fields_aggregated__heatmap_{dataset_key}.png"
    _savefig(fig, path)
    return path
    ax.set_xticklabels(field_labels, fontsize=8, rotation=45, ha="right")
    ax.set_yticks(range(n_exp))
    ax.set_yticklabels(exp_names, fontsize=9)
    
    # Add values
    for i in range(n_exp):
        for j in range(n_fields):
            v = matrix[i, j]
            if not np.isnan(v):
                # For custom colormap: high F1 (green, light) → black text, low F1 (red, dark) → white text
                # Use median to determine threshold
                valid_vals = matrix[~np.isnan(matrix)]
                threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5
                txt_col = "white" if v < threshold else "black"
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color=txt_col, fontsize=7, fontweight="bold")
    
    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    ax.set_title(f"Field-Level Heatmap (Run-Aggregated) – Macro F1 ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()
    
    path = output_dir / f"cross_C_fields_aggregated__heatmap_{dataset_key}.png"
    _savefig(fig, path)
    return path


def plot_field_heatmap_mae(
    cross_records: Dict[str, Dict[str, List]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """Field-level MAE heatmap: rows=experiments, columns=FFA fields (14), value=mae."""
    from collections import defaultdict
    from evaluation.ffa_scoring import FFA_FIELD_ORDER
    
    exp_names = sorted(cross_records.keys())
    n_exp = len(exp_names)
    
    # Use the standard FFA field evaluation order (1-14)
    all_fields = FFA_FIELD_ORDER
    n_fields = len(all_fields)
    
    # Build matrix: experiments × fields (for MAE)
    matrix = np.full((n_exp, n_fields), fill_value=np.nan)
    
    for i, exp_name in enumerate(exp_names):
        records = cross_records.get(exp_name, {}).get(dataset_key, [])
        if not records:
            continue
        
        # Group by field_name
        errors_by_field: Dict[str, List[float]] = defaultdict(list)
        
        for r in records:
            if r.field_name and r.abs_error is not None:
                errors_by_field[r.field_name].append(r.abs_error)
        
        # Compute MAE per field
        for j, field_name in enumerate(all_fields):
            errors = errors_by_field.get(field_name, [])
            if errors:
                mae = np.mean(errors)
                matrix[i, j] = mae
    
    # Create figure (wider for 14 fields)
    fig, ax = plt.subplots(figsize=(min(18, n_fields * 1.2), max(3, n_exp * 1.2)))
    # Use custom performance colormap reversed: Red (bad/high MAE) → Yellow → Green (good/low MAE)
    im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE_REV, aspect="auto", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="MAE (Green=Low Error)")
    
    # Format field labels (shorter for space)
    field_labels = [f.replace("_", "\n") for f in all_fields]
    ax.set_xticks(range(n_fields))
    ax.set_xticklabels(field_labels, fontsize=8, rotation=45, ha="right")
    ax.set_yticks(range(n_exp))
    ax.set_yticklabels(exp_names, fontsize=9)
    
    # Add values
    for i in range(n_exp):
        for j in range(n_fields):
            v = matrix[i, j]
            if not np.isnan(v):
                # For custom colormap reversed: low MAE (green, light) → black text, high MAE (red, dark) → white text
                # Use median of data to determine threshold
                valid_vals = matrix[~np.isnan(matrix)]
                threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5
                txt_col = "white" if v > threshold else "black"
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color=txt_col, fontsize=7, fontweight="bold")
    
    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    ax.set_title(f"Field-Level Heatmap – MAE ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()
    
    path = output_dir / f"cross_C_field_heatmap_mae_{dataset_key}.png"
    _savefig(fig, path)
    return path


def plot_field_heatmap_mae_aggregated(
    cross_records: Dict[str, Dict[str, List]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """
    Field-level MAE heatmap aggregated by configuration (not by individual runs):
    - For each config (GPT-4o, GPT-4.1, GPT-5.4), for each field:
      - Collect ALL records from ALL runs of that config
      - Calculate MAE per run
      - Average MAE across all runs
      - Calculate 95% CI on the MAE values
    """
    import re
    from collections import defaultdict
    from evaluation.ffa_scoring import FFA_FIELD_ORDER
    
    # Group experiments by config name (strip _run\d+ suffix)
    config_runs: Dict[str, List[str]] = defaultdict(list)
    for exp_name in sorted(cross_records.keys()):
        config_name = re.sub(r"_run\d+$", "", exp_name, flags=re.IGNORECASE)
        config_runs[config_name].append(exp_name)
    
    config_names = sorted(config_runs.keys())
    n_configs = len(config_names)
    
    # Use the standard FFA field evaluation order (1-14)
    all_fields = FFA_FIELD_ORDER
    n_fields = len(all_fields)
    
    # Build matrix: configs × fields
    matrix = np.full((n_configs, n_fields), fill_value=np.nan)
    ci_matrix = np.full((n_configs, n_fields), fill_value=np.nan)  # For 95% CI
    
    for i, config_name in enumerate(config_names):
        run_exp_names = config_runs[config_name]
        
        # For each field, calculate MAE per run, then average
        for j, field_name in enumerate(all_fields):
            mae_scores_per_run = []
            
            # Collect MAE from each run of this config
            for exp_name in sorted(run_exp_names):
                records = cross_records.get(exp_name, {}).get(dataset_key, [])
                if not records:
                    continue
                
                # Filter records for this field
                field_records = [rec for rec in records if rec.field_name == field_name]
                
                if field_records:
                    errors = [rec.abs_error for rec in field_records 
                              if rec.abs_error is not None]
                    
                    if errors:
                        mae = np.mean(errors)
                        mae_scores_per_run.append(mae)
            
            # Average MAE across runs for this field
            if mae_scores_per_run:
                mean_mae = np.mean(mae_scores_per_run)
                std_mae = np.std(mae_scores_per_run, ddof=0) if len(mae_scores_per_run) > 1 else 0
                se = std_mae / np.sqrt(len(mae_scores_per_run))
                ci = 1.96 * se
                
                matrix[i, j] = mean_mae
                ci_matrix[i, j] = ci
    
    # Create figure
    fig, ax = plt.subplots(figsize=(min(20, n_fields * 1.2), max(3, n_configs * 1.5)))
    # Use custom performance colormap reversed: Red (bad/high MAE) → Yellow → Green (good/low MAE)
    im = ax.imshow(matrix, cmap=_CMAP_PERFORMANCE_REV, aspect="auto", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="MAE (Green=Low Error)")
    
    # Format field labels
    field_labels = [f.replace("_", "\n") for f in all_fields]
    
    ax.set_xticks(range(n_fields))
    ax.set_xticklabels(field_labels, fontsize=8, rotation=45, ha="right")
    ax.set_yticks(range(n_configs))
    ax.set_yticklabels(config_names, fontsize=9)
    
    # Add values with CI for fields
    for i in range(n_configs):
        for j in range(n_fields):
            v = matrix[i, j]
            ci = ci_matrix[i, j]
            if not np.isnan(v):
                valid_vals = matrix[~np.isnan(matrix)]
                threshold = np.median(valid_vals) if len(valid_vals) > 0 else 0.5
                txt_col = "white" if v > threshold else "black"
                ci_str = f"±{ci:.2f}" if not np.isnan(ci) else ""
                ax.text(j, i, f"{v:.2f}\n{ci_str}", ha="center", va="center",
                        color=txt_col, fontsize=7, fontweight="bold")
    
    ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
    ax.set_title(f"Field-Level Heatmap (Config-Aggregated) – MAE ± 95% CI ({ds_title})", fontsize=12, fontweight="bold")
    fig.tight_layout()
    
    path = output_dir / f"cross_C_fields_aggregated__heatmap_mae_{dataset_key}.png"
    _savefig(fig, path)
    return path


def plot_cross_experiment_ffa_bars(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Path:
    """
    Create grouped bar chart showing GT vs experiment total FFA scores per assembly.
    
    Each assembly is a group with bars for GT + each experiment.
    """
    try:
        # Collect experiment names and assemblies
        exp_names = sorted([e for e in cross_metrics.keys() if not e.startswith("_")])
        if not exp_names:
            logger.warning(f"  No experiments found for FFA bars")
            return None
        
        # Use the union across experiments. Some assemblies may be missing from
        # a subset of runs; they should still be shown when any run has data.
        assembly_data: Dict[str, Dict] = {}
        for exp_name in exp_names:
            exp_assembly_data = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            for asm_id, asm_scores in exp_assembly_data.items():
                assembly_data.setdefault(asm_id, asm_scores)

        if not assembly_data:
            logger.warning(f"  No assembly_ffa data found for {dataset_key}")
            return None
        
        # Sort by assembly_name (not ID)
        assembly_items = sorted(assembly_data.items())
        n_assemblies = len(assembly_items)
        n_experiments = len(exp_names)
        
        # Prepare data: assembly → [gt_score, exp1_score, exp2_score, ...]
        x_labels = []
        data_matrix = []
        
        for asm_id, asm_scores in assembly_items:
            x_labels.append(asm_scores.get("name", display_assembly_name(asm_id)))
            scores = [asm_scores.get("gt_total_ffa", np.nan)]
            
            # Add experiment scores
            for exp_name in exp_names:
                exp_asm_data = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
                if asm_id in exp_asm_data:
                    scores.append(exp_asm_data[asm_id].get("pred_total_ffa", np.nan))
                else:
                    scores.append(np.nan)
            
            data_matrix.append(scores)
        
        data_matrix = np.array(data_matrix).T  # Transpose: (1+n_exp) × n_assemblies
        
        # Create figure
        fig, ax = plt.subplots(figsize=(max(12, n_assemblies * 1.5), 6))
        
        # Prepare bar positions
        bar_width = 0.15
        x_pos = np.arange(n_assemblies)
        bar_positions = [x_pos + (i - n_experiments / 2) * bar_width 
                        for i in range(n_experiments + 1)]
        
        # Colors: GT (green) + experiment colors
        colors = [_COLOR_GT] + _EXPERIMENT_COLORS[:n_experiments]
        
        # Plot bars
        bar_containers = []
        labels = ["GT"] + list(exp_names)
        
        for idx, (bar_pos, color, label) in enumerate(zip(bar_positions, colors, labels)):
            values = data_matrix[idx]
            bars = ax.bar(bar_pos, values, bar_width, label=label, color=color, alpha=0.85)
            bar_containers.append(bars)
            
            # Add value labels on bars
            for bar, value in zip(bars, values):
                if not np.isnan(value):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height,
                           f"{value:.2f}", ha="center", va="bottom", 
                           fontsize=7, color="black", fontweight="bold")
        
        # Configure axes
        ax.set_xlabel("Assembly", fontsize=11, fontweight="bold")
        ax.set_ylabel("FFA Score", fontsize=11, fontweight="bold")
        ax.set_xticks(x_pos)
        ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=9)
        # Extend y-axis to leave whitespace above bars so the legend never overlaps data
        all_vals = data_matrix[~np.isnan(data_matrix)]
        y_max = float(np.nanmax(all_vals)) if len(all_vals) else 1.0
        ax.set_ylim(0, max(1.0, y_max) * 1.35)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        n_legend_cols = max(1, min(4, n_experiments + 1))
        ax.legend(fontsize=9, loc="upper center",
                  ncol=n_legend_cols, framealpha=0.9,
                  bbox_to_anchor=(0.5, 1.0))

        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        ax.set_title(f"Cross-Experiment Total FFA Scores ({ds_title})",
                    fontsize=13, fontweight="bold", pad=15)

        fig.tight_layout()

        path = output_dir / f"cross_A_total_ffa_bars_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as e:
        logger.error(f"  Failed to create FFA bars: {e}")
        return None


# ============================================================================
# §9.2-A+  Cross-Experiment FFA Bars – Runs only (no GT), Variationstest
# ============================================================================

def plot_cross_experiment_ffa_bars_variationtest(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Optional[Path]:
    """
    Same layout as plot_cross_experiment_ffa_bars but shows ONLY the
    experiment runs – no GT bar.  Useful for comparing run-to-run
    variability without the GT reference dominating the view.

    Filename: cross_A_total_ffa_bars_Variationtest_{dataset_key}.png
    """
    try:
        exp_names = sorted([e for e in cross_metrics.keys() if not e.startswith("_")])
        if not exp_names:
            logger.warning("  plot_cross_experiment_ffa_bars_variationtest: no experiments")
            return None

        assembly_data: Dict[str, Dict] = {}
        for exp_name in exp_names:
            exp_assembly_data = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            for asm_id, asm_scores in exp_assembly_data.items():
                assembly_data.setdefault(asm_id, asm_scores)

        if not assembly_data:
            logger.warning(f"  No assembly_ffa data for {dataset_key}")
            return None

        assembly_items = sorted(assembly_data.items())
        n_assemblies = len(assembly_items)
        n_experiments = len(exp_names)

        x_labels = []
        # data_matrix rows: one per experiment (no GT row)
        data_matrix = []

        for asm_id, asm_scores in assembly_items:
            x_labels.append(asm_scores.get("name", display_assembly_name(asm_id)))

        for exp_name in exp_names:
            row = []
            for asm_id, _ in assembly_items:
                exp_asm = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
                row.append(exp_asm.get(asm_id, {}).get("pred_total_ffa", np.nan))
            data_matrix.append(row)

        data_matrix = np.array(data_matrix)  # n_experiments × n_assemblies

        fig, ax = plt.subplots(figsize=(max(12, n_assemblies * 1.5), 6))

        bar_width = 0.7 / max(n_experiments, 1)
        x_pos = np.arange(n_assemblies)
        offsets = np.linspace(-(n_experiments - 1) / 2, (n_experiments - 1) / 2, n_experiments) * bar_width

        for idx, (exp_name, offset) in enumerate(zip(exp_names, offsets)):
            values = data_matrix[idx]
            bars = ax.bar(
                x_pos + offset, values, bar_width,
                label=exp_name,
                color=_EXPERIMENT_COLORS[idx % len(_EXPERIMENT_COLORS)],
                alpha=0.85,
            )
            for bar, value in zip(bars, values):
                if not np.isnan(value):
                    ax.text(
                        bar.get_x() + bar.get_width() / 2., bar.get_height(),
                        f"{value:.2f}", ha="center", va="bottom",
                        fontsize=7, color="black", fontweight="bold",
                    )

        ax.set_xlabel("Assembly", fontsize=11, fontweight="bold")
        ax.set_ylabel("FFA Score", fontsize=11, fontweight="bold")
        ax.set_xticks(x_pos)
        ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=9)
        all_vals = data_matrix[~np.isnan(data_matrix)]
        y_max = float(np.nanmax(all_vals)) if len(all_vals) else 1.0
        ax.set_ylim(0, max(1.0, y_max) * 1.35)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        n_legend_cols = max(1, min(4, n_experiments))
        ax.legend(fontsize=9, loc="upper center",
                  ncol=n_legend_cols, framealpha=0.9,
                  bbox_to_anchor=(0.5, 1.0))

        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        ax.set_title(
            f"Total FFA Scores – Runs Only / Variationstest ({ds_title})",
            fontsize=13, fontweight="bold", pad=15,
        )
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        path = output_dir / f"cross_A_total_ffa_bars_Variationtest_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_cross_experiment_ffa_bars_variationtest failed: {exc}", exc_info=True)
        return None


# ============================================================================
# §9.2-E  FFA Deviation – Std + 95 % Confidence Interval per Assembly
# ============================================================================

def _fmt_p(p) -> str:
    """Format a p-value for display: scientific notation for very small values."""
    if p is None:
        return "–"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}"


def plot_stat_table(
    stat_comparisons: List[Dict],
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
    run_label: Optional[str] = None,
) -> Optional[Path]:
    """
    Standalone statistical test results table (Mann-Whitney-U + t-test, BH-corrected).
    Auto-sizes to content. Saved as cross_E_stat_table_{dataset_key}.png.
    """
    try:
        relevant = [c for c in (stat_comparisons or []) if c.get("dataset") == dataset_key]
        if not relevant:
            return None

        # Group colours – same Viridis logic as plot_ffa_deviation
        all_exp = sorted([e for e in cross_metrics if not e.startswith("_")])
        group_names = sorted({re.sub(r"_run\d+$", "", e, flags=re.IGNORECASE) for e in all_exp})
        _n = len(group_names)
        _cmap = plt.get_cmap("viridis")
        group_colors = {
            gname: _cmap(0.15 + 0.70 * i / (_n - 1 if _n > 1 else 1))
            for i, gname in enumerate(group_names)
        }

        col_labels = ["Comparison", "Metric", "Test", "p_raw", "p_BH", "r / d", "Sig."]
        rows, colors, text_colors = [], [], []

        for comp in relevant:
            na        = comp.get("name_a", "?")
            nb        = comp.get("name_b", "?")
            col_a     = group_colors.get(na, (0.3, 0.3, 0.3, 1))
            comp_label = f"{na}  vs  {nb}"

            for metric_key, metric_label in [("total_ffa_mae", "MAE"), ("macro_f1", "Macro F1")]:
                m = comp.get("metrics", {}).get(metric_key, {})
                if not m:
                    continue

                _ra, _ga, _ba = col_a[0], col_a[1], col_a[2]
                bg     = (_ra * 0.08 + 0.92, _ga * 0.08 + 0.92, _ba * 0.08 + 0.92, 1.0)
                bg_alt = (_ra * 0.04 + 0.96, _ga * 0.04 + 0.96, _ba * 0.04 + 0.96, 1.0)

                # ── Mann-Whitney-U row ──
                w       = m.get("mannwhitneyu", {})
                p_raw_w = w.get("p_raw")
                p_bh_w  = m.get("p_adjusted_bh", w.get("p_adjusted_bh"))
                r_rb    = m.get("rank_biserial_r")
                sig_w   = m.get("significant", False)
                sig_bg_w = (0.85, 0.95, 0.88, 1.0) if sig_w else (0.97, 0.88, 0.88, 1.0)

                rows.append([comp_label, metric_label, "Mann-Whitney-U",
                              _fmt_p(p_raw_w), _fmt_p(p_bh_w),
                              f"{r_rb:+.2f}" if r_rb is not None else "–",
                              "✓" if sig_w else "✗"])
                colors.append([bg, "#FAFAFA", "#FAFAFA", "#FAFAFA",
                               "#FAFAFA", "#FAFAFA", sig_bg_w])
                text_colors.append([col_a, "#333", "#555", "#333", "#333", "#333",
                                    "#179C7D" if sig_w else "#CC4444"])

                # ── t-test row ──
                tt      = m.get("ttest", {})
                p_raw_t = tt.get("p_raw")
                p_bh_t  = tt.get("p_adjusted_bh")
                d       = tt.get("cohens_d")
                paired  = tt.get("paired", True)
                test_lbl = "t-test (paired)" if paired else "t-test (Welch)"
                sig_t   = bool(p_bh_t < 0.05) if p_bh_t is not None else False
                sig_bg_t = (0.85, 0.95, 0.88, 1.0) if sig_t else (0.97, 0.88, 0.88, 1.0)

                rows.append(["", "", test_lbl,
                              _fmt_p(p_raw_t), _fmt_p(p_bh_t),
                              f"{d:+.2f}" if d is not None else "–",
                              "✓" if sig_t else "✗"])
                colors.append([bg_alt, "#FAFAFA", "#FAFAFA", "#FAFAFA",
                               "#FAFAFA", "#FAFAFA", sig_bg_t])
                text_colors.append(["#888", "#888", "#555", "#333", "#333", "#333",
                                    "#179C7D" if sig_t else "#CC4444"])

        if not rows:
            return None

        n_rows  = len(rows)
        fig_h   = max(1.5, 0.5 + (n_rows + 1) * 0.50)
        fig, ax = plt.subplots(figsize=(14, fig_h))
        ax.axis("off")
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        title = f"Statistical Tests  –  Mann-Whitney-U + t-test (independent), BH-corrected  ({ds_title})"
        if run_label:
            title = f"{run_label} — {title}"
        ax.set_title(title, fontsize=11, fontweight="bold", pad=8)

        tbl = ax.table(
            cellText=rows,
            colLabels=col_labels,
            cellLoc="left",
            loc="center",
            cellColours=colors,
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9.5)
        tbl.auto_set_column_width(list(range(len(col_labels))))
        tbl.scale(1.0, 1.8)

        for j in range(len(col_labels)):
            tbl[0, j].set_facecolor("#C8D4E8")
            tbl[0, j].set_text_props(fontweight="bold", color="#1a1a2e")

        for row_i, tc_row in enumerate(text_colors, start=1):
            for col_j, tc in enumerate(tc_row):
                tbl[row_i, col_j].set_text_props(color=tc)
            tbl[row_i, 6].set_text_props(fontweight="bold", color=tc_row[6])

        fig.tight_layout()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_run = re.sub(r"[^\w\-]", "_", run_label) if run_label else None
        filename = f"cross_E_stat_table_{dataset_key}.png"
        if safe_run:
            filename = f"{safe_run}_{filename}"
        path = output_dir / filename
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_stat_table failed: {exc}", exc_info=True)
        return None


def plot_ffa_deviation(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
    stat_comparisons: Optional[List[Dict]] = None,
    run_label: Optional[str] = None,
    include_groups: Optional[List[str]] = None,
    filename_suffix: Optional[str] = None,
    group_label_overrides: Optional[Dict[str, str]] = None,
) -> Optional[Path]:
    """
    Horizontal band chart – per assembly, one ±1 SD band per experiment group.

    Keys in cross_metrics follow the format  "{group_name}__{run_id}"
    (written by run_evaluation.py).  All runs belonging to the same group are
    aggregated to a per-group mean ± 1 SD.

    For each assembly row:
      • Green dot     = GT reference score
      • Coloured band = mean ± 1 SD for that experiment group
      • Coloured dot  = group mean

    Assemblies are sorted by the absolute difference between group means
    (largest divergence on top).

    Filename: cross_E_ffa_deviation_{dataset_key}.png
    """
    try:
        all_keys = sorted([e for e in cross_metrics if not e.startswith("_")])
        if include_groups:
            include_set = set(include_groups)
            all_keys = [
                key for key in all_keys
                if (key.split("__")[0] if "__" in key else key) in include_set
            ]
        if len(all_keys) < 2:
            logger.info("  plot_ffa_deviation: need ≥2 experiments, skipping")
            return None

        # ── parse group names from "groupName__runId" keys ───────────────
        groups_order: list = []
        group_runs: Dict[str, list] = {}
        for key in all_keys:
            if "__" in key:
                gname = key.split("__")[0]
            else:
                gname = key  # fallback: legacy single-run key
            if gname not in group_runs:
                group_runs[gname] = []
                groups_order.append(gname)
            group_runs[gname].append(key)

        n_groups = len(groups_order)

        # ── collect per-group preds per assembly ─────────────────────────
        # asm_data[asm_id] = {"name": str, "gt": float, groups: {gname: [preds]}}
        asm_data: Dict[str, dict] = {}
        for gname, run_keys in group_runs.items():
            for rkey in run_keys:
                asm_ffa = cross_metrics[rkey].get(dataset_key, {}).get("assembly_ffa", {})
                for asm_id, entry in asm_ffa.items():
                    if asm_id not in asm_data:
                        asm_data[asm_id] = {
                            "name": entry.get("name", asm_id),
                            "gt":   entry.get("gt_total_ffa", np.nan),
                            "groups": {},
                        }
                    grp = asm_data[asm_id]["groups"].setdefault(gname, [])
                    pred = entry.get("pred_total_ffa")
                    if pred is not None and not np.isnan(float(pred)):
                        grp.append(float(pred))

        if not asm_data:
            logger.warning(f"  plot_ffa_deviation: no assembly_ffa data ({dataset_key})")
            return None

        # ── sort assemblies by GT reference FFA descending ─────────────────
        ordered = sorted(asm_data.items(), key=lambda kv: kv[1]["gt"], reverse=True)
        n_asm = len(ordered)
        y_pos = np.arange(n_asm)
        asm_names = [v["name"] for _, v in ordered]
        gts = np.array([v["gt"] for _, v in ordered])

        # ── figure ────────────────────────────────────────────────────────
        row_height = max(4, n_asm * 0.80 + 2.0)
        fig = plt.figure(figsize=(14, row_height))
        ax = fig.add_subplot(111)
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        title = f"System-FfA ± 95% Konfidenzintervall je Baugruppe ({ds_title})"
        if run_label:
            title = f"{run_label} — {title}"
        fig.suptitle(title, fontsize=12, fontweight="bold")

        _legend_style = dict(boxstyle="round,pad=0.4", fc="white", ec="#CCCCCC", lw=0.8, alpha=0.9)
        _box_x = 1.02

        # ── draw per-group bands + mean dots ────────────────────────────
        legend_handles = []
        group_stats: Dict[str, Dict] = {}  # for summary box

        # Viridis palette – evenly spaced, avoids the very dark end (0.0)
        # and the bright yellow end (1.0) for readability on white background
        _cmap = plt.get_cmap("viridis")
        _n = max(n_groups, 1)
        group_colors = [_cmap(0.15 + 0.70 * i / (_n - 1 if _n > 1 else 1))
                        for i in range(_n)]

        for g_idx, gname in enumerate(groups_order):
            color = group_colors[g_idx]
            g_means, g_stds, g_n_runs = [], [], []
            for _, entry in ordered:
                preds = entry["groups"].get(gname, [])
                if len(preds) >= 2:
                    g_means.append(np.nanmean(preds))
                    g_stds.append(np.nanstd(preds, ddof=0))
                    g_n_runs.append(len(preds))
                elif len(preds) == 1:
                    g_means.append(preds[0])
                    g_stds.append(np.nan)
                    g_n_runs.append(1)
                else:
                    g_means.append(np.nan)
                    g_stds.append(np.nan)
                    g_n_runs.append(0)

            g_means_arr = np.array(g_means)
            g_stds_arr  = np.array(g_stds)
            g_n_runs_arr = np.array(g_n_runs)
            valid_sd = ~np.isnan(g_stds_arr) & (g_n_runs_arr >= 2)
            valid_m  = ~np.isnan(g_means_arr)

            # 95% CI band (mean ± 1.96 * SE, where SE = std / sqrt(n))
            if valid_sd.any():
                se = g_stds_arr[valid_sd] / np.sqrt(g_n_runs_arr[valid_sd])
                ci_half = 1.96 * se
                lo = np.clip(g_means_arr[valid_sd] - ci_half, 0.0, 1.0)
                hi = np.clip(g_means_arr[valid_sd] + ci_half, 0.0, 1.0)
                ax.barh(
                    y_pos[valid_sd], hi - lo, left=lo,
                    height=0.55,
                    color=color, alpha=0.30, zorder=2 + g_idx,
                )

            # Mean dot
            if valid_m.any():
                # Draw scatter points for means
                ax.scatter(
                    np.clip(g_means_arr[valid_m], 0.0, 1.0), y_pos[valid_m],
                    s=60, color=color, zorder=5 + g_idx,
                    edgecolors="white", linewidths=0.7,
                )
                # Create rectangle patch for legend (instead of scatter point)
                from matplotlib.patches import Patch
                rect_patch = Patch(
                    facecolor=color, alpha=0.60, edgecolor="none",
                    label=(group_label_overrides or {}).get(gname, gname)
                )
                legend_handles.append(rect_patch)

            # Collect summary stats for annotation
            errs = g_means_arr - gts
            valid_e = ~np.isnan(errs)

            # macro_f1 per run from cross_metrics summary
            f1_vals = []
            for rkey in group_runs[gname]:
                try:
                    f1 = cross_metrics[rkey][dataset_key]["summary"]["macro_f1"]
                    if f1 is not None:
                        f1_vals.append(float(f1))
                except (KeyError, TypeError):
                    pass
            mean_f1 = float(np.nanmean(f1_vals)) if f1_vals else float("nan")
            std_f1  = float(np.nanstd(f1_vals, ddof=0)) if len(f1_vals) >= 2 else float("nan")

            group_stats[gname] = {
                "color":    color,
                "mean_sd":  float(np.nanmean(g_stds_arr[valid_sd])) if valid_sd.any() else float("nan"),
                "mae":      float(np.nanmean(np.abs(errs[valid_e]))) if valid_e.any() else float("nan"),
                "mean_err": float(np.nanmean(errs[valid_e])) if valid_e.any() else float("nan"),
                "n_runs":   len(group_runs[gname]),
                "g_means":  g_means_arr,
                "g_stds":   g_stds_arr,
                "macro_f1": mean_f1,
                "f1_std":   std_f1,
            }

        # ── GT circle (orange scatter points) ──────────────────────────────────
        valid_gt = ~np.isnan(gts)
        if valid_gt.any():
            gt_indices = np.where(valid_gt)[0]
            gt_x = np.clip(gts[valid_gt], 0.0, 1.0)
            gt_y_list = np.array([y_pos[i] for i in gt_indices])
            
            # Draw orange circles for GT values
            ax.scatter(
                gt_x, gt_y_list,
                s=100, color=_COLOR_GT_RECT, alpha=0.9, zorder=9,
                edgecolors="white", linewidths=0.7,
            )
            
            # Add legend entry for GT circle
            import matplotlib.lines as mlines
            gt_line = mlines.Line2D(
                [], [], marker="o", color=_COLOR_GT_RECT, linestyle="None",
                markersize=8, markeredgecolor="white", markeredgewidth=0.7,
                label="Referenz-FfA"
            )
            legend_handles.insert(0, gt_line)



        # ── axes ──────────────────────────────────────────────────────────
        ax.set_yticks(y_pos)
        ax.set_yticklabels(asm_names, fontsize=13, fontfamily='serif', fontweight='bold')
        ax.set_xlabel("Baugruppen-FfA", fontsize=14, fontfamily='serif', fontweight='bold', labelpad=20)
        ax.set_xlim(0.6, 1.0)
        ax.set_ylim(-0.7, n_asm - 0.3)
        ax.grid(axis="x", alpha=0.25, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # ── legend ────────────────────────────────────────────────────────
        ax.legend(
            handles=legend_handles,
            fontsize=13, loc="lower center",
            bbox_to_anchor=(0.5, -0.28),
            ncol=5,
            borderaxespad=0, framealpha=0.9,
            prop={'family': 'serif'},
        )

        fig.tight_layout()
        fig.subplots_adjust(left=0.16, right=0.80, bottom=0.25)
        suffix = f"_{filename_suffix}" if filename_suffix else ""
        path = output_dir / f"cross_E_ffa_deviation_{dataset_key}{suffix}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_ffa_deviation failed: {exc}", exc_info=True)
        return None


# ============================================================================
# §9.2-F  Per-Assembly × Experiment-Group Deviation  (grouped runs, ±2 SD)
# ============================================================================

def plot_ffa_grouped_deviation(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Optional[Path]:
    """
    Horizontal scatter plot – one row-block per assembly, one row per
    experiment group within each block.

    Grouping: strips trailing ``_run<N>`` from the experiment key.
    • Single run  → coloured dot only
    • ≥2 runs     → mean dot  +  ±2 SD horizontal bar (clipped to [0.5, 1.0])
    • GT          → green dot at the top of each block

    Filename: cross_F_ffa_grouped_deviation_{dataset_key}.png
    """
    import matplotlib.patches as mpatches
    import matplotlib.lines as mlines

    try:
        all_exp_names = sorted([e for e in cross_metrics if not e.startswith("_")])
        if not all_exp_names:
            logger.warning("  plot_ffa_grouped_deviation: no experiments")
            return None

        # ── group runs by base name (strip _runN suffix) ────────────────
        groups: Dict[str, list] = {}
        for exp_name in all_exp_names:
            base = re.sub(r"_run\d+$", "", exp_name, flags=re.IGNORECASE)
            groups.setdefault(base, []).append(exp_name)
        group_names = sorted(groups.keys())
        n_groups = len(group_names)

        # ── collect assembly metadata ────────────────────────────────────
        asm_index: Dict[str, dict] = {}
        for exp_name in all_exp_names:
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            for asm_id, asm_data in asm_ffa.items():
                if asm_id not in asm_index:
                    asm_index[asm_id] = {
                        "name": asm_data.get("name", asm_id),
                        "gt":   asm_data.get("gt_total_ffa", np.nan),
                    }

        if not asm_index:
            logger.warning(f"  plot_ffa_grouped_deviation: no assembly_ffa data ({dataset_key})")
            return None

        ordered_asms = sorted(asm_index.items(), key=lambda kv: kv[1]["name"])
        n_asm = len(ordered_asms)

        # ── y-layout: each assembly occupies a block ─────────────────────
        row_gap    = 0.55           # vertical gap between rows within a block
        block_h    = (n_groups + 1) * row_gap + 0.5
        asm_y      = np.arange(n_asm, dtype=float) * block_h

        # GT row at top of each block, groups stacked below
        half = n_groups * row_gap / 2.0
        offset_gt  = +half
        grp_offsets = [half - (g + 1) * row_gap for g in range(n_groups)]

        # ── figure ───────────────────────────────────────────────────────
        fig_h = max(5, n_asm * block_h * 0.75 + 2.5)
        fig, ax = plt.subplots(figsize=(10, fig_h))
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        fig.suptitle(
            f"FFA Scores per Assembly & Experiment Group – ±2 SD  ({ds_title})",
            fontsize=12, fontweight="bold",
        )

        # ── draw ─────────────────────────────────────────────────────────
        for asm_idx, (asm_id, asm_data) in enumerate(ordered_asms):
            yc = asm_y[asm_idx]

            # GT dot
            gt_val = asm_data["gt"]
            if not np.isnan(gt_val):
                ax.scatter(
                    np.clip(gt_val, 0.5, 1.0), yc + offset_gt,
                    marker="o", s=60, color=_COLOR_GT, zorder=6,
                    edgecolors="white", linewidths=0.8,
                )

            for g_idx, gname in enumerate(group_names):
                color = _EXPERIMENT_COLORS[g_idx % len(_EXPERIMENT_COLORS)]
                yg = yc + grp_offsets[g_idx]

                preds = []
                for rk in groups[gname]:
                    asm_ffa = cross_metrics[rk].get(dataset_key, {}).get("assembly_ffa", {})
                    v = asm_ffa.get(asm_id, {}).get("pred_total_ffa")
                    if v is not None and not np.isnan(float(v)):
                        preds.append(float(v))

                if not preds:
                    continue

                mean_v = float(np.mean(preds))

                if len(preds) >= 2:
                    sd  = float(np.std(preds, ddof=0))
                    lo  = float(np.clip(mean_v - 2 * sd, 0.5, 1.0))
                    hi  = float(np.clip(mean_v + 2 * sd, 0.5, 1.0))
                    ax.barh(
                        yg, hi - lo, left=lo,
                        height=0.22, color=color, alpha=0.40, zorder=2,
                    )

                ax.scatter(
                    np.clip(mean_v, 0.5, 1.0), yg,
                    s=50, color=color, zorder=5,
                    edgecolors="white", linewidths=0.6, marker="o",
                )

        # Separator lines between assembly blocks
        for i in range(1, n_asm):
            sep_y = (asm_y[i - 1] + asm_y[i]) / 2.0
            ax.axhline(sep_y, color="lightgray", linewidth=0.8, zorder=1)

        # ── axes decoration ───────────────────────────────────────────────
        ax.set_yticks(asm_y)
        ax.set_yticklabels([v["name"] for _, v in ordered_asms], fontsize=9)
        ax.set_xlabel("Total FFA Score", fontsize=10)
        ax.set_xlim(0.5, 1.0)
        ax.set_ylim(asm_y[0] - block_h / 2, asm_y[-1] + block_h / 2)
        ax.grid(axis="x", alpha=0.25, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # ── legend (outside right) ─────────────────────────────────────
        legend_items = [mlines.Line2D(
            [], [], marker="o", color=_COLOR_GT, linestyle="None",
            markersize=7, label="GT",
        )]
        for g_idx, gname in enumerate(group_names):
            color = _EXPERIMENT_COLORS[g_idx % len(_EXPERIMENT_COLORS)]
            n_runs = len(groups[gname])
            label = f"{gname}  (n={n_runs})" if n_runs > 1 else gname
            legend_items.append(mlines.Line2D(
                [], [], marker="o", color=color, linestyle="None",
                markersize=7, label=label,
            ))
            if n_runs >= 2:
                legend_items.append(mpatches.Patch(
                    facecolor=color, alpha=0.40, label=f"  ± 2 SD",
                ))

        ax.legend(
            handles=legend_items,
            fontsize=8, loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            borderaxespad=0, framealpha=0.9,
        )

        fig.tight_layout()
        fig.subplots_adjust(right=0.72)

        path = output_dir / f"cross_F_ffa_grouped_deviation_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_ffa_grouped_deviation failed: {exc}", exc_info=True)
        return None


# ============================================================================
# §9.2-D  Per-Assembly Variation Plot (N runs)
# ============================================================================

def plot_assembly_variation(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Optional[Path]:
    """
    Shows run-to-run variation per assembly across all experiments.

    Left panel – Dot + error-bar plot:
      • x-axis: Total FFA score [0, 1]
      • y-axis: Assembly names (one row per assembly)
      • N dots per assembly (one per experiment run)
      • Mean marker (vertical line inside the error bar)
      • Horizontal error bar = mean ± 1 SD
      • GT reference marker (star)

    Right panel – Std deviation bar (sorted highest → lowest):
      • Quick 'which assembly is most variable' read-out
      • Optional CV (std/mean) on secondary axis when mean > 0.05

    Args:
        cross_metrics: {exp_name: {"eval"|"test": {"assembly_ffa": {...}, ...}}}
        output_dir: Destination directory.
        dataset_key: "eval" or "test".
    """
    try:
        exp_names = sorted([e for e in cross_metrics if not e.startswith("_")])
        if len(exp_names) < 2:
            logger.info("  plot_assembly_variation: need ≥2 experiments, skipping")
            return None

        # ── collect per-assembly data ──────────────────────────────────────
        # assembly_id → {name, gt, [pred_run_1, pred_run_2, ...]}
        asm_index: Dict[str, dict] = {}
        for exp_name in exp_names:
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            for asm_id, asm_data in asm_ffa.items():
                if asm_id not in asm_index:
                    asm_index[asm_id] = {
                        "name": asm_data.get("name", asm_id),
                        "gt":   asm_data.get("gt_total_ffa", np.nan),
                        "preds": [],
                    }
                pred = asm_data.get("pred_total_ffa")
                if pred is not None and not np.isnan(pred):
                    asm_index[asm_id]["preds"].append(pred)

        if not asm_index:
            logger.warning(f"  plot_assembly_variation: no assembly_ffa data ({dataset_key})")
            return None

        # Sort assemblies alphabetically by display name
        ordered = sorted(asm_index.items(), key=lambda kv: kv[1]["name"].lower())
        n_asm = len(ordered)
        y_pos = np.arange(n_asm)
        asm_names = [v["name"] for _, v in ordered]

        # ── compute stats ─────────────────────────────────────────────────
        means = np.array([np.nanmean(v["preds"]) if v["preds"] else np.nan for _, v in ordered])
        stds  = np.array([np.nanstd(v["preds"], ddof=0) if len(v["preds"]) >= 2 else np.nan for _, v in ordered])
        gts   = np.array([v["gt"] for _, v in ordered])
        # CV only where mean is large enough to be meaningful
        with np.errstate(invalid="ignore", divide="ignore"):
            cvs = np.where(means > 0.05, stds / means, np.nan)

        # ── figure: two panels ────────────────────────────────────────────
        fig, (ax_dot, ax_bar) = plt.subplots(
            1, 2,
            figsize=(14, max(4, n_asm * 0.65 + 1.5)),
            gridspec_kw={"width_ratios": [2, 1]},
        )
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        fig.suptitle(
            f"Per-Assembly Run Variation ({ds_title})\n"
            f"{len(exp_names)} experiments  ·  error bars = mean ± 1 SD",
            fontsize=12, fontweight="bold",
        )

        # ── LEFT: dot + error-bar plot ─────────────────────────────────────
        rng = np.random.default_rng(42)  # deterministic jitter

        for i, (_, v) in enumerate(ordered):
            preds = v["preds"]
            if not preds:
                continue
            # Individual run dots (jittered vertically for legibility)
            jitter = rng.uniform(-0.15, 0.15, size=len(preds))
            ax_dot.scatter(
                preds, i + jitter,
                s=28, alpha=0.7, zorder=3,
                color=[_EXPERIMENT_COLORS[k % len(_EXPERIMENT_COLORS)] for k in range(len(preds))],
                edgecolors="white", linewidths=0.4,
            )

        # Mean ± SD error bars
        valid = ~np.isnan(means)
        if valid.any():
            ax_dot.errorbar(
                means[valid], y_pos[valid],
                xerr=stds[valid],
                fmt="|", color="#333333",
                markersize=10, markeredgewidth=2.0,
                elinewidth=1.8, capsize=5, capthick=1.8,
                zorder=4, label="Mean ± 1 SD",
            )

        # GT reference markers
        gt_valid = ~np.isnan(gts)
        if gt_valid.any():
            ax_dot.scatter(
                gts[gt_valid], y_pos[gt_valid],
                marker="*", s=90, color=_COLOR_GT, zorder=5,
                label="GT", edgecolors="white", linewidths=0.4,
            )

        ax_dot.set_yticks(y_pos)
        ax_dot.set_yticklabels(asm_names, fontsize=9)
        ax_dot.set_xlabel("Total FFA Score", fontsize=10)
        ax_dot.set_xlim(-0.05, 1.05)
        ax_dot.set_ylim(-0.7, n_asm - 0.3)
        ax_dot.axvline(0.5, color="gray", linestyle=":", linewidth=0.8, alpha=0.5)
        ax_dot.grid(axis="x", alpha=0.25, linestyle="--")
        ax_dot.spines["top"].set_visible(False)
        ax_dot.spines["right"].set_visible(False)
        ax_dot.legend(fontsize=8, loc="lower right")

        # ── RIGHT: std deviation bars (sorted) ────────────────────────────
        sort_idx = np.argsort(stds)[::-1]  # highest std first
        stds_sorted  = stds[sort_idx]
        names_sorted = [asm_names[i] for i in sort_idx]
        cvs_sorted   = cvs[sort_idx]

        bar_colors = [
            "#F58220" if s > 0.15 else "#FDB913" if s > 0.08 else "#179C7D"
            for s in stds_sorted
        ]
        h_bars = ax_bar.barh(
            y_pos, stds_sorted,
            color=bar_colors, alpha=0.85, edgecolor="white", linewidth=0.5,
        )
        # Annotate bar values
        for bar, s in zip(h_bars, stds_sorted):
            if not np.isnan(s):
                ax_bar.text(
                    s + 0.003, bar.get_y() + bar.get_height() / 2,
                    f"{s:.3f}", va="center", ha="left", fontsize=8,
                )

        # CV as secondary x-axis overlay (dashed line)
        ax_bar2 = ax_bar.twiny()
        cv_valid = ~np.isnan(cvs_sorted)
        if cv_valid.any():
            ax_bar2.plot(
                cvs_sorted, y_pos,
                color="#595959", linestyle="--", marker="o",
                markersize=4, linewidth=1.2, label="CV (std/mean)",
            )
            ax_bar2.set_xlabel("CV (std / mean)", fontsize=8, color="#595959")
            ax_bar2.tick_params(axis="x", labelcolor="#595959", labelsize=7)
            ax_bar2.legend(fontsize=7, loc="lower right")

        ax_bar.set_yticks(y_pos)
        ax_bar.set_yticklabels(names_sorted, fontsize=9)
        ax_bar.set_xlabel("Std Deviation", fontsize=10)
        ax_bar.set_xlim(left=0)
        ax_bar.set_ylim(-0.7, n_asm - 0.3)
        ax_bar.grid(axis="x", alpha=0.25, linestyle="--")
        ax_bar.spines["top"].set_visible(False)
        ax_bar.spines["right"].set_visible(False)

        # Color legend
        from matplotlib.patches import Patch
        legend_patches = [
            Patch(color="#F58220", label="SD > 0.15  (high)"),
            Patch(color="#FDB913", label="SD 0.08–0.15  (medium)"),
            Patch(color="#179C7D", label="SD < 0.08  (low)"),
        ]
        ax_bar.legend(handles=legend_patches, fontsize=7, loc="lower right")

        fig.tight_layout()
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"cross_D_assembly_variation_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_assembly_variation failed: {exc}", exc_info=True)
        return None


# ============================================================================
# HELPER
# ============================================================================

def _line(ax, x, values, color, label):
    valid_x = [xi for xi, v in zip(x, values) if v is not None]
    valid_v = [v for v in values if v is not None]
    if not valid_v:
        return
    ax.plot(list(x), [v if v is not None else float("nan") for v in values],
            color=color, marker="o", linewidth=2, markersize=7, label=label)
    for xi, v in zip(valid_x, valid_v):
        ax.annotate(f"{v:.3f}", (xi, v), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8, color=color)


# ============================================================================
# CONVENIENCE: generate all within-experiment plots
# ============================================================================

def generate_within_experiment_plots(
    metrics_by_dataset: Dict[str, Dict],
    experiment_name: str,
    output_dir: Path,
) -> Dict[str, Path]:
    """Generate all §9.1 plots for one experiment."""
    saved = {}
    out = output_dir / experiment_name

    try:
        saved["A"] = plot_total_ffa_mae_bar(metrics_by_dataset, experiment_name, out)
    except Exception as e:
        logger.warning(f"  Plot A failed: {e}")
    try:
        saved["B"] = plot_category_mae(metrics_by_dataset, experiment_name, out)
    except Exception as e:
        logger.warning(f"  Plot B failed: {e}")
    try:
        saved["C"] = plot_category_macro_f1(metrics_by_dataset, experiment_name, out)
    except Exception as e:
        logger.warning(f"  Plot C failed: {e}")
    try:
        saved["E"] = plot_assembly_scatter(metrics_by_dataset, experiment_name, out)
    except Exception as e:
        logger.warning(f"  Plot E failed: {e}")

    return saved


# ============================================================================
# NEW  §9.2-G  FFA Deviation – grouped BY EXPERIMENT  (one block per exp)
# ============================================================================

def plot_ffa_deviation_exp_grouped(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Optional[Path]:
    """
    Horizontal dot plot: assemblies listed UNDER their experiment.

    Layout:
        ── Experiment 1 ────────────────  (grey separator + bold label)
            Assembly A   ● (GT green)  ◆ (pred, exp color)
            Assembly B   ● (GT green)  ◆ (pred, exp color)
        ── Experiment 2 ────────────────
            Assembly A   ● (GT green)  ◆ (pred, exp color)
            ...

    One block per experiment, separated by a thin grey divider.
    Filename: cross_E_ffa_by_experiment_{dataset_key}.png
    """
    try:
        exp_names = sorted([e for e in cross_metrics if not e.startswith("_")])
        if not exp_names:
            return None

        exp_colors = _EXPERIMENT_COLORS + [
            plt.cm.tab20(i / 20) for i in range(len(exp_names))
        ]

        # ── Build row list ──────────────────────────────────────────────
        # Each entry: {"label": str, "gt": float|None, "pred": float|None,
        #              "color": str, "is_header": bool}
        rows = []
        for exp_idx, exp_name in enumerate(exp_names):
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            if not asm_ffa:
                continue
            # Spacer between groups (skip before first)
            if rows:
                rows.append({"is_spacer": True})
            rows.append({"label": exp_name, "is_header": True, "color": exp_colors[exp_idx % len(exp_colors)]})
            for asm_id in sorted(asm_ffa.keys()):
                d = asm_ffa[asm_id]
                rows.append({
                    "label": d.get("name", asm_id),
                    "gt":    d.get("gt_total_ffa"),
                    "pred":  d.get("pred_total_ffa"),
                    "color": exp_colors[exp_idx % len(exp_colors)],
                    "is_header": False,
                    "is_spacer": False,
                })

        n = len(rows)
        if n == 0:
            return None

        fig_h = max(5, n * 0.45 + 2)
        fig, ax = plt.subplots(figsize=(9, fig_h))
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        fig.suptitle(
            f"Total FFA – GT vs Predicted  •  by Experiment  ({ds_title})",
            fontsize=12, fontweight="bold",
        )

        y = 0
        yticks, ylabels = [], []
        for row in reversed(rows):          # reversed so first exp is on top
            if row.get("is_spacer"):
                y += 0.4
                continue
            if row.get("is_header"):
                ax.axhline(y + 0.5, color="#BBBBBB", linewidth=0.8, zorder=1)
                ax.text(
                    0.50, y,
                    row["label"],
                    color=row["color"], fontsize=9, fontweight="bold",
                    va="center", ha="left",
                )
                y += 0.9
                continue
            yticks.append(y)
            ylabels.append(f"  {row['label']}")
            gt   = row.get("gt")
            pred = row.get("pred")
            if gt is not None and not np.isnan(float(gt)):
                ax.scatter([float(gt)],  [y], s=60, color=_COLOR_GT, zorder=5,
                           edgecolors="white", linewidths=0.6, marker="o", label="_gt")
            if pred is not None and not np.isnan(float(pred)):
                ax.scatter([float(pred)], [y], s=55, color=row["color"], zorder=5,
                           edgecolors="white", linewidths=0.6, marker="D", label="_pred")
            y += 1.0

        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels, fontsize=8)
        ax.set_xlabel("Total FFA Score", fontsize=10)
        ax.set_xlim(0.49, 1.01)
        ax.set_ylim(-0.8, y + 0.3)
        ax.grid(axis="x", alpha=0.25, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Legend: GT + one entry per experiment
        legend_handles = [
            plt.scatter([], [], s=60, color=_COLOR_GT, marker="o", label="GT"),
        ]
        for i, exp_name in enumerate(exp_names):
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            if not asm_ffa:
                continue
            legend_handles.append(
                plt.scatter([], [], s=55, color=exp_colors[i % len(exp_colors)],
                            marker="D", label=exp_name)
            )
        ax.legend(handles=legend_handles, fontsize=8, loc="upper left",
                  bbox_to_anchor=(1.01, 1.0), borderaxespad=0, framealpha=0.9)

        fig.tight_layout()
        fig.subplots_adjust(right=0.72)
        path = output_dir / f"cross_E_ffa_by_experiment_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_ffa_deviation_exp_grouped failed: {exc}", exc_info=True)
        return None


# ============================================================================
# NEW  §9.2-H  FFA Deviation – grouped BY ASSEMBLY  (GT + all experiments)
# ============================================================================

def plot_ffa_deviation_asm_overlaid(
    cross_metrics: Dict[str, Dict[str, Dict]],
    output_dir: Path,
    dataset_key: str = "eval",
    run_label: Optional[str] = None,
) -> Optional[Path]:
    """
    Horizontal dot plot: one row per assembly.

    On each row:
      ● large green circle  = GT value
      ◆ colored diamond × N = predicted value, one per experiment (different color)

    Assemblies are sorted alphabetically.
    Filename: cross_E_ffa_by_assembly_{dataset_key}.png
    """
    try:
        exp_names = sorted([e for e in cross_metrics if not e.startswith("_")])
        if not exp_names:
            return None

        exp_colors = _EXPERIMENT_COLORS + [
            plt.cm.tab20(i / 20) for i in range(len(exp_names))
        ]

        # ── Collect per-assembly data ───────────────────────────────────
        # asm_data[asm_name] = {"gt": float, "preds": {exp_name: float}}
        asm_data: Dict[str, dict] = {}
        for exp_name in exp_names:
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            for asm_id, d in asm_ffa.items():
                name = d.get("name", asm_id)
                if name not in asm_data:
                    asm_data[name] = {"gt": d.get("gt_total_ffa"), "preds": {}}
                pred = d.get("pred_total_ffa")
                if pred is not None:
                    asm_data[name]["preds"][exp_name] = float(pred)

        if not asm_data:
            return None

        asm_names_sorted = sorted(asm_data.keys())
        n_asm = len(asm_names_sorted)
        y_pos = np.arange(n_asm)

        fig_h = max(4, n_asm * 0.7 + 2.5)
        fig, ax = plt.subplots(figsize=(10, fig_h))
        ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
        title = f"Total FFA – GT vs Predicted  •  by Assembly  ({ds_title})"
        if run_label:
            title = f"{run_label} — {title}"
        fig.suptitle(title, fontsize=12, fontweight="bold")

        # Alternate row shading for readability
        for i in range(n_asm):
            if i % 2 == 0:
                ax.axhspan(i - 0.45, i + 0.45, color="#F5F5F5", zorder=0)

        for i, asm_name in enumerate(asm_names_sorted):
            d    = asm_data[asm_name]
            gt   = d.get("gt")
            preds = d.get("preds", {})

            # GT dot
            if gt is not None and not np.isnan(float(gt)):
                ax.scatter([float(gt)], [i], s=90, color=_COLOR_GT, zorder=6,
                           edgecolors="white", linewidths=0.8, marker="o")

            # Pred dot per experiment (slight vertical jitter to avoid overlap)
            n_exp = len(preds)
            offsets = np.linspace(-0.18, 0.18, n_exp) if n_exp > 1 else [0.0]
            for j, (exp_name, pred_val) in enumerate(
                sorted(preds.items(), key=lambda kv: exp_names.index(kv[0]))
            ):
                exp_idx = exp_names.index(exp_name)
                ax.scatter(
                    [pred_val], [i + offsets[j]],
                    s=60, color=exp_colors[exp_idx % len(exp_colors)],
                    zorder=5, edgecolors="white", linewidths=0.6, marker="D",
                )

            # Light connecting line from GT to each pred
            if gt is not None and not np.isnan(float(gt)):
                for pred_val in preds.values():
                    ax.plot([float(gt), pred_val], [i, i],
                            color="#CCCCCC", linewidth=0.7, zorder=3)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(asm_names_sorted, fontsize=9)
        ax.set_xlabel("Total FFA Score", fontsize=10)
        ax.set_xlim(0.49, 1.01)
        ax.set_ylim(-0.7, n_asm - 0.3)
        ax.grid(axis="x", alpha=0.25, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Legend
        legend_handles = [plt.scatter([], [], s=90, color=_COLOR_GT, marker="o", label="GT")]
        for i, exp_name in enumerate(exp_names):
            asm_ffa = cross_metrics[exp_name].get(dataset_key, {}).get("assembly_ffa", {})
            if not asm_ffa:
                continue
            legend_handles.append(
                plt.scatter([], [], s=60, color=exp_colors[i % len(exp_colors)],
                            marker="D", label=exp_name)
            )
        ax.legend(handles=legend_handles, fontsize=8, loc="upper left",
                  bbox_to_anchor=(1.01, 1.0), borderaxespad=0, framealpha=0.9)

        fig.tight_layout()
        fig.subplots_adjust(right=0.72)
        path = output_dir / f"cross_E_ffa_by_assembly_{dataset_key}.png"
        _savefig(fig, path)
        return path

    except Exception as exc:
        logger.error(f"  plot_ffa_deviation_asm_overlaid failed: {exc}", exc_info=True)
        return None


def _step_ffa_from_records(records, use_gt: bool) -> Dict[str, float]:
    """
    Compute per-step FFA scalar from a flat list of CriterionRecord.
    Returns {step_id_str: ffa_score} using the same formula as compute_assembly_ffa_from_records.
    """
    from collections import defaultdict
    _SUBPROCESSES = ["separation", "handling", "positioning", "joining"]

    step_recs: Dict[str, list] = defaultdict(list)
    for r in records:
        step_recs[r.step_id].append(r)

    result = {}
    for sid, recs in step_recs.items():
        sp_scores = []
        for sp in _SUBPROCESSES:
            sp_r = [r for r in recs if r.category == sp]
            if not sp_r:
                continue
            vals = np.array([r.gt_ffa_value if use_gt else r.pred_ffa_value for r in sp_r], dtype=float)
            ws   = np.array([r.criterion_weight for r in sp_r], dtype=float)
            w_sum = ws.sum()
            if w_sum > 0:
                sp_scores.append(float(np.dot(ws, vals) / w_sum))
        if sp_scores:
            # try to cast step_id to int for sorting
            try:
                sort_key = int(sid)
            except (ValueError, TypeError):
                sort_key = sid
            result[sid] = float(np.mean(sp_scores))
    return result


def plot_per_assembly_ffa_steps(
    records_per_group: Dict[str, Dict[str, Dict[str, list]]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Dict[str, Path]:
    """
    One plot per assembly:
      X-axis  = assembly step number (1, 2, ...)
      Y-axis  = FFA score  [0, 1]
      Green   = GT  (dots + line)
      Colours = per experiment group mean (dots + line) ± 1 SD shading

    Output: output_dir/per_assembly/{safe_asm_name}_{dataset_key}.png
    Returns {asm_name: path} for all saved plots.
    """
    saved: Dict[str, Path] = {}
    try:
        # ── parse group names ────────────────────────────────────────────
        groups_order: list = []
        group_runs: Dict[str, list] = {}
        for gname in sorted(records_per_group):
            if gname not in group_runs:
                group_runs[gname] = sorted(records_per_group[gname])
                groups_order.append(gname)

        # ── collect records per assembly ─────────────────────────────────
        # asm_records[asm_id][gname][run_id] = List[CriterionRecord]
        from collections import defaultdict
        asm_records: Dict[str, Dict[str, Dict[str, list]]] = defaultdict(lambda: defaultdict(dict))
        asm_name_map: Dict[str, str] = {}

        for gname in groups_order:
            for run_id, ds_map in records_per_group[gname].items():
                recs = ds_map.get(dataset_key, [])
                for r in recs:
                    asm_records[r.assembly_id][gname][run_id] = asm_records[r.assembly_id][gname].get(run_id, [])
                    asm_records[r.assembly_id][gname][run_id].append(r)
                    if r.assembly_id not in asm_name_map:
                        asm_name_map[r.assembly_id] = display_assembly_name(r.assembly_id)

        if not asm_records:
            return saved

        per_asm_dir = output_dir / "per_assembly"
        per_asm_dir.mkdir(parents=True, exist_ok=True)

        for asm_id, group_run_recs in asm_records.items():
            asm_label = asm_name_map.get(asm_id, asm_id)

            # ── compute GT step scores (use first group / run that has data) ──
            gt_step_scores: Dict[str, float] = {}
            for gname in groups_order:
                if not gt_step_scores:
                    for run_id, recs in group_run_recs.get(gname, {}).items():
                        if recs:
                            gt_step_scores = _step_ffa_from_records(recs, use_gt=True)
                            break

            if not gt_step_scores:
                continue

            # Sort steps numerically
            def _step_sort(s):
                try: return int(s)
                except (ValueError, TypeError): return s

            step_ids_sorted = sorted(gt_step_scores, key=_step_sort)
            x = list(range(1, len(step_ids_sorted) + 1))
            gt_vals = [gt_step_scores[s] for s in step_ids_sorted]

            # ── compute per-group mean ± std per step ────────────────────
            # group_step_runs[gname][step_id] = [val_run1, val_run2, ...]
            group_step_runs: Dict[str, Dict[str, list]] = {g: defaultdict(list) for g in groups_order}
            for gname in groups_order:
                for run_id, recs in group_run_recs.get(gname, {}).items():
                    if not recs:
                        continue
                    run_scores = _step_ffa_from_records(recs, use_gt=False)
                    for sid in step_ids_sorted:
                        if sid in run_scores:
                            group_step_runs[gname][sid].append(run_scores[sid])

            # ── figure ───────────────────────────────────────────────────
            n_steps = len(step_ids_sorted)
            fig, ax = plt.subplots(figsize=(max(7, n_steps * 1.2 + 2), 5))
            ds_title = "Eval Set" if dataset_key == "eval" else "Test Set"
            fig.suptitle(
                f"{asm_label}  –  FFA per Step  ({ds_title})",
                fontsize=11, fontweight="bold",
            )

            # GT line + dots
            ax.plot(x, gt_vals, color=_COLOR_GT, linewidth=2.0,
                    zorder=6, label="GT")
            ax.scatter(x, gt_vals, color=_COLOR_GT, s=70, zorder=7,
                       edgecolors="white", linewidths=0.7)

            # Per-group mean ± SD
            _cmap2 = plt.get_cmap("viridis")
            _ng = max(len(groups_order), 1)
            _grp_colors = [_cmap2(0.15 + 0.70 * i / (_ng - 1 if _ng > 1 else 1))
                           for i in range(_ng)]
            for g_idx, gname in enumerate(groups_order):
                color = _grp_colors[g_idx]
                means, stds = [], []
                for sid in step_ids_sorted:
                    vals = group_step_runs[gname].get(sid, [])
                    if vals:
                        means.append(float(np.nanmean(vals)))
                        stds.append(float(np.nanstd(vals, ddof=0)) if len(vals) >= 2 else 0.0)
                    else:
                        means.append(np.nan)
                        stds.append(np.nan)

                means_arr = np.array(means)
                stds_arr  = np.array(stds)
                valid = ~np.isnan(means_arr)

                if not valid.any():
                    continue

                x_valid = np.array(x)[valid]

                # SD shading
                lo = np.clip(means_arr[valid] - stds_arr[valid], 0.0, 1.0)
                hi = np.clip(means_arr[valid] + stds_arr[valid], 0.0, 1.0)
                ax.fill_between(x_valid, lo, hi, color=color, alpha=0.18, zorder=2)

                # Mean line + dots
                ax.plot(x_valid, means_arr[valid], color=color,
                        linewidth=1.8, zorder=5, label=gname)
                ax.scatter(x_valid, means_arr[valid], color=color, s=60,
                           zorder=6, edgecolors="white", linewidths=0.7)

            # ── axes ─────────────────────────────────────────────────────
            ax.set_xticks(x)
            ax.set_xticklabels([f"Step {s}" for s in step_ids_sorted],
                               fontsize=8.5, rotation=0)
            ax.set_xlabel("Assembly Step", fontsize=10)
            ax.set_ylabel("FFA Score", fontsize=10)
            ax.set_ylim(0.0, 1.05)
            ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)
            ax.grid(axis="y", alpha=0.25, linestyle="--")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

            ax.legend(fontsize=9, loc="lower right",
                      framealpha=0.9,
                      title="± 1 SD shading")

            fig.tight_layout()

            safe_name = re.sub(r'[^\w\-]', '_', asm_label)
            path = per_asm_dir / f"{safe_name}_{dataset_key}.png"
            _savefig(fig, path)
            saved[asm_label] = path

    except Exception as exc:
        logger.error(f"  plot_per_assembly_ffa_steps failed: {exc}", exc_info=True)
    return saved


def generate_cross_experiment_plots(
    cross_metrics: Dict[str, Dict[str, Dict]],
    cross_records: Dict[str, Dict[str, List]] = None,
    output_dir: Path = None,
    stat_comparisons: Optional[List[Dict]] = None,
    run_label: Optional[str] = None,
) -> Dict[str, Path]:
    """Generate all §9.2 plots."""
    if output_dir is None:
        output_dir = Path("data/experiments/evaluation/plots")
    if cross_records is None:
        cross_records = {}
    
    saved = {}
    out = output_dir / "cross_experiment"

    if len(cross_metrics) < 2:
        logger.info("  Skipping cross-experiment plots (need ≥2 experiments)")
        return saved

    try:
        saved["A"] = plot_cross_experiment_mae(cross_metrics, out)
    except Exception as e:
        logger.warning(f"  Cross-plot A failed: {e}")
    try:
        saved["B"] = plot_cross_experiment_f1(cross_metrics, out)
    except Exception as e:
        logger.warning(f"  Cross-plot B failed: {e}")
    try:
        saved["B+"] = plot_cross_experiment_f1_comparison(cross_metrics, out)
    except Exception as e:
        logger.warning(f"  Cross-plot B+ failed: {e}")
    for ds_key in ("eval", "test"):
        for metric in ("macro_f1", "mae"):
            try:
                saved[f"C_{metric}_{ds_key}"] = plot_category_heatmap(
                    cross_metrics, metric, out, ds_key
                )
            except Exception as e:
                logger.warning(f"  Cross-plot C ({metric}/{ds_key}) failed: {e}")
        
        # Field-level heatmaps (new)
        if cross_records:
            try:
                saved[f"C_field_{ds_key}"] = plot_field_heatmap(cross_records, out, ds_key)
            except Exception as e:
                logger.warning(f"  Cross-plot C_field ({ds_key}) failed: {e}")
            try:
                saved[f"C_field_mae_{ds_key}"] = plot_field_heatmap_mae(cross_records, out, ds_key)
            except Exception as e:
                logger.warning(f"  Cross-plot C_field_mae ({ds_key}) failed: {e}")
            try:
                saved[f"C_field_aggregated_{ds_key}"] = plot_field_heatmap_aggregated(cross_records, out, ds_key)
            except Exception as e:
                logger.warning(f"  Cross-plot C_field_aggregated ({ds_key}) failed: {e}")
            try:
                saved[f"C_field_mae_aggregated_{ds_key}"] = plot_field_heatmap_mae_aggregated(cross_records, out, ds_key)
            except Exception as e:
                logger.warning(f"  Cross-plot C_field_mae_aggregated ({ds_key}) failed: {e}")
        
        # Total FFA bar chart (GT + runs)
        try:
            saved[f"A_ffa_bars_{ds_key}"] = plot_cross_experiment_ffa_bars(cross_metrics, out, ds_key)
        except Exception as e:
            logger.warning(f"  Cross-plot A_ffa_bars ({ds_key}) failed: {e}")

        # Total FFA bar chart – runs only / Variationstest
        try:
            saved[f"A_ffa_bars_variationtest_{ds_key}"] = plot_cross_experiment_ffa_bars_variationtest(
                cross_metrics, out, ds_key
            )
        except Exception as e:
            logger.warning(f"  Cross-plot A_ffa_bars_variationtest ({ds_key}) failed: {e}")

        # Per-assembly variation (std dev + strip plot)
        try:
            saved[f"D_variation_{ds_key}"] = plot_assembly_variation(cross_metrics, out, ds_key)
        except Exception as e:
            logger.warning(f"  Cross-plot D_variation ({ds_key}) failed: {e}")

        # FFA deviation – std + 95% CI
        try:
            saved[f"E_ffa_deviation_{ds_key}"] = plot_ffa_deviation(
                cross_metrics, out, ds_key, stat_comparisons=stat_comparisons, run_label=run_label
            )
        except Exception as e:
            logger.warning(f"  Cross-plot E_ffa_deviation ({ds_key}) failed: {e}")

        # Ablation-study special: same E plot, but only the full system.
        try:
            saved[f"E_ffa_deviation_{ds_key}_Gesamtes_system_only"] = plot_ffa_deviation(
                cross_metrics,
                out,
                ds_key,
                stat_comparisons=stat_comparisons,
                run_label=run_label,
                include_groups=["Gesamtes_System"],
                filename_suffix="Gesamtes_system_only",
                group_label_overrides={"Gesamtes_System": "System-FfA"},
            )
        except Exception as e:
            logger.warning(f"  Cross-plot E_ffa_deviation full-system only ({ds_key}) failed: {e}")

        # Statistical tests – separate auto-sized figure
        if stat_comparisons:
            try:
                saved[f"E_stat_table_{ds_key}"] = plot_stat_table(
                    stat_comparisons, cross_metrics, out, ds_key, run_label=run_label
                )
            except Exception as e:
                logger.warning(f"  Cross-plot E_stat_table ({ds_key}) failed: {e}")

        # FFA grouped deviation – per experiment group, ±2 SD
        try:
            saved[f"F_ffa_grouped_{ds_key}"] = plot_ffa_grouped_deviation(cross_metrics, out, ds_key)
        except Exception as e:
            logger.warning(f"  Cross-plot F_ffa_grouped ({ds_key}) failed: {e}")

        # NEW G: FFA deviation grouped by experiment (one block per exp)
        try:
            saved[f"G_ffa_by_experiment_{ds_key}"] = plot_ffa_deviation_exp_grouped(cross_metrics, out, ds_key)
        except Exception as e:
            logger.warning(f"  Cross-plot G_ffa_by_experiment ({ds_key}) failed: {e}")

        # NEW H: FFA deviation overlaid by assembly (GT + all exp preds per row)
        try:
            saved[f"H_ffa_by_assembly_{ds_key}"] = plot_ffa_deviation_asm_overlaid(
                cross_metrics, out, ds_key, run_label=run_label
            )
        except Exception as e:
            logger.warning(f"  Cross-plot H_ffa_by_assembly ({ds_key}) failed: {e}")

    return saved


# ============================================================================
# DATA SCREENING – GT label distribution (eval vs test)
# ============================================================================

def plot_data_screening(
    eval_gt_dir: Path,
    test_gt_dir: Path,
    output_dir: Path,
) -> Dict[str, Path]:
    """
    Generate one bar chart per FFA category showing label distributions in
    eval set vs test set ground truth data.

    Each chart has one subplot per criterion within the category.
    Bars show how often each label (option ID) was annotated, split by dataset.

    Args:
        eval_gt_dir:  Path to ffa_ground_truth_evaluierungsdaten/
        test_gt_dir:  Path to ffa_ground_truth_testdaten/
        output_dir:   Root output dir – plots go into output_dir/data_screening/

    Returns:
        Dict mapping category name → saved Path.
    """
    import json
    import textwrap
    from collections import defaultdict

    from evaluation.ffa_scoring import (
        FIELD_TO_SUBPROCESS,
        SUBPROCESSES,
        FFA_FIELD_ORDER,
        load_scoring_mapping,
    )

    out_dir = Path(output_dir) / "data_screening"
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = load_scoring_mapping()

    # ----------------------------------------------------------------
    # 1.  Collect label counts:
    #     counts[dataset_label][field_name][option_id] = int
    # ----------------------------------------------------------------
    def _collect_counts(gt_dir: Path, label: str) -> Dict[str, Dict[int, int]]:
        counts: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        if not gt_dir.exists():
            logger.warning(f"  GT dir not found: {gt_dir}")
            return counts
        for json_file in sorted(gt_dir.glob("*_ffa_assessment_enum_gt.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    steps = json.load(f)
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    assessment = step.get("assessment", {})
                    for sp, fields in assessment.items():
                        if not isinstance(fields, dict):
                            continue
                        for field_name, option_id in fields.items():
                            if field_name in FIELD_TO_SUBPROCESS and isinstance(option_id, int):
                                counts[field_name][option_id] += 1
            except Exception as e:
                logger.warning(f"  Failed to read {json_file.name}: {e}")
        return counts

    ds_labels  = ["Eval Set", "Test Set"]
    ds_colors  = ["#F58220",  "#179C7D"]
    all_counts = {
        "Eval Set": _collect_counts(eval_gt_dir, "Eval Set"),
        "Test Set": _collect_counts(test_gt_dir, "Test Set"),
    }

    # ----------------------------------------------------------------
    # 2.  Group criteria by subprocess (category), preserving FFA_FIELD_ORDER
    # ----------------------------------------------------------------
    criteria_by_cat: Dict[str, List[str]] = {sp: [] for sp in SUBPROCESSES}
    for field in FFA_FIELD_ORDER:
        if field in FIELD_TO_SUBPROCESS:
            sp, _ = FIELD_TO_SUBPROCESS[field]
            criteria_by_cat[sp].append(field)

    saved: Dict[str, Path] = {}

    # Readable category titles
    cat_titles = {
        "separation": "Separation",
        "handling":   "Handling",
        "positioning": "Positioning",
        "joining":    "Joining",
    }

    # ----------------------------------------------------------------
    # 3.  One figure per category
    # ----------------------------------------------------------------
    for cat, fields in criteria_by_cat.items():
        if not fields:
            continue

        n_fields = len(fields)
        ncols = min(2, n_fields)
        nrows = math.ceil(n_fields / ncols)

        fig, axes = plt.subplots(
            nrows, ncols,
            figsize=(ncols * 7, nrows * 4.5),
            squeeze=False,
        )

        for ax_flat_idx in range(nrows * ncols):
            row, col = divmod(ax_flat_idx, ncols)
            ax = axes[row][col]
            if ax_flat_idx >= n_fields:
                ax.set_visible(False)
                continue

            field_name = fields[ax_flat_idx]
            sp_key, crit_key = FIELD_TO_SUBPROCESS[field_name]
            crit_meta = mapping.get(sp_key, {}).get(crit_key, {})
            criterion_label = crit_meta.get("_criterion_label", field_name)
            options = crit_meta.get("options", {})

            # All possible option IDs present in either dataset + defined in mapping
            all_ids = sorted(
                set(int(k) for k in options.keys()) |
                set(all_counts["Eval Set"][field_name].keys()) |
                set(all_counts["Test Set"][field_name].keys())
            )
            if not all_ids:
                ax.set_visible(False)
                continue

            n_ids = len(all_ids)
            bar_w = 0.35
            x = np.arange(n_ids)

            for ds_i, (ds_label, ds_color) in enumerate(zip(ds_labels, ds_colors)):
                counts_field = all_counts[ds_label][field_name]
                values = [counts_field.get(oid, 0) for oid in all_ids]
                offset = (ds_i - 0.5) * bar_w
                bars = ax.bar(
                    x + offset, values, bar_w,
                    label=ds_label, color=ds_color, alpha=0.85, edgecolor="white",
                )
                for bar, val in zip(bars, values):
                    if val > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + 0.1,
                            str(val), ha="center", va="bottom", fontsize=8,
                        )

            # X-tick labels: "ID: short label"
            tick_labels = []
            for oid in all_ids:
                raw_label = options.get(str(oid), {}).get("label", str(oid))
                # Wrap long labels to 2 lines
                wrapped = "\n".join(textwrap.wrap(raw_label, width=22))
                tick_labels.append(f"{oid}: {wrapped}")

            ax.set_xticks(x)
            ax.set_xticklabels(tick_labels, fontsize=7.5, ha="center")
            ax.set_ylabel("Count", fontsize=9)
            ax.set_xlabel("Option ID : Label", fontsize=9)
            ax.set_title(criterion_label, fontsize=10, fontweight="bold", pad=6)
            ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
            ax.grid(axis="y", alpha=0.3, linestyle="--")
            if ax_flat_idx == 0:
                ax.legend(fontsize=9)

        fig.suptitle(
            f"GT Label Distribution – {cat_titles[cat]}",
            fontsize=13, fontweight="bold", y=1.01,
        )
        fig.tight_layout()

        path = out_dir / f"data_screening_{cat}.png"
        _savefig(fig, path)
        saved[cat] = path
        logger.info(f"  data_screening/{path.name}")

    return saved
