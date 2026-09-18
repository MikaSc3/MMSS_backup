"""
Confusion Matrix Generation for FFA Fields

Generates per-config, per-field confusion matrices aggregated across all runs.
"""

import re
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix

from evaluation.ffa_evaluator import CriterionRecord
from evaluation.ffa_scoring import FFA_FIELD_ORDER, load_scoring_mapping

logger = logging.getLogger(__name__)


def compute_confusion_matrices_per_config(
    records_per_group: Dict[str, Dict[str, Dict[str, List[CriterionRecord]]]],
    output_dir: Path,
    dataset_key: str = "eval",
) -> Dict[str, Path]:
    """
    Generate confusion matrices for each config × field.
    
    Aggregates across all runs of each config.
    
    Args:
        records_per_group: {group_name: {run_id: {dataset_key: [records]}}}
        output_dir: Directory to save CMs (will create CM/{config_name}/ subdirs)
        dataset_key: "eval" or "test"
    
    Returns:
        Dict mapping "config/field" to Path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cm_root = output_dir / "CM"
    cm_root.mkdir(parents=True, exist_ok=True)
    
    # Load option mappings
    try:
        mapping = load_scoring_mapping()
    except Exception as e:
        logger.warning(f"Could not load mapping: {e}")
        mapping = {}
    
    saved_paths = {}
    
    # Group experiments by config name (strip _run\d+ suffix from group_name)
    config_runs: Dict[str, Dict[str, Dict[str, List]]] = defaultdict(lambda: defaultdict(dict))
    for group_name in sorted(records_per_group.keys()):
        config_name = re.sub(r"_run\d+$", "", group_name, flags=re.IGNORECASE)
        config_runs[config_name][group_name] = records_per_group[group_name]
    
    # Process each config
    for config_name in sorted(config_runs.keys()):
        group_run_map = config_runs[config_name]  # {group_name: {run_id: {dataset_key: [records]}}}
        config_dir = cm_root / config_name
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each field
        for field_name in FFA_FIELD_ORDER:
            try:
                # Collect all GT and Pred IDs for this field across all runs and groups
                gt_ids = []
                pred_ids = []
                
                for group_name in sorted(group_run_map.keys()):
                    run_id_map = group_run_map[group_name]  # {run_id: {dataset_key: [records]}}
                    for run_id in sorted(run_id_map.keys()):
                        records = run_id_map[run_id].get(dataset_key, [])
                        
                        for rec in records:
                            if rec.field_name == field_name and \
                               rec.gt_option_id is not None and \
                               rec.pred_option_id is not None:
                                gt_ids.append(rec.gt_option_id)
                                pred_ids.append(rec.pred_option_id)
                
                if not gt_ids or not pred_ids:
                    logger.debug(f"  No data for {config_name} / {field_name}")
                    continue
                
                # Build confusion matrix
                labels = sorted(set(gt_ids) | set(pred_ids))
                cm = confusion_matrix(gt_ids, pred_ids, labels=labels)
                
                # Get option names from mapping
                field_options = mapping.get(field_name, {}).get("options", {})
                
                def truncate_name(s: str, max_len: int = 40) -> str:
                    """Truncate string to max_len characters."""
                    return s[:max_len] + ("..." if len(s) > max_len else "")
                
                # Create labels: "ID: Name"
                label_names = []
                for lbl in labels:
                    name = field_options.get(str(lbl), f"Option {lbl}")
                    name = truncate_name(name, 40)
                    label_names.append(f"{lbl}: {name}")
                
                # Create seaborn heatmap
                fig, ax = plt.subplots(figsize=(10, 8))
                sns.heatmap(
                    cm, 
                    annot=True, 
                    fmt="d",
                    cmap="Blues",
                    xticklabels=label_names,
                    yticklabels=label_names,
                    cbar_kws={"label": "Count"},
                    ax=ax,
                )
                ax.set_xlabel("Predicted", fontsize=11, fontweight="bold")
                ax.set_ylabel("Ground Truth", fontsize=11, fontweight="bold")
                ax.set_title(
                    f"Confusion Matrix: {field_name} ({config_name})",
                    fontsize=12, fontweight="bold"
                )
                plt.tight_layout()
                
                # Save as PNG
                output_path = config_dir / f"{field_name}.png"
                plt.savefig(output_path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                
                saved_paths[f"{config_name}/{field_name}"] = output_path
                logger.info(f"  Saved: {output_path}")
                
            except Exception as e:
                logger.warning(f"  Failed to generate CM for {config_name}/{field_name}: {e}")
                continue
    
    logger.info(f"  Confusion matrices saved to {cm_root}")
    return saved_paths
