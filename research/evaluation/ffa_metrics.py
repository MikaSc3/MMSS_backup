"""
FFA Evaluation Metrics (Macro-Average fokussiert)

Berechnet Metriken mit Fokus auf Macro-Average, um mit unausgewogenen Klassen umzugehen.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, accuracy_score
from collections import defaultdict


def load_ffa_data(enum_file: Path, ground_truth_file: Path) -> Tuple[List[Dict], List[Dict], List[str]]:
    """
    Lädt Prediction (Enum) und Ground Truth Daten.
    
    Args:
        enum_file: *_ffa_assessment_enum.json (LLM predictions)
        ground_truth_file: *_ffa_assessment_enum_gt.json (Ground Truth)
    
    Returns:
        (predictions, ground_truth, step_names)
    """
    with open(enum_file, 'r') as f:
        predictions = json.load(f)
    
    with open(ground_truth_file, 'r') as f:
        ground_truth = json.load(f)
    
    # Handle both wrapped (step_assessments key) and unwrapped (direct list) formats
    if isinstance(predictions, dict) and "step_assessments" in predictions:
        predictions = predictions["step_assessments"]
    
    if isinstance(ground_truth, dict) and "step_assessments" in ground_truth:
        ground_truth = ground_truth["step_assessments"]
    
    step_names = [step.get("step_name", f"step_{i}") for i, step in enumerate(ground_truth)]
    
    return predictions, ground_truth, step_names


def extract_field_values(
    predictions: List[Dict],
    ground_truth: List[Dict],
    field_name: str
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrahiert Werte eines spezifischen Feldes aus Predictions und Ground Truth.
    
    Struktur wird auto-detektiert:
    - Flat: step.{field_name}
    - Nested: step.assessment.{category}.{field_name}
    
    Args:
        predictions: Liste von Prediction-Steps
        ground_truth: Liste von GT-Steps
        field_name: Feldname (z.B. "part_rigidity")
    
    Returns:
        (pred_values, gt_values) als NumPy Arrays
    """
    pred_vals = []
    gt_vals = []
    
    for pred_step, gt_step in zip(predictions, ground_truth):
        # Try flat structure first
        pred_val = pred_step.get(field_name)
        gt_val = gt_step.get(field_name)
        
        # If not found, try nested structure (assessment.category.field)
        if pred_val is None and isinstance(pred_step, dict) and "assessment" in pred_step:
            assessment = pred_step["assessment"]
            # Search in all categories
            for category in assessment.values():
                if isinstance(category, dict) and field_name in category:
                    pred_val = category[field_name]
                    break
        
        if gt_val is None and isinstance(gt_step, dict) and "assessment" in gt_step:
            assessment = gt_step["assessment"]
            # Search in all categories
            for category in assessment.values():
                if isinstance(category, dict) and field_name in category:
                    gt_val = category[field_name]
                    break
        
        # Skip if either is None
        if pred_val is None or gt_val is None:
            continue
        
        pred_vals.append(pred_val)
        gt_vals.append(gt_val)
    
    return np.array(pred_vals), np.array(gt_vals)


def calculate_macro_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Berechnet Macro-Average Metriken (für unausgewogene Klassen).
    
    Args:
        y_true: Ground Truth Labels
        y_pred: Predictions
    
    Returns:
        Dict mit Metriken
    """
    metrics = {
        "macro_f1": f1_score(y_true, y_pred, average='macro', zero_division=0),
        "macro_precision": precision_score(y_true, y_pred, average='macro', zero_division=0),
        "macro_recall": recall_score(y_true, y_pred, average='macro', zero_division=0),
        "micro_accuracy": accuracy_score(y_true, y_pred),  # Referenz
        "weighted_f1": f1_score(y_true, y_pred, average='weighted', zero_division=0),  # Referenz
        "samples": len(y_true)
    }
    
    return metrics


def calculate_per_class_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[int, Dict[str, float]]:
    """
    Berechnet Metriken pro Klasse (für alle möglichen Labels, auch fehlende).
    
    Args:
        y_true: Ground Truth Labels
        y_pred: Predictions
    
    Returns:
        Dict: {class_id: {precision, recall, f1, support, tp, fp, fn}}
    """
    # Get all possible labels
    all_labels = np.arange(int(max(y_true.max(), y_pred.max())) + 1)
    per_class = {}
    
    for cls in all_labels:
        y_true_binary = (y_true == cls).astype(int)
        y_pred_binary = (y_pred == cls).astype(int)
        
        tp = np.sum((y_true_binary == 1) & (y_pred_binary == 1))
        fp = np.sum((y_true_binary == 0) & (y_pred_binary == 1))
        fn = np.sum((y_true_binary == 1) & (y_pred_binary == 0))
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        support = np.sum(y_true_binary)
        
        per_class[int(cls)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": int(support),
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn)
        }
    
    return per_class


def calculate_confusion_matrix_data(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    """
    Berechnet Confusion Matrix mit allen möglichen Labels.
    
    Args:
        y_true: Ground Truth
        y_pred: Predictions
    
    Returns:
        Dict mit Confusion Matrix und Analysen
    """
    # Determine all possible labels (0 to max value found + handle missing classes)
    all_labels = np.arange(int(max(y_true.max(), y_pred.max())) + 1)
    
    cm = confusion_matrix(y_true, y_pred, labels=all_labels)
    
    return {
        "confusion_matrix": cm.tolist(),
        "classes": all_labels.tolist(),
        "shape": cm.shape
    }


def evaluate_assembly(
    enum_dir: Path,
    ground_truth_root: Path,
    assembly_name: str
) -> Dict[str, Dict]:
    """
    Evaluiert eine Assembly gegen Ground Truth.
    
    Args:
        enum_dir: Ordner mit *_ffa_assessment_enum.json
        ground_truth_root: Ordner mit GT Dateien
        assembly_name: Name der Assembly
    
    Returns:
        Dict mit Metriken pro Feld
    """
    # Find files
    enum_file = enum_dir / f"{assembly_name}_ffa_assessment_enum.json"
    gt_file = ground_truth_root / f"{assembly_name}_ffa_assessment_enum_gt.json"
    
    if not enum_file.exists() or not gt_file.exists():
        return {
            "status": "missing_files",
            "enum_file": str(enum_file),
            "gt_file": str(gt_file)
        }
    
    # Load data
    predictions, ground_truth, step_names = load_ffa_data(enum_file, gt_file)
    
    # Fields to evaluate
    eval_fields = [
        "nature_of_provision",
        "part_rigidity",
        "gripping_areas",
        "orientation_features",
        "surface_sensibility",
        "accuracy_of_target_position",
        "positioning_aids",
        "additional_orientation_by_rotation",
        "accessibility_to_joining_position",
        "positioning_motion",
        "positioning_tolerances",
        "stability_in_positioned_state",
        "feeding_of_joining_element",
        "fixing_of_mounted_part"
    ]
    
    results = {
        "assembly_name": assembly_name,
        "steps": len(step_names),
        "step_names": step_names,
        "fields": {}
    }
    
    # Evaluate each field
    for field in eval_fields:
        y_pred, y_true = extract_field_values(predictions, ground_truth, field)
        
        if len(y_pred) == 0:
            results["fields"][field] = {"status": "no_data"}
            continue
        
        results["fields"][field] = {
            "metrics": calculate_macro_metrics(y_true, y_pred),
            "per_class": calculate_per_class_metrics(y_true, y_pred),
            "confusion_matrix": calculate_confusion_matrix_data(y_true, y_pred)
        }
    
    # Calculate macro over all fields
    macro_f1_scores = [
        f["metrics"]["macro_f1"]
        for f in results["fields"].values()
        if f.get("metrics")
    ]
    
    results["overall_macro_f1"] = np.mean(macro_f1_scores) if macro_f1_scores else 0
    results["overall_macro_f1_std"] = np.std(macro_f1_scores) if macro_f1_scores else 0
    
    return results


def evaluate_experiment(
    exp_dir: Path,
    ground_truth_root: Path
) -> Dict:
    """
    Evaluiert ein komplettes Experiment über alle Assemblies.
    
    Args:
        exp_dir: Experiment-Ordner mit Assembly-Subdirectories
        ground_truth_root: GT Root
    
    Returns:
        Dict mit Metriken für alle Assemblies
    """
    results = {
        "experiment": exp_dir.name,
        "assemblies": {}
    }
    
    # Find all assembly directories
    for asm_dir in sorted(exp_dir.iterdir()):
        if not asm_dir.is_dir() or asm_dir.name.startswith("_"):
            continue
        
        assembly_name = asm_dir.name
        asm_eval = evaluate_assembly(asm_dir, ground_truth_root, assembly_name)
        results["assemblies"][assembly_name] = asm_eval
    
    # Calculate overall metrics
    overall_f1_scores = [
        asm["overall_macro_f1"]
        for asm in results["assemblies"].values()
        if "overall_macro_f1" in asm
    ]
    
    results["overall_macro_f1"] = np.mean(overall_f1_scores) if overall_f1_scores else 0
    results["overall_macro_f1_std"] = np.std(overall_f1_scores) if overall_f1_scores else 0
    results["num_assemblies"] = len(results["assemblies"])
    
    return results


def rank_assemblies(experiment_results: Dict) -> List[Tuple[str, float]]:
    """
    Rankt Assemblies nach Macro-F1 Score.
    
    Args:
        experiment_results: Result Dict von evaluate_experiment()
    
    Returns:
        Liste von (assembly_name, macro_f1) sorted descending
    """
    rankings = []
    
    for asm_name, asm_data in experiment_results["assemblies"].items():
        f1 = asm_data.get("overall_macro_f1", 0)
        rankings.append((asm_name, f1))
    
    rankings.sort(key=lambda x: x[1], reverse=True)
    return rankings


def create_class_distribution_analysis(
    predictions: List[Dict],
    ground_truth: List[Dict],
    field_name: str
) -> Dict:
    """
    Analysiert die Klassen-Verteilung für ein Feld.
    
    Args:
        predictions: Predictions
        ground_truth: Ground Truth
        field_name: Feldname
    
    Returns:
        Dict mit Verteilungs-Infos
    """
    _, y_true = extract_field_values(predictions, ground_truth, field_name)
    
    classes, counts = np.unique(y_true, return_counts=True)
    
    analysis = {
        "field": field_name,
        "total_samples": int(len(y_true)),
        "num_classes": int(len(classes)),
        "class_distribution": {
            int(cls): int(count)
            for cls, count in zip(classes, counts)
        },
        "imbalance_ratio": float(counts.max() / counts.min()) if len(counts) > 0 else 0
    }
    
    return analysis
