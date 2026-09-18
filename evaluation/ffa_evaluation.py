"""
FFA Evaluation - Ground Truth vs LLM Predictions

Berechnet Metriken (Accuracy, Precision, Recall, F1-Score) und Confusion Matrices
für FFA Assessment Daten (Ground Truth vs LLM Predictions).

Evaluation auf 3 Ebenen:
1. Per-Field (14 einzelne FFA-Felder)
2. Per-Subprocess (Separation, Handling, Positioning, Joining)
3. Aggregated (Overall Performance)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import warnings

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report
)
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

# Import from agent directory (dependencies remain there)
from agent.structured_output import FeedingOfJoiningElementOption

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')  # Suppress sklearn warnings for missing classes


# ============================================================================
# CONFIGURATION
# ============================================================================

# Subprocess Prefix Mapping
SUBPROCESS_PREFIX = {
    "separation": "1_Separation",
    "handling": "2_Handling",
    "positioning": "3_Positioning",
    "joining": "4_Joining"
}

def get_field_prefix(field_name: str) -> str:
    """Gibt Subprocess-Präfix für einen Field-Namen zurück (z.B. '2_Handling_')."""
    for subprocess, fields in SUBPROCESS_MAPPING.items():
        if field_name in fields:
            return f"{SUBPROCESS_PREFIX[subprocess]}_"
    return ""  # Fallback

# Field → Subprocess Mapping
SUBPROCESS_MAPPING = {
    "separation": ["nature_of_provision"],
    "handling": ["part_rigidity", "gripping_areas", "orientation_features", "surface_sensibility"],
    "positioning": [
        "accuracy_of_target_position",
        "positioning_aids",
        "additional_orientation_by_rotation",
        "accessibility_to_joining_position",
        "positioning_motion",
        "positioning_tolerances",
        "stability_in_positioned_state"
    ],
    "joining": ["feeding_of_joining_element", "fixing_of_mounted_part"]
}

# All FFA fields (flat list)
ALL_FFA_FIELDS = [field for fields in SUBPROCESS_MAPPING.values() for field in fields]

# Field → Enum Class Name Mapping (same as in ffa_str_to_enum.py)
FIELD_TO_ENUM = {
    # Separation
    "nature_of_provision": "NatureOfProvisionOption",
    
    # Handling
    "part_rigidity": "PartRigidityOption",
    "gripping_areas": "GrippingAreasOption",
    "orientation_features": "OrientationFeaturesOption",
    "surface_sensibility": "SurfaceSensibilityOption",
    
    # Positioning
    "accuracy_of_target_position": "AccuracyOfTargetPositionOption",
    "positioning_aids": "PositioningAidsOption",
    "additional_orientation_by_rotation": "AdditionalOrientationByRotationOption",
    "accessibility_to_joining_position": "AccessibilityToJoiningPositionOption",
    "positioning_motion": "PositioningMotionOption",
    "positioning_tolerances": "PositioningTolerancesOption",
    "stability_in_positioned_state": "StabilityInPositionedStateOption",
    
    # Joining
    "feeding_of_joining_element": "FeedingOfJoiningElementOption",
    "fixing_of_mounted_part": "FixingOfMountedPartOption",
}


# ============================================================================
# DATA LOADING
# ============================================================================

def load_enum_mapping(enum_mapping_path: Path) -> Dict[str, Dict[str, int]]:
    """
    Lädt ffa_enum_mapping.json.
    
    Args:
        enum_mapping_path: Pfad zu ffa_enum_mapping.json
    
    Returns:
        Enum-Mapping Dictionary (String → Int)
    """
    with open(enum_mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    
    logger.info(f"Loaded enum mapping with {len(mapping)} enum classes")
    return mapping


def create_reverse_enum_mapping(enum_mapping: Dict[str, Dict[str, int]]) -> Dict[str, Dict[int, str]]:
    """
    Erstellt reverse mapping (Int → String) für jedes Enum.
    
    Args:
        enum_mapping: String → Int mapping
    
    Returns:
        Dict: {enum_class: {int: string}}
    """
    reverse_mapping = {}
    
    for enum_class, str_to_int in enum_mapping.items():
        reverse_mapping[enum_class] = {v: k for k, v in str_to_int.items()}
    
    return reverse_mapping

def load_ground_truth(ground_truth_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lädt alle Ground Truth Files aus ground_truth/ Ordner.
    
    Args:
        ground_truth_dir: Pfad zu data/evaluation/ground_truth/
    
    Returns:
        Dict: {assembly_name: step_assessments_list}
    """
    ground_truth_data = {}
    
    if not ground_truth_dir.exists():
        logger.error(f"Ground truth directory does not exist: {ground_truth_dir}")
        return ground_truth_data
    
    # Look for both *_enum.json and *_enum_gt.json files
    gt_files = list(ground_truth_dir.glob("*_ffa_assessment_enum*.json"))
    # Exclude the mapping file
    gt_files = [f for f in gt_files if f.name != "ffa_enum_mapping.json"]
    
    for gt_file in gt_files:
        # Extract assembly name (remove _ffa_assessment_enum.json or _ffa_assessment_enum_gt.json)
        assembly_name = gt_file.name
        assembly_name = assembly_name.replace("_ffa_assessment_enum_gt.json", "")
        assembly_name = assembly_name.replace("_ffa_assessment_enum.json", "")
        
        try:
            with open(gt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract step_assessments
            if isinstance(data, dict) and "step_assessments" in data:
                ground_truth_data[assembly_name] = data["step_assessments"]
            elif isinstance(data, list):
                ground_truth_data[assembly_name] = data
            else:
                logger.warning(f"Unexpected structure in {gt_file}")
        
        except Exception as e:
            logger.error(f"Failed to load ground truth {gt_file}: {e}")
    
    logger.info(f"Loaded ground truth for {len(ground_truth_data)} assemblies")
    return ground_truth_data


def load_predictions(predictions_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lädt alle Prediction Files aus evaluation run Ordner.
    
    Args:
        predictions_dir: Pfad zu data/evaluation/run_*/
    
    Returns:
        Dict: {assembly_name: step_assessments_list}
    """
    predictions_data = {}
    
    if not predictions_dir.exists():
        logger.error(f"Predictions directory does not exist: {predictions_dir}")
        return predictions_data
    
    pred_files = list(predictions_dir.glob("*_ffa_assessment_enum.json"))
    
    for pred_file in pred_files:
        assembly_name = pred_file.name.replace("_ffa_assessment_enum.json", "")
        
        try:
            with open(pred_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract step_assessments
            if isinstance(data, dict) and "step_assessments" in data:
                predictions_data[assembly_name] = data["step_assessments"]
            elif isinstance(data, list):
                predictions_data[assembly_name] = data
            else:
                logger.warning(f"Unexpected structure in {pred_file}")
        
        except Exception as e:
            logger.error(f"Failed to load prediction {pred_file}: {e}")
    
    logger.info(f"Loaded predictions for {len(predictions_data)} assemblies")
    return predictions_data


# ============================================================================
# STEP MATCHING
# ============================================================================

def match_steps(
    ground_truth: Dict[str, List[Dict[str, Any]]],
    predictions: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, List[Tuple[Dict, Dict]]]:
    """
    Matched Ground Truth Steps mit Prediction Steps per Assembly + Step-ID.
    
    Args:
        ground_truth: GT data per assembly
        predictions: Prediction data per assembly
    
    Returns:
        Dict: {assembly_name: [(gt_step, pred_step), ...]}
    """
    matched_data = {}
    
    # Find common assemblies
    common_assemblies = set(ground_truth.keys()) & set(predictions.keys())
    
    if not common_assemblies:
        logger.error("No common assemblies found between GT and Predictions!")
        return matched_data
    
    for assembly_name in common_assemblies:
        gt_steps = ground_truth[assembly_name]
        pred_steps = predictions[assembly_name]
        
        # Create step_id lookup for predictions
        pred_by_id = {step.get("step_id"): step for step in pred_steps}
        
        matched_steps = []
        unmatched_count = 0
        
        for gt_step in gt_steps:
            step_id = gt_step.get("step_id")
            
            if step_id in pred_by_id:
                matched_steps.append((gt_step, pred_by_id[step_id]))
            else:
                unmatched_count += 1
                logger.warning(f"Assembly: {assembly_name} | Step {step_id} not found in predictions")
        
        if unmatched_count > 0:
            print(f"\n⚠ ACHTUNG {assembly_name}: {unmatched_count} Steps NOT MATCHING")
        
        matched_data[assembly_name] = matched_steps
        logger.info(f"Matched {len(matched_steps)} steps for {assembly_name}")
    
    return matched_data


# ============================================================================
# METRICS CALCULATION - PER FIELD
# ============================================================================

def extract_field_values(
    matched_data: Dict[str, List[Tuple[Dict, Dict]]],
    field_name: str,
    subprocess_name: str
) -> Tuple[List[int], List[int], List[str]]:
    """
    Extrahiert Ground Truth und Predicted Values für ein spezifisches FFA-Feld.
    
    Ignoriert null-Werte (Option A: nur non-null evaluieren).
    
    Args:
        matched_data: Matched steps per assembly
        field_name: z.B. "nature_of_provision"
        subprocess_name: z.B. "separation"
    
    Returns:
        Tuple: (y_true, y_pred, assembly_step_ids)
        - y_true: Ground truth values (integers)
        - y_pred: Predicted values (integers)
        - assembly_step_ids: ["assembly_name:step_id", ...] for error tracking
    """
    y_true = []
    y_pred = []
    assembly_step_ids = []
    
    for assembly_name, matched_steps in matched_data.items():
        for gt_step, pred_step in matched_steps:
            step_id = gt_step.get("step_id", "?")
            
            # Extract values from assessment dict
            gt_assessment = gt_step.get("assessment", {})
            pred_assessment = pred_step.get("assessment", {})
            
            if gt_assessment is None or pred_assessment is None:
                continue
            
            gt_subprocess = gt_assessment.get(subprocess_name, {})
            pred_subprocess = pred_assessment.get(subprocess_name, {})
            
            if gt_subprocess is None or pred_subprocess is None:
                continue
            
            gt_value = gt_subprocess.get(field_name)
            pred_value = pred_subprocess.get(field_name)
            
            # Ignore null values (0 in our encoding)
            if gt_value is None or gt_value == 0 or pred_value is None or pred_value == 0:
                continue
            
            y_true.append(gt_value)
            y_pred.append(pred_value)
            assembly_step_ids.append(f"{assembly_name}:{step_id}")
    
    return y_true, y_pred, assembly_step_ids


def calculate_field_metrics(
    y_true: List[int],
    y_pred: List[int],
    field_name: str,
    assembly_step_ids: List[str],
    all_possible_labels: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Berechnet Metriken für ein einzelnes FFA-Feld.
    
    Args:
        y_true: Ground truth values
        y_pred: Predicted values
        field_name: Field name
        assembly_step_ids: Assembly:Step-ID mapping for misclassifications
        all_possible_labels: Alle möglichen Klassen (für volle CM Größe)
    
    Returns:
        Dict mit Metriken
    """
    if len(y_true) == 0:
        return {
            "field_name": field_name,
            "support": 0,
            "accuracy": None,
            "precision_macro": None,
            "recall_macro": None,
            "f1_macro": None,
            "confusion_matrix": None,
            "all_possible_labels": all_possible_labels,
            "misclassifications": []
        }
    
    # Calculate metrics
    accuracy = accuracy_score(y_true, y_pred)
    
    # Macro-averaged metrics (equal weight to each class)
    precision_macro = precision_score(y_true, y_pred, average='macro', zero_division=0)
    recall_macro = recall_score(y_true, y_pred, average='macro', zero_division=0)
    f1_macro = f1_score(y_true, y_pred, average='macro', zero_division=0)
    
    # Confusion matrix with ALL possible labels for consistent size
    if all_possible_labels is not None:
        cm = confusion_matrix(y_true, y_pred, labels=all_possible_labels)
    else:
        cm = confusion_matrix(y_true, y_pred)
    
    # Find misclassifications
    misclassifications = []
    for i, (gt, pred, step_id) in enumerate(zip(y_true, y_pred, assembly_step_ids)):
        if gt != pred:
            assembly_name, step_num = step_id.split(":")
            # Remove "Step" prefix if present
            if step_num.startswith("Step"):
                step_num = step_num[4:]  # Remove "Step" prefix
            misclassifications.append({
                "assembly": assembly_name,
                "step_id": int(step_num),
                "ground_truth": int(gt),
                "predicted": int(pred)
            })
    
    return {
        "field_name": field_name,
        "support": len(y_true),
        "accuracy": float(accuracy),
        "precision_macro": float(precision_macro),
        "recall_macro": float(recall_macro),
        "f1_macro": float(f1_macro),
        "confusion_matrix": cm.tolist(),
        "unique_classes": sorted(set(y_true) | set(y_pred)),
        "all_possible_labels": all_possible_labels,
        "misclassifications": misclassifications
    }


def calculate_metrics_per_field(
    matched_data: Dict[str, List[Tuple[Dict, Dict]]],
    enum_mapping: Optional[Dict[str, Dict[str, int]]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Berechnet Metriken für alle 14 FFA-Felder.
    
    Args:
        matched_data: Matched GT and Prediction steps
        enum_mapping: Enum mapping (String → Int) für volle CM Größe
    
    Returns:
        Dict: {field_name: metrics_dict}
    """
    field_metrics = {}
    
    for subprocess_name, field_names in SUBPROCESS_MAPPING.items():
        for field_name in field_names:
            y_true, y_pred, assembly_step_ids = extract_field_values(
                matched_data, field_name, subprocess_name
            )
            
            # Get all possible labels for this field from enum mapping
            all_possible_labels = None
            if enum_mapping and field_name in FIELD_TO_ENUM:
                enum_class_name = FIELD_TO_ENUM[field_name]
                if enum_class_name in enum_mapping:
                    # Get all integer values (1, 2, 3, ..., N) for this enum
                    all_possible_labels = sorted(enum_mapping[enum_class_name].values())
            
            # Use subprocess.field_name as key to avoid duplicates (e.g. automatable appears 4x)
            field_key = f"{subprocess_name}.{field_name}"
            
            # Debug: Print if automatable field
            if field_name == "automatable":
                logger.info(f"Processing {field_key}: {len(y_true)} samples")
            
            metrics = calculate_field_metrics(
                y_true, y_pred, field_name, assembly_step_ids, all_possible_labels
            )
            field_metrics[field_key] = metrics
    
    return field_metrics


# ============================================================================
# METRICS CALCULATION - AGGREGATED
# ============================================================================

def calculate_metrics_aggregated(
    field_metrics: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Berechnet aggregierte Metriken über alle Felder.
    
    Args:
        field_metrics: Per-field metrics
    
    Returns:
        Dict mit aggregierten Metriken
    """
    # Collect all non-null metrics
    accuracies = []
    f1_scores = []
    supports = []
    
    for field_name, metrics in field_metrics.items():
        if metrics["support"] > 0:
            accuracies.append(metrics["accuracy"])
            f1_scores.append(metrics["f1_macro"])
            supports.append(metrics["support"])
    
    if len(accuracies) == 0:
        return {
            "overall_accuracy_mean": None,
            "overall_f1_macro_mean": None,
            "total_samples": 0,
            "fields_evaluated": 0
        }
    
    # Weighted by support
    total_support = sum(supports)
    weighted_accuracy = sum(acc * sup for acc, sup in zip(accuracies, supports)) / total_support
    weighted_f1 = sum(f1 * sup for f1, sup in zip(f1_scores, supports)) / total_support
    
    return {
        "overall_accuracy_mean": float(np.mean(accuracies)),
        "overall_accuracy_weighted": float(weighted_accuracy),
        "overall_f1_macro_mean": float(np.mean(f1_scores)),
        "overall_f1_macro_weighted": float(weighted_f1),
        "total_samples": total_support,
        "fields_evaluated": len(accuracies)
    }


# ============================================================================
# METRICS CALCULATION - PER SUBPROCESS
# ============================================================================

def calculate_metrics_per_subprocess(
    field_metrics: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Berechnet aggregierte Metriken pro Subprocess (Separation, Handling, Positioning, Joining).
    
    Args:
        field_metrics: Per-field metrics
    
    Returns:
        Dict: {subprocess_name: metrics_dict}
    """
    subprocess_metrics = {}
    
    for subprocess_name, field_names in SUBPROCESS_MAPPING.items():
        subprocess_accuracies = []
        subprocess_f1_scores = []
        subprocess_supports = []
        
        for field_name in field_names:
            if field_name in field_metrics and field_metrics[field_name]["support"] > 0:
                subprocess_accuracies.append(field_metrics[field_name]["accuracy"])
                subprocess_f1_scores.append(field_metrics[field_name]["f1_macro"])
                subprocess_supports.append(field_metrics[field_name]["support"])
        
        if len(subprocess_accuracies) > 0:
            total_support = sum(subprocess_supports)
            weighted_accuracy = sum(acc * sup for acc, sup in zip(subprocess_accuracies, subprocess_supports)) / total_support
            weighted_f1 = sum(f1 * sup for f1, sup in zip(subprocess_f1_scores, subprocess_supports)) / total_support
            
            subprocess_metrics[subprocess_name] = {
                "accuracy_mean": float(np.mean(subprocess_accuracies)),
                "accuracy_weighted": float(weighted_accuracy),
                "f1_macro_mean": float(np.mean(subprocess_f1_scores)),
                "f1_macro_weighted": float(weighted_f1),
                "total_samples": total_support,
                "fields_evaluated": len(subprocess_accuracies)
            }
        else:
            subprocess_metrics[subprocess_name] = {
                "accuracy_mean": None,
                "accuracy_weighted": None,
                "f1_macro_mean": None,
                "f1_macro_weighted": None,
                "total_samples": 0,
                "fields_evaluated": 0
            }
    
    return subprocess_metrics


# ============================================================================
# METRICS CALCULATION - PER ASSEMBLY
# ============================================================================

def calculate_metrics_per_assembly(
    matched_data: Dict[str, List[Tuple[Dict, Dict]]],
    enum_mapping: Optional[Dict[str, Dict[str, int]]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Berechnet Metriken pro Assembly mit per-field Confusion Matrices.
    
    Verwendet die gleiche Struktur wie calculate_metrics_per_field,
    aber für jedes Assembly separat.
    
    Args:
        matched_data: Matched GT and Prediction steps per assembly
        enum_mapping: Enum mapping für full-size confusion matrices
    
    Returns:
        Dict: {assembly_name: {field_metrics, overall_metrics}}
    """
    assembly_metrics = {}
    
    for assembly_name, matched_steps in matched_data.items():
        # Calculate per-field metrics for this assembly (same structure as global)
        field_metrics = {}
        
        for subprocess_name, field_names in SUBPROCESS_MAPPING.items():
            for field_name in field_names:
                # Extract field values for this assembly
                y_true = []
                y_pred = []
                assembly_step_ids = []
                
                for gt_step, pred_step in matched_steps:
                    # Get assessment dictionaries
                    gt_subprocess = gt_step.get("assessment", {}).get(subprocess_name)
                    pred_subprocess = pred_step.get("assessment", {}).get(subprocess_name)
                    
                    if gt_subprocess is None:
                        continue
                    if pred_subprocess is None:
                        pred_subprocess = {}
                    
                    gt_value = gt_subprocess.get(field_name, 0)
                    pred_value = pred_subprocess.get(field_name, 0)
                    
                    # Only include if ground truth has a value
                    if gt_value != 0:
                        y_true.append(gt_value)
                        y_pred.append(pred_value)
                        assembly_step_ids.append(f"{assembly_name}:Step{gt_step.get('step_id', '?')}")
                
                # Get all possible labels for this field
                all_possible_labels = None
                if enum_mapping and field_name in FIELD_TO_ENUM:
                    enum_class_name = FIELD_TO_ENUM[field_name]
                    if enum_class_name in enum_mapping:
                        all_possible_labels = sorted(enum_mapping[enum_class_name].values())
                
                # Calculate metrics for this field
                # Use subprocess.field_name as key to avoid duplicates
                field_key = f"{subprocess_name}.{field_name}"
                metrics = calculate_field_metrics(
                    y_true, y_pred, field_name, assembly_step_ids, all_possible_labels
                )
                field_metrics[field_key] = metrics
        
        # Calculate overall metrics for this assembly
        y_true_all = []
        y_pred_all = []
        
        for field_name, metrics in field_metrics.items():
            if metrics["support"] > 0:
                y_true_all.extend([1] * metrics["support"])  # Placeholder for overall metrics
                # We can't really combine different fields, so we just track counts
        
        total_support = sum(m["support"] for m in field_metrics.values() if m["support"] > 0)
        
        if total_support > 0:
            # Calculate aggregated metrics for this assembly
            accuracies = [m["accuracy"] for m in field_metrics.values() if m["support"] > 0]
            f1_scores = [m["f1_macro"] for m in field_metrics.values() if m["support"] > 0]
            
            assembly_metrics[assembly_name] = {
                "assembly_name": assembly_name,
                "field_metrics": field_metrics,
                "overall_accuracy_mean": float(np.mean(accuracies)),
                "overall_f1_macro_mean": float(np.mean(f1_scores)),
                "total_support": total_support,
                "fields_evaluated": len(accuracies),
                "num_steps": len(matched_steps)
            }
        else:
            assembly_metrics[assembly_name] = {
                "assembly_name": assembly_name,
                "field_metrics": {},
                "overall_accuracy_mean": None,
                "overall_f1_macro_mean": None,
                "total_support": 0,
                "fields_evaluated": 0,
                "num_steps": len(matched_steps)
            }
        
        logger.info(f"Assembly '{assembly_name}': {total_support} values across {len(accuracies) if total_support > 0 else 0} fields")
    
    return assembly_metrics


# ============================================================================
# VISUALIZATION - CONFUSION MATRICES
# ============================================================================

def plot_confusion_matrix(
    cm: np.ndarray,
    class_labels: List[int],
    field_name: str,
    output_path: Path,
    label_mode: str = 'str',
    reverse_mapping: Optional[Dict[str, Dict[int, str]]] = None,
    assembly_name: Optional[str] = None
) -> None:
    """
    Erstellt und speichert Confusion Matrix Plot.
    
    Args:
        cm: Confusion matrix
        class_labels: All possible class labels (integers)
        field_name: Field name for title
        output_path: Output PNG path
        label_mode: 'enum' für Zahlen, 'str' für String-Labels
        reverse_mapping: Reverse enum mapping (Int → String) für 'str' mode
        assembly_name: Optional assembly name (None = all assemblies)
    """
    # Convert labels to strings if mode is 'str'
    display_labels = class_labels
    if label_mode == 'str' and reverse_mapping is not None:
        # Get enum class name for this field
        enum_class = FIELD_TO_ENUM.get(field_name)
        if enum_class and enum_class in reverse_mapping:
            # Format: [1] string_label (max 20 chars for string part)
            display_labels = []
            for label in class_labels:
                label_str = reverse_mapping[enum_class].get(label, str(label))
                # Limit string to 20 characters
                if len(label_str) > 20:
                    label_str = label_str[:17] + "..."
                display_labels.append(f"[{label}] {label_str}")
    
    # Dynamic figure size based on number of classes
    size = max(8, len(class_labels) * 0.8)
    plt.figure(figsize=(size, size * 0.9))
    
    # Create custom colormap: White -> Green
    white_color = "#FFFFFF"  # White
    green_color = "#179C7D"  # Green
    
    colors = [white_color, green_color]
    n_bins = 256
    cmap = LinearSegmentedColormap.from_list('white_green', colors, N=n_bins)
    
    # Use seaborn for better visualization
    sns.heatmap(
        cm,
        annot=True,
        fmt='d',
        cmap=cmap,
        xticklabels=display_labels,
        yticklabels=display_labels,
        cbar_kws={'label': 'Count'}
    )
    
    # Title with assembly context
    title = f'Confusion Matrix: {field_name}'
    if assembly_name:
        title += f' ({assembly_name})'
    else:
        title += ' (All Assemblies)'
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('Predicted', fontsize=12)
    plt.ylabel('Ground Truth', fontsize=12)
    plt.tight_layout()
    
    # Save figure
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved confusion matrix plot: {output_path}")


def plot_f1_scores_bar(
    field_metrics: Dict[str, Dict[str, Any]],
    output_path: Path,
    assembly_name: Optional[str] = None
) -> None:
    """
    Erstellt Balkendiagramm mit F1-Scores für alle Felder.
    
    Args:
        field_metrics: Per-field metrics
        output_path: Output PNG path
        assembly_name: Optional assembly name (None = all assemblies)
    """
    # Extract field names and f1 scores
    field_names = []
    f1_scores = []
    
    for field_name, metrics in field_metrics.items():
        if metrics["support"] > 0 and metrics["f1_macro"] is not None:
            field_names.append(field_name)
            f1_scores.append(metrics["f1_macro"])
    
    if len(field_names) == 0:
        logger.warning("No F1 scores to plot")
        return
    
    # Create figure
    plt.figure(figsize=(12, 6))
    
    # Create bar plot (Orange)
    bars = plt.bar(range(len(field_names)), f1_scores, color='#F58220', edgecolor='black')
    
    # Add value labels on bars
    for i, (bar, score) in enumerate(zip(bars, f1_scores)):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                f'{score:.3f}', ha='center', va='bottom', fontsize=9)
    
    plt.xlabel('FFA Field', fontsize=12)
    plt.ylabel('F1-Score (Macro)', fontsize=12)
    title = 'F1-Scores per FFA Field'
    if assembly_name:
        title += f' ({assembly_name})'
    else:
        title += ' (All Assemblies)'
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xticks(range(len(field_names)), field_names, rotation=45, ha='right')
    plt.ylim(0, 1.1)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    # Save figure
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved F1-scores bar plot: {output_path}")


def plot_subprocess_comparison(
    subprocess_metrics: Dict[str, Dict[str, Any]],
    output_path: Path
) -> None:
    """
    Erstellt Balkendiagramm mit F1-Scores pro Subprocess.
    
    Args:
        subprocess_metrics: Per-subprocess metrics
        output_path: Output PNG path
    """
    subprocess_names = []
    f1_scores_mean = []
    f1_scores_weighted = []
    
    for subprocess_name, metrics in subprocess_metrics.items():
        if metrics["fields_evaluated"] > 0:
            subprocess_names.append(subprocess_name.capitalize())
            f1_scores_mean.append(metrics["f1_macro_mean"])
            f1_scores_weighted.append(metrics["f1_macro_weighted"])
    
    if len(subprocess_names) == 0:
        logger.warning("No subprocess metrics to plot")
        return
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(subprocess_names))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, f1_scores_mean, width, label='Mean', color='#F58220', edgecolor='black')
    bars2 = ax.bar(x + width/2, f1_scores_weighted, width, label='Weighted', color='#F58220', edgecolor='black', alpha=0.7)
    
    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, height + 0.01,
                   f'{height:.3f}', ha='center', va='bottom', fontsize=9)
    
    ax.set_xlabel('Subprocess', fontsize=12)
    ax.set_ylabel('F1-Score (Macro)', fontsize=12)
    ax.set_title('F1-Scores per Subprocess', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(subprocess_names)
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved subprocess comparison plot: {output_path}")


def plot_assembly_comparison(
    assembly_metrics: Dict[str, Dict[str, Any]],
    output_path: Path
) -> None:
    """
    Erstellt Balkendiagramm mit F1-Scores pro Assembly.
    
    Args:
        assembly_metrics: Per-assembly metrics
        output_path: Output PNG path
    """
    assembly_names = []
    f1_scores = []
    accuracies = []
    
    for assembly_name, metrics in assembly_metrics.items():
        if metrics["total_support"] > 0:
            assembly_names.append(assembly_name)
            f1_scores.append(metrics["overall_f1_macro_mean"])
            accuracies.append(metrics["overall_accuracy_mean"])
    
    if len(assembly_names) == 0:
        logger.warning("No assembly metrics to plot")
        return
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(assembly_names))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, f1_scores, width, label='F1-Score', color='#F58220', edgecolor='black')
    bars2 = ax.bar(x + width/2, accuracies, width, label='Accuracy', color='#179C7D', edgecolor='black')
    
    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, height + 0.01,
                   f'{height:.3f}', ha='center', va='bottom', fontsize=9)
    
    ax.set_xlabel('Assembly', fontsize=12)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_title('Performance per Assembly', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(assembly_names, rotation=45, ha='right')
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved assembly comparison plot: {output_path}")


# ============================================================================
# STEP-BY-STEP EVALUATION
# ============================================================================

def generate_step_by_step_evaluation(
    matched_data: Dict[str, List[Tuple[Dict, Dict]]],
    reverse_mapping: Dict[str, Dict[int, str]],
    step_analysis_dir: Path,
    per_assembly_dir: Path
) -> None:
    """
    Generiert detaillierte Step-by-Step Evaluation mit Field-level Vergleichen.
    
    Args:
        matched_data: Matched GT and Prediction steps per assembly
        reverse_mapping: Reverse enum mapping (Int → String) für Labels
        step_analysis_dir: Output directory für globale Step-Analysis Reports
        per_assembly_dir: Output directory für per-assembly Reports
    """
    import pandas as pd
    
    all_step_evaluations = []
    
    # Für jede Assembly
    for assembly_name, matched_steps in matched_data.items():
        for gt_step, pred_step in matched_steps:
            step_id = gt_step.get("step_id", "?")
            step_desc = gt_step.get("step_description", "")
            
            fields_correct = 0
            fields_incorrect = 0
            fields_evaluated = 0
            field_comparisons = {}
            
            # Vergleiche alle Felder
            for subprocess_name, field_names in SUBPROCESS_MAPPING.items():
                gt_subprocess = gt_step.get("assessment", {}).get(subprocess_name)
                pred_subprocess = pred_step.get("assessment", {}).get(subprocess_name)
                
                if gt_subprocess is None:
                    continue
                
                for field_name in field_names:
                    gt_value = gt_subprocess.get(field_name, 0)
                    pred_value = pred_subprocess.get(field_name, 0) if pred_subprocess else 0
                    
                    # Nur evaluieren wenn GT ≠ 0
                    if gt_value == 0:
                        continue
                    
                    fields_evaluated += 1
                    match = (gt_value == pred_value)
                    
                    if match:
                        fields_correct += 1
                    else:
                        fields_incorrect += 1
                    
                    # Labels holen
                    field_key = f"{subprocess_name}.{field_name}"
                    enum_class_name = FIELD_TO_ENUM.get(field_name)
                    
                    gt_label = str(gt_value)
                    pred_label = str(pred_value)
                    
                    if enum_class_name and enum_class_name in reverse_mapping:
                        gt_str = reverse_mapping[enum_class_name].get(gt_value, str(gt_value))
                        pred_str = reverse_mapping[enum_class_name].get(pred_value, str(pred_value))
                        
                        # Kürze auf 30 Zeichen
                        if len(gt_str) > 30:
                            gt_str = gt_str[:27] + "..."
                        if len(pred_str) > 30:
                            pred_str = pred_str[:27] + "..."
                        
                        gt_label = f"[{gt_value}] {gt_str}"
                        pred_label = f"[{pred_value}] {pred_str}"
                    
                    field_comparisons[field_key] = {
                        "match": match,
                        "gt_value": int(gt_value),
                        "pred_value": int(pred_value),
                        "gt_label": gt_label,
                        "pred_label": pred_label
                    }
            
            step_accuracy = fields_correct / fields_evaluated if fields_evaluated > 0 else 0.0
            
            step_eval = {
                "assembly_name": assembly_name,
                "step_id": step_id,
                "step_description": step_desc,
                "step_accuracy": round(step_accuracy, 3),
                "fields_evaluated": fields_evaluated,
                "fields_correct": fields_correct,
                "fields_incorrect": fields_incorrect,
                "field_comparisons": field_comparisons
            }
            
            all_step_evaluations.append(step_eval)
    
    if not all_step_evaluations:
        logger.warning("No step evaluations to save")
        return
    
    # Berechne Error Summary
    field_error_counts = {}
    step_accuracies = [(s["assembly_name"], s["step_id"], s["step_accuracy"]) for s in all_step_evaluations]
    
    for step_eval in all_step_evaluations:
        for field_key, comparison in step_eval["field_comparisons"].items():
            if not comparison["match"]:
                field_error_counts[field_key] = field_error_counts.get(field_key, 0) + 1
    
    # Sortiere nach Fehleranzahl
    most_problematic_fields = sorted(field_error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    most_problematic_steps = sorted(step_accuracies, key=lambda x: x[2])[:10]
    
    overall_step_accuracy = sum(s["step_accuracy"] for s in all_step_evaluations) / len(all_step_evaluations)
    
    summary = {
        "total_steps": len(all_step_evaluations),
        "overall_step_accuracy": round(overall_step_accuracy, 3),
        "step_evaluations": all_step_evaluations,
        "error_summary": {
            "most_problematic_fields": [{"field": f, "error_count": c} for f, c in most_problematic_fields],
            "most_problematic_steps": [{"assembly": a, "step_id": s, "accuracy": acc} for a, s, acc in most_problematic_steps]
        }
    }
    
    # Save JSON
    json_path = step_analysis_dir / "step_by_step_evaluation.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved step-by-step evaluation JSON: {json_path}")
    
    # Generate Excel Report
    generate_step_evaluation_excel(all_step_evaluations, step_analysis_dir)
    
    # Generate Heatmaps
    generate_step_accuracy_heatmap(all_step_evaluations, step_analysis_dir, title_suffix="All Assemblies")
    generate_field_accuracy_summary_heatmap(all_step_evaluations, step_analysis_dir)
    
    # Generate per-assembly heatmaps
    assemblies = {}
    for step_eval in all_step_evaluations:
        assembly_name = step_eval["assembly_name"]
        if assembly_name not in assemblies:
            assemblies[assembly_name] = []
        assemblies[assembly_name].append(step_eval)
    
    for assembly_name, assembly_steps in assemblies.items():
        assembly_dir = per_assembly_dir / assembly_name.replace(" ", "_")
        assembly_step_dir = assembly_dir / "step_analysis"
        assembly_step_dir.mkdir(parents=True, exist_ok=True)
        generate_step_accuracy_heatmap(assembly_steps, assembly_step_dir, title_suffix=assembly_name)
        generate_field_accuracy_summary_heatmap(assembly_steps, assembly_step_dir, title_suffix=assembly_name)
    
    logger.info(f"✓ Step-by-step evaluation complete")


def generate_step_evaluation_excel(step_evaluations: List[Dict], output_dir: Path) -> None:
    """Erstellt Excel Report mit farbcodierten Zellen."""
    try:
        import pandas as pd
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill
        
        # Erstelle DataFrame
        rows = []
        for step_eval in step_evaluations:
            row = {
                "Assembly": step_eval["assembly_name"],
                "Step": step_eval["step_id"],
                "Description": step_eval["step_description"][:50],
                "Accuracy": step_eval["step_accuracy"],
                "Correct": step_eval["fields_correct"],
                "Incorrect": step_eval["fields_incorrect"],
                "Total": step_eval["fields_evaluated"]
            }
            
            # Füge Field-Comparisons hinzu
            for field_key, comp in step_eval["field_comparisons"].items():
                row[field_key] = "✓" if comp["match"] else f"✗ ({comp['gt_label']} vs {comp['pred_label']})"
            
            rows.append(row)
        
        df = pd.DataFrame(rows)
        excel_path = output_dir / "step_by_step_evaluation.xlsx"
        df.to_excel(excel_path, index=False, engine='openpyxl')
        
        logger.info(f"Saved step-by-step Excel: {excel_path}")
    
    except Exception as e:
        logger.warning(f"Could not generate Excel report: {e}")


def generate_step_accuracy_heatmap(step_evaluations: List[Dict], output_dir: Path, title_suffix: str = "All Assemblies") -> None:
    """Erstellt Heatmap: Steps × Fields mit Match/Mismatch Farbcodierung."""
    import pandas as pd
    
    # Erstelle Matrix: Rows = Steps, Columns = Fields
    step_labels = []
    
    # Sortiere field_keys nach Subprocess-Reihenfolge (nicht alphabetisch)
    ordered_field_keys = []
    for subprocess_name in ["separation", "handling", "positioning", "joining"]:
        if subprocess_name in SUBPROCESS_MAPPING:
            for field_name in SUBPROCESS_MAPPING[subprocess_name]:
                field_key = f"{subprocess_name}.{field_name}"
                ordered_field_keys.append(field_key)
    
    # Nur Fields verwenden, die tatsächlich in den Daten vorkommen
    available_fields = set(k for s in step_evaluations for k in s["field_comparisons"].keys())
    field_keys = [fk for fk in ordered_field_keys if fk in available_fields]
    
    matrix_data = []
    
    for step_eval in step_evaluations:
        step_label = f"{step_eval['assembly_name'][:15]}\nStep {step_eval['step_id']}"
        step_labels.append(step_label)
        
        row = []
        for field_key in field_keys:
            comp = step_eval["field_comparisons"].get(field_key)
            if comp is None:
                row.append(0)  # Grau (nicht vorhanden)
            elif comp["match"]:
                row.append(1)  # Grün (Match)
            else:
                row.append(-1)  # Rot (Mismatch)
        
        matrix_data.append(row)
    
    # Plot Heatmap
    matrix = np.array(matrix_data)
    
    fig, ax = plt.subplots(figsize=(max(16, len(field_keys) * 0.5), max(8, len(step_labels) * 0.3)))
    
    # Custom colormap: Rot (-1), Grau (0), Grün (1)
    from matplotlib.colors import ListedColormap
    colors = ['#E74C3C', '#BDC3C7', '#27AE60']  # Rot, Grau, Grün
    cmap = ListedColormap(colors)
    
    im = ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=-1, vmax=1)
    
    # Achsen
    ax.set_xticks(np.arange(len(field_keys)))
    ax.set_yticks(np.arange(len(step_labels)))
    ax.set_xticklabels([fk.replace('.', '\n') for fk in field_keys], rotation=90, ha='center', fontsize=8)
    ax.set_yticklabels(step_labels, fontsize=8)
    
    # Titel
    ax.set_title(f'Step-by-Step Field Accuracy Heatmap ({title_suffix})\n(Green=Match, Red=Mismatch, Gray=Missing)', 
                 fontsize=14, fontweight='bold', pad=20)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax, ticks=[-1, 0, 1])
    cbar.ax.set_yticklabels(['Mismatch', 'Missing', 'Match'])
    
    plt.tight_layout()
    
    heatmap_path = output_dir / "step_accuracy_heatmap.png"
    plt.savefig(heatmap_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved step accuracy heatmap: {heatmap_path}")


def generate_field_accuracy_summary_heatmap(step_evaluations: List[Dict], output_dir: Path, title_suffix: str = "All Assemblies") -> None:
    """
    Erstellt aggregierte Heatmap: Zeigt für jedes Field die Anzahl der 
    Correct vs Incorrect Predictions über alle Steps hinweg.
    """
    # Sortiere field_keys nach Subprocess-Reihenfolge
    ordered_field_keys = []
    for subprocess_name in ["separation", "handling", "positioning", "joining"]:
        if subprocess_name in SUBPROCESS_MAPPING:
            for field_name in SUBPROCESS_MAPPING[subprocess_name]:
                field_key = f"{subprocess_name}.{field_name}"
                ordered_field_keys.append(field_key)
    
    # Nur Fields verwenden, die tatsächlich in den Daten vorkommen
    available_fields = set(k for s in step_evaluations for k in s["field_comparisons"].keys())
    field_keys = [fk for fk in ordered_field_keys if fk in available_fields]
    
    # Aggregiere Statistiken pro Field
    field_stats = {}
    for field_key in field_keys:
        total_matches = 0
        total_mismatches = 0
        total_missing = 0
        
        for step_eval in step_evaluations:
            comp = step_eval["field_comparisons"].get(field_key)
            if comp is None:
                total_missing += 1
            elif comp["match"]:
                total_matches += 1
            else:
                total_mismatches += 1
        
        field_stats[field_key] = {
            "correct": total_matches,
            "incorrect": total_mismatches,
            "missing": total_missing,
            "total": total_matches + total_mismatches + total_missing,
            "accuracy": total_matches / (total_matches + total_mismatches) if (total_matches + total_mismatches) > 0 else 0
        }
    
    # Erstelle stacked bar chart
    fig, ax = plt.subplots(figsize=(max(14, len(field_keys) * 0.6), 8))
    
    # Daten für Stacked Bar Chart
    field_labels = [fk.replace('.', '\n') for fk in field_keys]
    correct_counts = [field_stats[fk]["correct"] for fk in field_keys]
    incorrect_counts = [field_stats[fk]["incorrect"] for fk in field_keys]
    missing_counts = [field_stats[fk]["missing"] for fk in field_keys]
    
    x = np.arange(len(field_keys))
    width = 0.6
    
    # Stacked bars
    p1 = ax.bar(x, correct_counts, width, label='Correct', color='#27AE60')
    p2 = ax.bar(x, incorrect_counts, width, bottom=correct_counts, label='Incorrect', color='#E74C3C')
    
    # Optional: Missing-Counts obendrauf (wenn vorhanden)
    if any(missing_counts):
        bottom_vals = [c + i for c, i in zip(correct_counts, incorrect_counts)]
        p3 = ax.bar(x, missing_counts, width, bottom=bottom_vals, label='Missing', color='#BDC3C7')
    
    # Achsenbeschriftung
    ax.set_ylabel('Count', fontsize=12)
    ax.set_xlabel('Fields', fontsize=12)
    ax.set_title(f'Field Accuracy Summary ({title_suffix})\nCorrect vs Incorrect Predictions per Field', 
                 fontsize=14, pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(field_labels, rotation=90, ha='center', fontsize=9)
    ax.legend(loc='upper right', fontsize=10)
    
    # Accuracy-Werte als Text über Bars
    for i, (fk, stats) in enumerate(zip(field_keys, [field_stats[fk] for fk in field_keys])):
        total_height = stats["correct"] + stats["incorrect"] + stats["missing"]
        accuracy_pct = stats["accuracy"] * 100
        ax.text(i, total_height + 0.5, f'{accuracy_pct:.1f}%', 
                ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    plt.tight_layout()
    
    # Speichern
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "field_accuracy_summary.png"
    plt.savefig(summary_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    logger.info(f"Saved field accuracy summary heatmap: {summary_path}")


# ============================================================================
# MAIN EVALUATION FUNCTION
# ============================================================================

def find_latest_evaluation_run(evaluation_base_dir: Path = Path("data/experiments")) -> Optional[Path]:
    """Findet den aktuellsten Experiment-Run und gibt dessen Verzeichnis zurück.
    
    Sucht in data/experiments/ nach run_* Verzeichnissen.
    Legacy-Support: Falls data/experiments nicht vorhanden, sucht in data/evaluation/.
    """
    # Prefer new structure
    if evaluation_base_dir.exists():
        run_dirs = [item for item in evaluation_base_dir.iterdir() 
                    if item.is_dir() and item.name.startswith("run_")]
        
        if run_dirs:
            latest_run = sorted(run_dirs, key=lambda x: x.name, reverse=True)[0]
            return latest_run
    
    # Fallback to legacy structure
    legacy_dir = Path("data/evaluation")
    if legacy_dir.exists():
        run_dirs = [item for item in legacy_dir.iterdir() 
                    if item.is_dir() and item.name.startswith("run_")]
        
        if run_dirs:
            latest_run = sorted(run_dirs, key=lambda x: x.name, reverse=True)[0]
            return latest_run
    
    return None


def run_evaluation(predictions_dir: Path = None) -> None:
    """
    Hauptfunktion: Führt komplette FFA Evaluation durch.
    
    Args:
        predictions_dir: Pfad zu Experiment-Ordner (z.B. data/experiments/run_2026-02-10_154526/exp1_baseline/)
                        Wenn None: Auto-detect latest run
    """
    # Auto-detect latest run if not provided
    if predictions_dir is None:
        print("No predictions directory specified. Auto-detecting latest run...")
        predictions_dir = find_latest_evaluation_run()
        
        if predictions_dir is None:
            print("\n❌ Error: No experiment runs found in data/experiments/")
            print("\nUsage: python -m evaluation.ffa_evaluation [<run_dir>]")
            print("\nExample:")
            print("  python -m evaluation.ffa_evaluation data/experiments/run_2026-02-10_154526/exp1_baseline")
            return
        
        print(f"✓ Using latest run: {predictions_dir}\n")
    else:
        predictions_dir = Path(predictions_dir)
    
    # Setup paths
    workspace_root = Path(__file__).resolve().parents[1]
    ground_truth_dir = workspace_root / "data" / "ground_truth" / "ffa_ground_truth"
    output_dir = predictions_dir / "evaluation_results"
    
    # Organized subdirectories
    metrics_dir = output_dir / "metrics"
    viz_dir = output_dir / "visualizations"
    cm_dir = viz_dir / "confusion_matrices"
    f1_dir = viz_dir / "f1_scores"
    step_analysis_dir = viz_dir / "step_analysis"
    per_assembly_dir = output_dir / "per_assembly"
    
    # Create output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    cm_dir.mkdir(parents=True, exist_ok=True)
    f1_dir.mkdir(parents=True, exist_ok=True)
    step_analysis_dir.mkdir(parents=True, exist_ok=True)
    per_assembly_dir.mkdir(parents=True, exist_ok=True)
    
    # Header
    print("\n" + "="*80)
    print("FFA EVALUATION - Ground Truth vs LLM Predictions")
    print("="*80)
    
    # Safe relative path printing
    try:
        gt_rel = ground_truth_dir.relative_to(workspace_root)
    except ValueError:
        gt_rel = ground_truth_dir
    
    try:
        pred_rel = predictions_dir.relative_to(workspace_root)
    except ValueError:
        pred_rel = predictions_dir
    
    try:
        out_rel = output_dir.relative_to(workspace_root)
    except ValueError:
        out_rel = output_dir
    
    print(f"\nGround Truth: {gt_rel}")
    print(f"Predictions:  {pred_rel}")
    print(f"Output:       {out_rel}")
    
    # Load enum mapping for full confusion matrix size
    print("\n[1/9] Loading Enum Mapping...")
    enum_mapping_path = predictions_dir / "ffa_enum_mapping.json"
    
    enum_mapping = None
    reverse_mapping = None
    if enum_mapping_path.exists():
        enum_mapping = load_enum_mapping(enum_mapping_path)
        reverse_mapping = create_reverse_enum_mapping(enum_mapping)
        print(f"   ✓ Loaded enum mapping with {len(enum_mapping)} enum classes")
    else:
        print(f"   ⚠ No ffa_enum_mapping.json found (confusion matrices may be incomplete)")
    
    # Load data
    print("\n[2/9] Loading Ground Truth and Predictions...")
    ground_truth = load_ground_truth(ground_truth_dir)
    predictions = load_predictions(predictions_dir)
    
    if not ground_truth:
        print("   ❌ No ground truth data found!")
        return
    if not predictions:
        print("   ❌ No prediction data found!")
        return
    
    print(f"   ✓ Ground Truth: {len(ground_truth)} assemblies")
    print(f"   ✓ Predictions:  {len(predictions)} assemblies")
    
    # Match steps
    print("\n[3/9] Matching Steps (GT ↔ Predictions)...")
    matched_data = match_steps(ground_truth, predictions)
    
    total_matched = sum(len(steps) for steps in matched_data.values())
    print(f"   ✓ Matched {total_matched} steps across {len(matched_data)} assemblies")
    
    # Calculate metrics per field
    print("\n[4/9] Calculating Metrics per Field...")
    field_metrics = calculate_metrics_per_field(matched_data, enum_mapping)
    
    fields_with_data = sum(1 for m in field_metrics.values() if m["support"] > 0)
    print(f"   ✓ Calculated metrics for {fields_with_data}/{len(ALL_FFA_FIELDS)} fields")
    
    # Calculate aggregated metrics
    print("\n[5/9] Calculating Aggregated Metrics...")
    aggregated_metrics = calculate_metrics_aggregated(field_metrics)
    print(f"   ✓ Overall F1-Score (mean): {aggregated_metrics['overall_f1_macro_mean']:.3f}")
    print(f"   ✓ Overall Accuracy (mean): {aggregated_metrics['overall_accuracy_mean']:.3f}")
    
    # Calculate metrics per subprocess
    print("\n[6/9] Calculating Metrics per Subprocess...")
    subprocess_metrics = calculate_metrics_per_subprocess(field_metrics)
    print("   ✓ Subprocess F1-Scores:")
    for subprocess, metrics in subprocess_metrics.items():
        if metrics["fields_evaluated"] > 0:
            print(f"      - {subprocess.capitalize()}: {metrics['f1_macro_weighted']:.3f}")
    
    # Calculate metrics per assembly
    print("\n[7/9] Calculating Metrics per Assembly...")
    assembly_metrics = calculate_metrics_per_assembly(matched_data, enum_mapping)
    print("   ✓ Assembly F1-Scores:")
    for assembly_name, metrics in assembly_metrics.items():
        if metrics["total_support"] > 0:
            print(f"      - {assembly_name}: {metrics['overall_f1_macro_mean']:.3f} (Acc: {metrics['overall_accuracy_mean']:.3f})")
    
    # Generate visualizations
    print("\n[8/9] Generating Visualizations...")
    
    # Confusion matrices for each field
    cm_count = 0
    for field_key, metrics in field_metrics.items():
        if metrics["support"] > 0 and metrics["confusion_matrix"] is not None:
            cm = np.array(metrics["confusion_matrix"])
            # Use all_possible_labels if available (volle Matrix Größe)
            class_labels = metrics.get("all_possible_labels", metrics["unique_classes"])
            
            # Extract subprocess and field_name from key (e.g. "separation.automatable")
            subprocess_name, field_name = field_key.split(".", 1)
            prefix = get_field_prefix(field_name)
            
            # Use field_key for unique filename (e.g. all_assemblies_1_Separation_separation.automatable_cm.png)
            output_path = cm_dir / f"all_assemblies_{prefix}{field_key.replace('.', '_')}_cm.png"
            plot_confusion_matrix(cm, class_labels, field_key, output_path, 
                                label_mode='str', reverse_mapping=reverse_mapping, 
                                assembly_name=None)
            cm_count += 1
    
    print(f"   ✓ Generated {cm_count} confusion matrix plots")
    
    # Confusion matrices for each assembly (per field, same structure as global)
    assembly_cm_count = 0
    for assembly_name, asm_metrics in assembly_metrics.items():
        if asm_metrics["total_support"] > 0 and asm_metrics.get("field_metrics"):
            # Create assembly-specific directory
            assembly_dir = per_assembly_dir / assembly_name.replace(" ", "_")
            assembly_cm_subdir = assembly_dir / "visualizations" / "confusion_matrices"
            assembly_cm_subdir.mkdir(parents=True, exist_ok=True)
            
            # Create one CM per field (same as global structure)
            for field_key, asm_field_metrics in asm_metrics["field_metrics"].items():
                if asm_field_metrics["support"] > 0 and asm_field_metrics["confusion_matrix"] is not None:
                    cm = np.array(asm_field_metrics["confusion_matrix"])
                    # Use all_possible_labels if available
                    class_labels = asm_field_metrics.get("all_possible_labels", asm_field_metrics["unique_classes"])
                    
                    # Extract subprocess and field_name from key
                    subprocess_name, field_name = field_key.split(".", 1)
                    prefix = get_field_prefix(field_name)
                    output_path = assembly_cm_subdir / f"{prefix}{field_key.replace('.', '_')}_cm.png"
                    plot_confusion_matrix(cm, class_labels, field_key, output_path,
                                        label_mode='str', reverse_mapping=reverse_mapping,
                                        assembly_name=assembly_name)
                    assembly_cm_count += 1
    
    print(f"   ✓ Generated {assembly_cm_count} assembly confusion matrix plots")
    
    # F1-scores bar chart (global - all assemblies)
    f1_bar_path = f1_dir / "all_assemblies_f1_scores_per_field.png"
    plot_f1_scores_bar(field_metrics, f1_bar_path, assembly_name=None)
    print(f"   ✓ Generated F1-scores bar chart (all assemblies)")
    
    # F1-scores bar chart per assembly
    assembly_f1_count = 0
    for assembly_name, asm_metrics in assembly_metrics.items():
        if asm_metrics["total_support"] > 0 and asm_metrics.get("field_metrics"):
            assembly_dir = per_assembly_dir / assembly_name.replace(" ", "_")
            assembly_viz_dir = assembly_dir / "visualizations"
            assembly_viz_dir.mkdir(parents=True, exist_ok=True)
            
            f1_bar_path = assembly_viz_dir / "f1_scores_per_field.png"
            plot_f1_scores_bar(asm_metrics["field_metrics"], f1_bar_path, 
                             assembly_name=assembly_name)
            assembly_f1_count += 1
    
    print(f"   ✓ Generated {assembly_f1_count} assembly F1-score bar charts")
    
    # Subprocess comparison (all assemblies)
    subprocess_plot_path = f1_dir / "all_assemblies_f1_scores_per_subprocess.png"
    plot_subprocess_comparison(subprocess_metrics, subprocess_plot_path)
    print(f"   ✓ Generated subprocess comparison plot (all assemblies)")
    
    # Assembly comparison (comparing all assemblies)
    assembly_plot_path = f1_dir / "comparison_across_assemblies.png"
    plot_assembly_comparison(assembly_metrics, assembly_plot_path)
    print(f"   ✓ Generated cross-assembly comparison plot")
    
    # Step-by-step evaluation
    print("\n   Generating step-by-step evaluation...")
    generate_step_by_step_evaluation(matched_data, reverse_mapping, step_analysis_dir, per_assembly_dir)
    
    # Save JSON results
    print("\n[9/9] Saving Results...")
    
    # Per-field metrics
    with open(metrics_dir / "metrics_per_field.json", 'w', encoding='utf-8') as f:
        json.dump(field_metrics, f, indent=2, ensure_ascii=False)
    print(f"   ✓ Saved metrics_per_field.json")
    
    # Per-subprocess metrics
    with open(metrics_dir / "metrics_per_subprocess.json", 'w', encoding='utf-8') as f:
        json.dump(subprocess_metrics, f, indent=2, ensure_ascii=False)
    print(f"   ✓ Saved metrics_per_subprocess.json")
    
    # Per-assembly metrics
    with open(metrics_dir / "metrics_per_assembly.json", 'w', encoding='utf-8') as f:
        json.dump(assembly_metrics, f, indent=2, ensure_ascii=False)
    print(f"   ✓ Saved metrics_per_assembly.json")
    
    # Aggregated metrics
    with open(metrics_dir / "metrics_summary.json", 'w', encoding='utf-8') as f:
        json.dump(aggregated_metrics, f, indent=2, ensure_ascii=False)
    print(f"   ✓ Saved metrics_summary.json")
    
    # Final summary
    print("\n" + "="*80)
    print("EVALUATION COMPLETE")
    print("="*80)
    print(f"\n📊 Results Summary:")
    print(f"   Overall Accuracy (weighted): {aggregated_metrics['overall_accuracy_weighted']:.3f}")
    print(f"   Overall F1-Score (weighted): {aggregated_metrics['overall_f1_macro_weighted']:.3f}")
    print(f"   Total Samples: {aggregated_metrics['total_samples']}")
    print(f"   Fields Evaluated: {aggregated_metrics['fields_evaluated']}/{len(ALL_FFA_FIELDS)}")
    
    try:
        rel_path = output_dir.relative_to(workspace_root)
    except ValueError:
        rel_path = output_dir
    
    print(f"\n📁 Output Location: {rel_path}")
    print(f"   - metrics_summary.json")
    print(f"   - metrics_per_field.json")
    print(f"   - metrics_per_subprocess.json")
    print(f"   - metrics_per_assembly.json")
    print(f"   - f1_scores_per_field.png")
    print(f"   - f1_scores_per_subprocess.png")
    print(f"   - performance_per_assembly.png")
    print(f"   - confusion_matrices/ ({cm_count} plots)")
    print(f"   - confusion_matrices_per_assembly/ ({assembly_cm_count} plots)\n")


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Auto-detect latest run if no argument provided
    if len(sys.argv) < 2:
        run_evaluation()
    else:
        predictions_dir = Path(sys.argv[1])
        run_evaluation(predictions_dir)
