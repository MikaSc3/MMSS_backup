# FFA Evaluation System

**Macro-Average fokussierte Evaluation für Fitness-for-Automation Assessments**

---

## 🎯 Ziel

Bewertung von LLM-generierten FFA Assessments gegen Ground Truth mit Fokus auf **Macro-Average Metriken**, um korrekt mit klassenunausgeglichenen Daten umzugehen.

---

## 📊 Problem: Class Imbalance

### Beispiel aus Daten

Für das Feld `nature_of_provision`:
- **Klasse 1** ("in magazine"): 10 Samples ✓
- **Klasse 2** ("in bulk"): 1 Sample ⚠️
- **Klasse 3-5**: 0 Samples (nicht vorhanden)

**Problem mit Weighted-Average Metrics:**
- Gewichtet nach Sample-Anzahl
- Minderheitsklasse hat minimalen Einfluss
- Schlechte Performance bei Klasse 2 wird ignoriert

**Lösung: Macro-Average**
- Alle Klassen gleich gewichtet
- Zeigt echte Per-Class Performance
- Enthüllt Minderheitsklassen-Probleme

---

## 🗂️ Dateistruktur

### Core Module

| Datei | Zeilen | Funktion |
|-------|--------|----------|
| `ffa_metrics.py` | 361 | Metrik-Berechnung (Macro/Micro/Per-Class) |
| `ffa_visualization.py` | 350+ | Visualisierungen (Charts, Heatmaps) |
| `ffa_str_to_enum.py` | 553 | String→Enum Konvertierung |
| `ffa_enum_to_str.py` | 200+ | Enum→String Reverse (für Reports) |

### Orchestrator

| Datei | Zeilen | Funktion |
|-------|--------|----------|
| `../run_ffa_evaluation.py` | 500+ | Main Pipeline Orchestrator |

### Output Struktur

```
data/experiments/ffa_experiments/
├── evaluation/                              ← ROOT
│   ├── enum_cache/
│   │   └── {assembly}_ffa_assessment_enum.json  (Converted files)
│   │
│   ├── summary.json                         ← Overall Metrics
│   ├── macro_f1_comparison.png              ← Root-level Charts
│   ├── assembly_ranking.png
│   │
│   └── {experiment_name}/                   ← Per-Experiment
│       ├── summary.json
│       └── {assembly_name}/                 ← Per-Assembly
│           ├── metrics.json                 ← All field metrics
│           ├── confusion_matrix_*.png       (14 Felder)
│           ├── per_class_*.png              (14 Felder)
│           ├── assembly_summary.png
│           ├── class_distribution_heatmap.png
│           └── step_overview.png
```

---

## 🔌 API Reference

### Load & Evaluate

```python
from evaluation.ffa_metrics import (
    load_ffa_data,
    evaluate_assembly,
    evaluate_experiment,
    rank_assemblies
)

# Load Predictions vs Ground Truth
predictions, ground_truth, step_names = load_ffa_data(
    enum_file=Path(".../_ffa_assessment_enum.json"),
    ground_truth_file=Path(".../_ffa_assessment_enum_gt.json")
)

# Evaluate Single Assembly (all 14 FFA fields)
assembly_results = evaluate_assembly(
    enum_dir=Path(".../Connecting_Rod/"),
    ground_truth_root=Path(".../ffa_ground_truth/"),
    assembly_name="Connecting_Rod"
)

# Evaluate Entire Experiment
experiment_results = evaluate_experiment(
    exp_dir=Path(".../FFA_only_tryout_exp1_baseline/"),
    ground_truth_root=Path(".../ffa_ground_truth/")
)

# Rank Assemblies (best→worst)
rankings = rank_assemblies(experiment_results)
# Returns: [("Connecting_Rod", 0.67), ("Other_Assembly", 0.45), ...]
```

### Metrics Functions

```python
from evaluation.ffa_metrics import (
    calculate_macro_metrics,
    calculate_per_class_metrics,
    calculate_confusion_matrix_data
)

# Extract field values
y_pred, y_true = extract_field_values(
    predictions, ground_truth, 
    field_name="nature_of_provision"
)

# Macro-Average Metrics (MAIN)
metrics = calculate_macro_metrics(y_true, y_pred)
# Returns: {
#   "macro_f1": 0.539,
#   "macro_precision": 0.54,
#   "macro_recall": 0.55,
#   "micro_accuracy": 0.80,
#   "weighted_f1": 0.78,
#   "samples": 5
# }

# Per-Class Breakdown
per_class = calculate_per_class_metrics(y_true, y_pred)
# Returns: {
#   0: {"precision": 0.5, "recall": 0.67, "f1": 0.57, "support": 3, ...},
#   1: {"precision": 1.0, "recall": 0.0, "f1": 0.0, "support": 1, ...},
#   2: {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0, ...},
#   ...
# }

# Confusion Matrix
cm_data = calculate_confusion_matrix_data(y_true, y_pred)
# Returns: {
#   "confusion_matrix": [[3, 0, ...], [1, 0, ...], ...],
#   "classes": [0, 1, 2, 3, 4, 5],           ← All possible labels
#   "shape": (6, 6)
# }
```

### Visualization Functions

```python
from evaluation.ffa_visualization import (
    save_confusion_matrix,
    save_per_class_metrics_chart,
    save_assembly_summary_chart,
    save_macro_comparison_chart,
    save_assembly_ranking_chart
)

# Confusion Matrix Heatmap (per field)
save_confusion_matrix(
    cm_data=cm_data,
    output_path=Path(".../confusion_matrix_nature_of_provision.png"),
    field_name="nature_of_provision",
    assembly_name="Connecting_Rod"
)

# Assembly Summary (all fields, color-coded)
save_assembly_summary_chart(
    assembly_eval=assembly_results,
    output_path=Path(".../assembly_summary.png")
)
# Green (F1>0.7) | Orange (F1>0.5) | Red (F1<0.5)

# Experiment Comparison
save_macro_comparison_chart(
    experiments_results={"exp1": results1, "exp2": results2},
    output_path=Path(".../macro_f1_comparison.png")
)
```

---

## 🎯 Metriken Erklärung

### Macro-Average Metrics (PRIMARY)

| Metrik | Formel | Bedeutung |
|--------|--------|----------|
| **Macro F1** | Avg(F1_per_class) | **Primary metric** - unabhängig von Klassenimbalance |
| Macro Precision | Avg(Precision_per_class) | Durchschn. Genauigkeit pro Klasse |
| Macro Recall | Avg(Recall_per_class) | Durchschn. Abdeckung pro Klasse |

### Micro-Metrics (Reference only)

| Metrik | Bedeutung | Achtung |
|--------|-----------|---------|
| Micro Accuracy | Gesamtgenauigkeit | Kann mit Imbalance irreführend sein |
| Weighted F1 | F1 gewichtet nach Samples | Ignoriert Minderheitsklassen |

### Per-Class Metrics

```python
# Für jede Klasse:
"class_1": {
    "precision": TP / (TP + FP),           # Korrektheit positiver Vorhersagen
    "recall": TP / (TP + FN),               # Abdeckung echter Positiven
    "f1": 2 * (P * R) / (P + R),            # Harmonic Mean
    "support": count(true_samples),         # Anzahl Samples in GT
    "tp": true_positives,
    "fp": false_positives,
    "fn": false_negatives
}
```

---

## 🔄 Data Format

### Predictions Format

Expected: `{assembly}_ffa_assessment_enum.json`

```json
{
  "assembly_name": "Connecting_Rod",
  "total_steps": 5,
  "assessed_steps": 5,
  "step_assessments": [
    {
      "step_id": 1,
      "step_description": "Place Connecting Rod End on assembly table",
      "assessment": {
        "separation": {
          "nature_of_provision": 1,
          "automatable": null
        },
        "handling": {
          "part_rigidity": 1,
          "gripping_areas": 1,
          "orientation_features": 1,
          "surface_sensibility": 2,
          "automatable": null
        },
        "positioning": {
          "accuracy_of_target_position": 1,
          "positioning_aids": 2,
          ...
        },
        "joining": {
          "feeding_of_joining_element": 1,
          "fixing_of_mounted_part": 1,
          "automatable": null
        }
      }
    },
    ...
  ]
}
```

### Ground Truth Format

Same structure as predictions, located in:
`data/ground_truth/ffa_ground_truth/{assembly}_ffa_assessment_enum_gt.json`

---

## 14 FFA Felder

```
Separation (1 Feld):
  1. nature_of_provision

Handling (4 Felder):
  2. part_rigidity
  3. gripping_areas
  4. orientation_features
  5. surface_sensibility

Positioning (8 Felder):
  6. accuracy_of_target_position
  7. positioning_aids
  8. additional_orientation_by_rotation
  9. accessibility_to_joining_position
  10. positioning_motion
  11. positioning_tolerances
  12. stability_in_positioned_state

Joining (2 Felder):
  13. feeding_of_joining_element
  14. fixing_of_mounted_part
```

---

## 🚀 Usage Examples

### Complete Evaluation Run

```bash
# Evaluiert alle Experimente automatisch
python run_ffa_evaluation.py

# Spezifisches Experiment
python run_ffa_evaluation.py data/experiments/ffa_experiments/FFA_only_tryout_exp1_baseline
```

### Custom Script

```python
from pathlib import Path
from evaluation.ffa_metrics import evaluate_experiment, rank_assemblies
from evaluation.ffa_visualization import save_assembly_ranking_chart

# Evaluate one experiment
results = evaluate_experiment(
    exp_dir=Path("data/experiments/ffa_experiments/FFA_only_tryout_exp1_baseline"),
    ground_truth_root=Path("data/ground_truth/ffa_ground_truth")
)

# Show rankings
rankings = rank_assemblies(results)
for rank, (asm_name, f1) in enumerate(rankings, 1):
    status = "✓" if f1 > 0.7 else "⚠" if f1 > 0.5 else "✗"
    print(f"{rank}. {asm_name}: {f1:.3f} {status}")

# Create visualization
save_assembly_ranking_chart(
    experiments_results={"exp1": results},
    output_path=Path("evaluation/ranking.png")
)
```

---

## ⚠️ Known Issues & Limitations

1. **Class Imbalance Warning**: Sklearn warns about single labels - this is expected with imbalanced data
2. **Missing Classes**: If a class doesn't appear in data, CM row will have all zeros - this is correct
3. **Nested Structure Extraction**: `extract_field_values()` handles both flat and nested `assessment.category.field` structures
4. **Conversion Cache**: Stripped→Enum conversions are cached in `evaluation/enum_cache/`

---

## 📝 Output Files

### JSON Outputs

**summary.json** (Root & Per-Experiment)
```json
{
  "timestamp": "2026-02-13T...",
  "experiments": {
    "FFA_only_tryout_exp1_baseline": {
      "num_assemblies": 1,
      "overall_macro_f1": 0.539,
      "overall_macro_f1_std": 0.0
    }
  }
}
```

**metrics.json** (Per-Assembly)
```json
{
  "assembly_name": "Connecting_Rod",
  "fields": {
    "nature_of_provision": {
      "metrics": {"macro_f1": 0.67, ...},
      "per_class": {0: {...}, 1: {...}, ...},
      "confusion_matrix": {...}
    },
    ... (13 more fields)
  },
  "overall_macro_f1": 0.539
}
```

### PNG Outputs

- `confusion_matrix_*.png` - One heatmap per FFA field
- `per_class_*.png` - Bar charts with Precision/Recall/F1
- `assembly_summary.png` - All fields colored by performance
- `class_distribution_heatmap.png` - Shows class imbalance
- `macro_f1_comparison.png` - Experiment comparison
- `assembly_ranking.png` - Best→Worst assemblies
- `step_overview.png` - Step-level metadata

---

## 🔧 Development

### Adding New Visualizations

```python
def save_custom_chart(metrics_dict, output_path):
    import matplotlib.pyplot as plt
    
    fig, ax = plt.subplots(figsize=(10, 6))
    # Your plotting code
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
```

### Extending Evaluation

1. Add new metric function to `ffa_metrics.py`
2. Call it in `evaluate_assembly()`
3. Store result in `asm_eval["fields"][field_name]`
4. Create visualization in `ffa_visualization.py`
5. Call visualization in `run_ffa_evaluation.py`

---

**Letztes Update**: 13. Februar 2026  
**Maintainer**: KAB-MS
