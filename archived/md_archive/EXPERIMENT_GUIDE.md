# Experiment System - APA_from_CAD

## Überblick

Das Experiment-System ermöglicht es, verschiedene Konfigurationen systematisch zu testen:
- Verschiedene Prompt-Varianten
- Unterschiedliche Image-Views
- LLM-Temperature-Settings
- Feature-Flags (Additional Info, Merge BOM, Assembly Sequence Generation/Validation, FFA)

## Ordnerstruktur

```
configs/experiments/          # Experiment-Konfigurationen
├── exp1_baseline.yaml       # Baseline mit Standard-Settings
├── exp2_high_temp.yaml      # Höhere Temperature
└── ...

data/experiments/             # Experiment-Outputs (isoliert)
├── exp1_baseline/
│   ├── IPA_Cranfield/
│   │   ├── IPA_Cranfield_Overview_Enriched.json
│   │   ├── IPA_Cranfield_BOM_enriched.json
│   │   ├── enriched_parts/
│   │   │   ├── part_001_Data_enriched.json
│   │   │   ├── part_001_Data_enriched_merged.json
│   │   │   └── ...
│   │   ├── merged_bom.json                    # NEU
│   │   ├── assembly_sequence.json             # NEU
│   │   └── assembly_sequence_validation/      # NEU (optional)
│   │       ├── step_01_validation.json
│   │       ├── step_02_validation.json
│   │       └── assembly_sequence_validation_merged.json
│   └── experiment_summary.json
└── experiments_summary.json  # Globale Zusammenfassung

data/processed/stepparser/    # READ-ONLY: Stepparser-Outputs
└── IPA_Cranfield/
    └── ...                   # Wird NICHT beschrieben
```

## Verwendung

### Einzelnes Experiment ausführen

```bash
# Mit Experiment-Namen
python run_experiments.py exp1_baseline

# Mit vollständigem Pfad
python run_experiments.py configs/experiments/exp1_baseline.yaml
```

### Alle Experimente ausführen

```bash
python run_experiments.py
```

Dies führt automatisch alle `*.yaml` Dateien in `configs/experiments/` aus (außer `exp_example.yaml`).

### Legacy-Modus (einzelner Run ohne Experiments)

```bash
python agent/Workflow_enrich_data.py
```

Schreibt Outputs in stepparser-Ordner (nicht empfohlen).

## Experiment-Konfiguration

Jedes Experiment ist eine YAML-Datei mit folgenden Feldern:

```yaml
# Experiment Metadata
experiment_name: "exp1_baseline"
description: "Beschreibung des Experiments"

# Data Sources (STEP-Dateien aus data/processed/stepparser/)
step_files:
  - "IPA_Cranfield"
  - "Gearbox"

# Image Processing (run_assembly & run_monoparts)
img_to_analyse_assy: ["explosion", "isometric"]
img_to_analyse_monopart: ["top", "isometric"]
downscaling_factor: 1.0

# Feature Flags
use_additional_assembly_info: true
enable_merge_bom: true                        # NEU
enable_assembly_sequence: true                # NEU
enable_sequence_validation: false             # NEU (optional)
enable_ffa_assessment: false

# Assembly Sequence Generation Settings  (NEU)
assembly_sequence_image_keywords:
  - "exploded"
  - "isometric"
assembly_sequence_json_keywords:
  - "merged_bom"

# Assembly Sequence Validation Settings (NEU)
ASV_step_img_keywords:
  - "isometric"
  # Erweitern zu: ["isometric", "front", "top", "side"] für alle Views
ASV_finished_assy_keywords:
  - "isometric"
ASV_json_keywords:
  - "merged_bom"

# Prompt Selection
prompt_id_assy: "assembly_describer_v1"
prompt_id_monopart: "monopart_describer_v1"

# LLM Settings
img_describer_tokens_per_img: 2500
temperature: 0.0

# Workflow Settings
workflow_print: true
use_unique_parts: true
parallel: false
```

## Output-Struktur

Für jedes Experiment wird ein eigener Ordner erstellt:

```
data/experiments/{experiment_name}/{step_file}/
├── IPA_Cranfield_Overview_Enriched.json
├── IPA_Cranfield_BOM_enriched.json
├── enriched_parts/
│   ├── part_001_Data_enriched.json
│   ├── part_001_Data_enriched_merged.json
│   └── part_002_Data_enriched.json
└── experiment_summary.json
```

### experiment_summary.json

```json
{
  "experiment_name": "exp1_baseline",
  "step_file": "IPA_Cranfield",
  "status": "success",
  "assembly_written": "path/to/assembly.json",
  "parts_count": 2,
  "run_manifest": "path/to/manifest.json",
  "warnings": []
}
```

## Experiment-Vergleich

Nach dem Ausführen aller Experimente:

```bash
# Globale Zusammenfassung ansehen
cat data/experiments/experiments_summary.json

# Ergebnisse vergleichen
python -c "import json; data = json.load(open('data/experiments/experiments_summary.json')); print(f'Total: {data[\"total_experiments\"]} experiments, {data[\"successful_experiments\"]} successful')"
```

## Best Practices

1. **Stepparser bleibt read-only**: Originale stepparser-Outputs werden nie überschrieben
2. **Ein Experiment = Eine Frage**: Ändere pro Experiment nur wenige Parameter
3. **Aussagekräftige Namen**: `exp1_baseline`, `exp2_high_temp`, `exp3_no_context`
4. **Dokumentation**: Füge `description` Feld hinzu
5. **STEP-Files filtern**: Nur relevante Assemblies in `step_files` angeben

## Troubleshooting

### "No step_files specified"
Füge `step_files:` Liste zum Experiment-YAML hinzu.

### "Datasource not found"
Prüfe ob STEP-File in `data/processed/stepparser/` existiert (z.B. `IPA_Cranfield/`).

### Alte enriched Files in stepparser/
Das sind Legacy-Outputs. Neue Runs schreiben nach `data/experiments/`.
