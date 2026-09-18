# ToDos & Next Steps

## ✅ Renderer Bug Fixes – Section View Stability (KOMPLETT - 24.02.2026)

**Status**: Alle Rendering-Abstürze behoben ✅

**Problem**: Rendering hängte sich bei Section Views auf, insbesondere bei ~Render #110+ mit `wglMakeCurrent() has failed`-Fehlern. Das eigentliche Problem war nicht der OpenGL-Fehler selbst, sondern Instabilität im OCC Boolean-Kernel.

**Root Causes & Fixes:**

#### 1. ✅ `huge_margin = 100000` → OCC Boolean Kernel Crash
- **Problem**: Alle drei Section View Methoden verwendeten einen Schnittquader mit Kantenlänge 200.000+ Einheiten, während die Teile selbst typisch < 500 Einheiten groß sind. OCC's Boolean-Algorithmus ist bei Dimensionsverhältnissen >1:1000 numerisch instabil → stiller C++-Crash ohne Python Exception.
- **Fix**: `margin = max(geom_diagonal * 0.5, 10.0)` – tighter Quader basierend auf der echten Geometriediagonale (in allen 3 Section View Methoden: XY, XZ, YZ)
- **Datei**: `stepparser/rendering/renderer.py`

#### 2. ✅ Fake Timeout → Echter Thread-basierter Timeout
- **Problem**: `_run_with_timeout()` führte Operationen synchron aus ohne echten Timeout – stand sogar im Docstring. Boolean Cuts konnten unendlich hängen.
- **Fix**: Echter `threading.Thread` mit `t.join(timeout)` – Boolean Cut läuft in Daemon-Thread, wird nach `timeout` Sekunden aufgegeben, Fallback auf Originalteil.
- **Datei**: `stepparser/rendering/renderer.py`

#### 3. ✅ `UpdateCurrentViewer()` nach jedem transparenten Teil
- **Problem**: In `_display_shape()` wurde `Context.UpdateCurrentViewer()` nach jedem transparenten Teil aufgerufen → bei 7 Teilen = 7 Viewer-Updates → kumulativer OpenGL-State-Schaden.
- **Fix**: Aufruf entfernt – OCC aktualisiert automatisch beim finalen `View.Dump()`.
- **Datei**: `stepparser/rendering/renderer.py`

#### 4. ✅ Memory Leaks in Boolean Cuts
- **Problem**: `BRepAlgoAPI_Cut` Objekte wurden nicht explizit gelöscht → akkumulierter OCC C++-Speicher.
- **Fix**: `del cut_algo` nach jedem Cut + `gc.collect()` nach jedem Part in allen 3 Section View Methoden.
- **Datei**: `stepparser/rendering/renderer.py`

#### 5. ✅ Missing `return 0.0` in Entropy Fallback
- **Problem**: Fehlender `return 0.0` nach dem Fallback-Dump in `_save_image_with_entropy()` → Code lief weiter und versuchte, nicht existierende temp-Datei zu verarbeiten.
- **Fix**: `return 0.0` nach Fallback eingefügt.
- **Datei**: `stepparser/rendering/renderer.py`

**Architekturelle Klarstellung:**
- Section View Rendering gehört vollständig zu **`render_assembly_steps()`** (nicht zu `validate_assembly_sequence()`)
- `validate_assembly_sequence()` enthält **kein Rendering** – lädt nur vorgerenderte Bilder

**Betroffene Dateien:**
- `stepparser/rendering/renderer.py` – 5 Fixes
- `agent/Assembly_sequence_validation.py` – Section View Code korrekt in `render_assembly_steps()` platziert

---

## ✅ Interaction Analysis Node Implementation (KOMPLETT - 23.02.2026)

**Status**: Alle Komponenten vollständig implementiert und in Workflow integriert ✅

**Implementierte Komponenten:**

1. **Core Node Function**: `agent/Interaction_analysis.py` (570 Zeilen)
   - ✅ `analyze_assembly_sequence_interactions()` - Hauptfunktion
   - ✅ `get_step_renderings()` - Renderings laden mit Keyword-Filterung
   - ✅ `get_monopart_renderings()` - Einzelteil-Bilder mit Copy-Handling
   - ✅ `analyze_step_interaction()` - LLM-Analyse per Step
   - ✅ Duplicate Part Handling (`normalize_part_id()`)

2. **Workflow Integration**: `agent/workflow.py`
   - ✅ `_node_interaction_analysis()` Funktion (165 Zeilen)
   - ✅ Node in Workflow Graph registriert
   - ✅ Edges verbunden: `render_assembly_steps` → `interaction_analysis` → `validate_assembly_sequence`
   - ✅ State Variables: `interaction_analysis_path`, `interaction_analysis_data`

3. **Configuration**: `configs/default_settings.yaml`
   - ✅ 13 neue `IA_*` Settings hinzugefügt
   - ✅ `FFA_include_interaction_analysis` Flag (optional FFA integration)
   - ✅ Prompt IDs, Image Keywords, JSON Keys definiert

4. **Experiment Config**: `configs/full_workflow/expX_most_info.yaml`
   - ✅ IA Settings mit experiment-spezifischen Werten
   - ✅ FFA Integration Flag (default: false)

5. **Checkpoint Integration**: `create_checkpoint_from_run.py`
   - ✅ `interaction_analysis.json` wird beim Checkpoint-Erstellen kopiert
   - ✅ Lines 191-206: Copy Logic nach sequence_renderings Copy

6. **FFA Integration**: `agent/FFA_assessment.py`
   - ✅ `assess_step_ffa()` - `interaction_context` Parameter hinzugefügt
   - ✅ `assess_assembly_sequence_ffa()` - `interaction_analysis_data` Parameter
   - ✅ Per-Step Kontext-Extraktion und Prompt-Integration
   - ✅ "GEOMETRIC INTERACTION ANALYSIS" Section im FFA-Prompt

7. **FFA-Only Support**: `agent/workflow.py` - `run_assess_ffa_only()`
   - ✅ Lädt `interaction_analysis.json` from Checkpoint (falls vorhanden)
   - ✅ Übergibt zu State für FFA Node
   - ✅ Graceful Degradation wenn nicht vorhanden

8. **Prompt Templates**: `configs/prompts.yaml`
   - ✅ `Interaction_Analyst_V1` - System Prompt (Expert Role)
   - ✅ `Analyse_Interaction_V1` - Task Prompt (Contact/Alignment/Collision Analysis)
   - ✅ Lines 1391-1450

**Output Format**:
- JSON Schema mit `analysis_metadata`, `steps[]`, `summary`
- Per Step: `contact_surfaces`, `alignment_challenges`, `collision_risks`
- Speichern zu: `assembly_sequence_run{N}/interaction_analysis.json`
- Checkpoint Copy zu: `data/checkpoints/{timestamp}/{assembly_name}/interaction_analysis.json`

**Features**:
- ✅ Optional: Nur aktiviert wenn `IA_mode=enabled`
- ✅ Graceful Degradation: Alte Checkpoints ohne IA funktionieren
- ✅ FFA Integration Optional: Nur wenn `FFA_include_interaction_analysis=true`
- ✅ Image Downscaling mit PIL Fallback
- ✅ Monopart Rendering Optional
- ✅ Duplicate Part Handling (_copy1, _copy2 → base part)

**Documentation Updates**:
- ✅ INTERACTION_ANALYSIS_SPEC.md - Status zu "FULLY IMPLEMENTED"
- ✅ README.md - IA Node added to project structure
- ✅ WORKFLOW_DATA_IO_GUIDE.md - Node 9 neu dokumentiert mit I/O Details
- ✅ QUICK_REFERENCE.md - IA Node Info (optional)

---

**Status**: Alle Phasen 1-4 erfolgreich implementiert und getestet ✅

**Naming Convention: ALL_UNDERSCORES** (`file_name.json`)

**Produktive Dateinamen:**
- Stepparser: `part_001_Data_stepparser.json`, `{assembly}_BOM.json`, `{assembly}_Overview_Stepparser.json`
- Enrichment: `{assembly}_Overview_Enriched.json`, `part_001_Data_enriched.json`, `part_001_Data_enriched_merged.json`
- BOM Merge: `{assembly}_BOM_enriched.json` (merged_bom_reduced.json entfernt)
- Folders: `assembly_{assembly}/` (kein .STEP suffix mehr)

**Universelles JSON-Loader-Tool**: `extract_json_keys_from_file` in agent/tools.py
- Selective key extraction statt full JSON loading
- Part filtering via part_id_name_list
- Verwendet in allen 4 Workflow Nodes (Assembly/Monopart Describer, Assembly Sequence Gen/Val)

**Settings (configs/default_settings.yaml)**:
- Assembly Describer: `AAI_json_file_keyword`, `AAI_json_keys`, `AAI_part_id_list`
- Monopart Describer: `AMI_json_file_keyword`, `AMI_json_keys`, `AMI_part_id_list`
- Assembly Sequence Gen: `ASG_json_file_keyword: "BOM_enriched"`, `ASG_json_keys`, `ASG_part_id_name_list`
- Assembly Sequence Val: `ASV_json_file_keyword: "BOM_enriched"`, `ASV_json_keys`, `ASV_part_id_name_list`

**Strukturelle Änderungen**:
- ✅ Enriched metadata flattened (kein `metadata_monopart_enriched.analysis` wrapper mehr)
- ✅ `.STEP` extension automatisch entfernt
- ✅ `name` field aus stepparser entfernt (ersetzt durch `part_name_guess` nach enrichment)
- ✅ Backward compatibility durch Fallbacks (versucht neue Namen zuerst, dann alte)

**⚠️ NO STRICT BACKWARD COMPATIBILITY** - Neue Files verwenden neue Namen

---

## ✅ Assembly Sequence v3 Structure (KOMPLETT - 28.01.2026)

**Status**: Optimierte, flache Struktur implementiert ✅

**Neue Struktur**:
- `belongs_to`: Klares Feld statt verschachtelter Subassemblies ("Assembly (basic config)" oder "Subassy 1", "Subassy 2")
- `step_description`: Aussagekräftige Beschreibung pro Step
- `joining_process`: Prozesstyp (Insert, Screw, Press-fit, Place, etc.)
- Keine `Subassembly`-Klasse mehr - flache Step-Liste

**Rendering-Optimierungen**:
- Flache Ordnerstruktur: Alle Bilder direkt in `sequence_renderings/`
- Neue Dateinamen: `Step_{ID}_{belongs_to}_{basepart}_{joining_parts}_{process}_{view}.png`
- Beispiel: `Step_01_Subassy1_part001_part003_copy1+part003_copy2_Insert_isometric.png`
- Automatische Bereinigung ungültiger Zeichen in Dateinamen

**Prompt v3**:
- `generate_assembly_sequence_v3` in prompts.yaml
- Klare Anweisungen für `belongs_to`-Feld
- Vereinfachte Subassembly-Logik

**Code-Änderungen**:
- `agent/structured_output.py`: AssemblyStep mit belongs_to, step_description, joining_process
- `agent/Assembly_sequence_validation.py`: Rendering mit neuen Dateinamen, Subassembly-Expansion vor Part-Expansion
- `configs/default_settings.yaml`: ASG_prompt_id = "generate_assembly_sequence_v3"

---

## ✅ FFA Assessment Node (KOMPLETT - 28.01.2026)

**Status**: Vollständig implementiert und getestet ✅

### Implementierte Features

#### 1. ✅ **FFA Models** (agent/structured_output.py)
- ✅ Part-level assessment: `Separation`, `Handling` (nur für joining_part)
- ✅ Interaction-level assessment: `Positioning`, `Joining`
- ✅ `FFA_Assessment_Complete` mit options_analysis field für LLM reasoning
- ✅ `AssemblyStep.base_part` made Optional (initial placement: base_part=null)
- ✅ Alle Enums übersetzt und dokumentiert

#### 2. ✅ **FFA Assessment Node** (agent/FFA_assessment.py - 877 lines)
**Kernfunktionen:**
- ✅ **BOM Integration**: Loads `{assembly}_BOM_enriched.json` mit `extract_json_keys_from_file()`
- ✅ **Metadata Caching**: MD5-hash basiert, identische Parts (part_003_copy1 = part_003) bekommen gleiche Separation/Handling
- ✅ **Prior Step Filtering**: Prior images nur wenn `belongs_to` matches (keine Cross-Subassembly-Pollution)
- ✅ **Multi-Image Support**: Lädt alle Keywords (["isometric", "top"])
- ✅ **Per-Part JSON Filtering**: base_part minimal keys, joining_part extended keys
- ✅ **Export**: JSON (full + stripped), Excel (.xlsx), CSV (utf-8-sig)

#### 3. ✅ **FFA Prompt & Settings**
- ✅ `ffa_assessment_full_v1` in prompts.yaml - Part-level vs Interaction-level Logik
- ✅ Settings in default_settings.yaml: FFA_mode, json_keys, image_keywords, downscale
- ✅ Test script: `test_ffa_assessment.py` - Auto-finds latest experiment, loads BOM

#### 4. ⏸ **Workflow Integration** (OFFEN)
**TODO:** Node `_node_assess_ffa()` in Workflow_enrich_data.py erstellen

---

## ✅ FFA Evaluation System (KOMPLETT - 13.02.2026)

**Status**: Macro-Average fokussierte Evaluation vollständig implementiert ✅

### Implementierte Features

#### 1. ✅ **Core Metrics Module** (evaluation/ffa_metrics.py - 361 lines)
- ✅ `load_ffa_data()` - Lädt Predictions vs GT mit Format-Flexibilität
- ✅ `extract_field_values()` - Extrahiert Feldwerte aus nested Struktur (assessment.category.field)
- ✅ `calculate_macro_metrics()` - Macro F1/Precision/Recall (PRIMARY)
- ✅ `calculate_per_class_metrics()` - Per-Class Details mit TP/FP/FN
- ✅ `calculate_confusion_matrix_data()` - CM mit allen möglichen Labels
- ✅ `evaluate_assembly()` - Evaluiert alle 14 FFA Felder für Assembly
- ✅ `evaluate_experiment()` - Aggregiert alle Assemblies
- ✅ `rank_assemblies()` - Sortiert Best→Worst nach Macro F1
- ✅ `create_class_distribution_analysis()` - Imbalance-Analyse

#### 2. ✅ **Visualization Module** (evaluation/ffa_visualization.py - 350+ lines)
- ✅ `save_confusion_matrix()` - Heatmaps pro Feld
- ✅ `save_per_class_metrics_chart()` - Bar Charts (Precision/Recall/F1)
- ✅ `save_assembly_summary_chart()` - Alle Felder Color-Coded (grün/orange/rot)
- ✅ `save_class_distribution_heatmap()` - Zeigt Imbalance visual
- ✅ `save_macro_comparison_chart()` - Experimente vergleichen
- ✅ `save_assembly_ranking_chart()` - Red→Green Gradient Ranking
- ✅ `save_step_overview_chart()` - Schritt-Level Übersicht

#### 3. ✅ **Orchestrator** (run_ffa_evaluation.py - 500+ lines)
- ✅ Entdeckt alle Experimente in ffa_experiments/
- ✅ Auto-konvertiert Stripped→Enum Format (cached in enum_cache/)
- ✅ Lädt FFA Predictions vs GT aus data/ground_truth/ffa_ground_truth/
- ✅ Berechnet Metriken für alle 14 FFA Felder
- ✅ Erstellt Pro-Assembly-Visualisierungen
- ✅ Generiert Root-Level Comparison Charts
- ✅ Output Struktur: evaluation/{exp_name}/{assembly_name}/

#### 4. ✅ **Handling Special Cases**
- ✅ Class Imbalance: Alle Labels in CM & Per-Class Metrics (auch fehlende)
- ✅ Nested Structure: extract_field_values() detektiert assessment.category.field
- ✅ Format Conversion: Stripped→Enum über ffa_str_to_enum.convert_ffa_stripped_to_enum()
- ✅ Missing Minority Classes: F1-Werte korrekt berechnet mit Fallback auf 0

#### 5. ✅ **Documentation** (KOMPLETT)
- ✅ evaluation/EVALUATION_README.md - Comprehensive API & Usage Guide
- ✅ WORKFLOW_DATA_IO_GUIDE.md - Section "Evaluation System (NEW)"
- ✅ QUICK_REFERENCE.md - Quick Start für FFA Evaluation
- ✅ README.md - Updated mit Evaluation System Overview

### Metrics Erklärung

**Macro-Average (PRIMARY):**
- Macro F1: Average F1 über alle Klassen (unabhängig von Imbalance)
- Macro Precision: Average Precision pro Klasse
- Macro Recall: Average Recall pro Klasse
- ➜ Ideal für unausgewogene Daten

**Per-Class Breakdown:**
- Precision, Recall, F1, Support (samples in GT)
- TP, FP, FN für detaillierte Analyse
- Zeigt Performance-Unterschiede zwischen Klassen

**Micro-Metrics (Reference):**
- Micro Accuracy: Gesamtgenauigkeit
- Weighted F1: Gewichtet nach Sample-Anzahl
- ⚠️ Kann mit Imbalance irreführend sein

### Usage

```bash
# Einfach ausführen - evaluiert alle Experimente
python run_ffa_evaluation.py

# Output:
# data/experiments/ffa_experiments/evaluation/
#   ├── summary.json
#   ├── macro_f1_comparison.png
#   ├── assembly_ranking.png
#   └── {exp_name}/{assembly_name}/
#       ├── confusion_matrix_*.png (14 Felder)
#       ├── per_class_*.png
#       ├── assembly_summary.png
#       ├── class_distribution_heatmap.png
#       └── metrics.json
```

---

## 📝 Weitere TODOs

### Workflow Integration (Prio 1)

---

## ✅ FFA Assessment Node (KOMPLETT - 28.01.2026)

**Status**: Vollständig implementiert und getestet ✅

### Implementierte Features

#### 1. ✅ **FFA Models** (agent/structured_output.py)
- ✅ Part-level: `Separation`, `Handling` (nur für joining_part)
- ✅ Interaction-level: `Positioning`, `Joining`
- ✅ `FFA_Assessment_Complete` mit `options_analysis` für LLM reasoning
- ✅ `AssemblyStep.base_part` Optional (initial placement: base_part=null)

#### 2. ✅ **FFA Assessment Node** (agent/FFA_assessment.py - 877 lines)
**Kernfunktionen:**
- ✅ **BOM Integration**: `{assembly}_BOM_enriched.json` mit `extract_json_keys_from_file()`
- ✅ **Metadata Caching**: MD5-hash, identische Parts (part_003_copy1 = part_003_copy2) → gleiche FFA
- ✅ **Prior Step Filtering**: Prior images nur wenn `belongs_to` matches
- ✅ **Multi-Image**: Lädt alle Keywords (["isometric", "top"])
- ✅ **Per-Part JSON Filtering**: base_part minimal, joining_part extended
- ✅ **Export**: JSON (full + stripped), Excel, CSV

**Ausgabe:**
```
ffa_assessment/
├── ffa_assessment.json (full data)
├── ffa_assessment_stripped.json (criteria only)
├── ffa_assessment.xlsx (Excel)
└── ffa_assessment.csv (CSV)
```

#### 3. ✅ **Prompt & Settings**
- ✅ `ffa_assessment_full_v1` in prompts.yaml
- ✅ Settings in default_settings.yaml (FFA_mode, json_keys, keywords, downscale)
- ✅ Test: `test_ffa_assessment.py` - Auto-finds experiment & BOM

#### 4. ⏸ **Workflow Integration** (OFFEN - Next Task)
**TODO:** Node `_node_assess_ffa()` in Workflow_enrich_data.py

---

## � CURRENT: System/Human Message Separation (Start: 29.01.2026)

**Ziel**: Trennung von System-Message (Rolle/Instruktionen) und Human-Message (Task/Daten) für alle LLM-Nodes

**Strategie**: Harte Migration, keine Backward Compatibility für alte Prompts

### Phase 1: Prompts aufteilen und erstellen ✅
- [ ] **prompts.yaml erweitern**
  - [ ] System Messages erstellen:
    - [ ] `cad_analysis_expert_v1` (für AAI + AMI)
    - [ ] `assembly_planner_expert_v1` (für ASG)
    - [ ] `critical_reviewer_v1` (für ASV)
    - [ ] `automation_expert_v1` (für FFA)
  - [ ] Human/Task Messages erstellen:
    - [ ] `assembly_analysis_task_v1` (AAI - aus assembly_describer_v1)
    - [ ] `monopart_analysis_task_v1` (AMI - aus monopart_describer_v1)
    - [ ] `generate_assembly_sequence_task_v3` (ASG - aus generate_assembly_sequence_v3)
    - [ ] `validate_assembly_sequence_task_v1` (ASV - aus validate_assembly_sequence_v1)
    - [ ] `ffa_assessment_task_v1` (FFA - aus ffa_assessment_full_v1)

### Phase 2: Settings erweitern ✅
- [ ] **default_settings.yaml updaten**
  - [ ] Global: `base_system_prompt_id: "cad_analysis_expert_v1"`
  - [ ] AAI settings: `AAI_system_prompt_id: null`, `AAI_human_prompt_id: "assembly_analysis_task_v1"`
  - [ ] AMI settings: `AMI_system_prompt_id: null`, `AMI_human_prompt_id: "monopart_analysis_task_v1"`
  - [ ] ASG settings: `ASG_system_prompt_id: "assembly_planner_expert_v1"`, `ASG_human_prompt_id: "generate_assembly_sequence_task_v3"`
  - [ ] ASV settings: `ASV_system_prompt_id: "critical_reviewer_v1"`, `ASV_human_prompt_id: "validate_assembly_sequence_task_v1"`
  - [ ] FFA settings: `FFA_system_prompt_id: "automation_expert_v1"`, `FFA_human_prompt_id: "ffa_assessment_task_v1"`
  - [ ] Alte Settings entfernen: `prompt_id_assy`, `prompt_id_monopart`, `ASG_prompt_id`, `FFA_prompt_id`

### Phase 3: Helper-Funktion implementieren ✅
- [ ] **agent/prompt_store.py erweitern**
  - [ ] `get_system_and_human_prompts(node_prefix, settings)` implementieren
  - [ ] Fallback-Logik: `{NODE}_system_prompt_id` → `base_system_prompt_id`
  - [ ] Tests: Alle 5 Nodes (AAI, AMI, ASG, ASV, FFA)

### Phase 4: Code-Anpassungen (Node für Node) ✅
- [x] **AAI: agent/tools.py - analyse_assembly_img & _describe_images_in_dir_impl**
  - [x] `get_system_and_human_prompts("AAI", settings)` verwenden
  - [x] Message-Konstruktion ändern: `[{"role": "system", ...}, {"role": "user", "content": [...]}]`
  - [x] Alte `prompt_id` Parameter entfernt

- [x] **AMI: agent/tools.py - analyse_monopart_img**
  - [x] `get_system_and_human_prompts("AMI", settings)` verwenden
  - [x] Message-Konstruktion ändern (teilt sich Code mit AAI)
  - [x] JSON-Kontext in Human-Message einbetten (nicht in System-Message)

- [x] **ASG: agent/Assembly_sequence_generation.py - generate_assembly_sequence**
  - [x] `get_system_and_human_prompts("ASG", settings)` verwenden
  - [x] Bestehende System/Human-Trennung beibehalten (bereits korrekt)
  - [x] Settings-Namen updaten (`ASG_prompt_id` → `ASG_human_prompt_id`)

- [x] **ASV: agent/Assembly_sequence_validation.py - validate_assembly_sequence_step**
  - [x] `get_system_and_human_prompts("ASV", settings)` verwenden
  - [x] Message-Konstruktion zu System+Human ändern (aktuell nur HumanMessage)
  - [x] Prompt-ID aus Settings laden

- [x] **FFA: agent/FFA_assessment.py - assess_step_ffa**
  - [x] `get_system_and_human_prompts("FFA", settings)` verwenden
  - [x] Message-Konstruktion zu System+Human ändern
  - [x] `FFA_prompt_id` → `FFA_human_prompt_id`

### Phase 5: Testing & Cleanup ⏳
- [ ] **Smoke Tests durchführen**
  - [ ] AAI: Assembly-Bilder analysieren
  - [ ] AMI: Part-Bilder analysieren
  - [ ] ASG: Assembly Sequence generieren
  - [ ] ASV: Sequence validieren
  - [ ] FFA: FFA Assessment durchführen

- [ ] **Alte Prompts entfernen** (Hard Migration)
  - [ ] `assembly_describer_v1` aus prompts.yaml löschen
  - [ ] `monopart_describer_v1` aus prompts.yaml löschen
  - [ ] `generate_assembly_sequence_v1`, `_v2` aus prompts.yaml löschen
  - [ ] `ffa_assessment_full_v1` umbenennen oder entfernen

- [ ] **Dokumentation updaten**
  - [ ] GETTING_STARTED.md: Neue Prompt-Struktur erklären
  - [ ] MIGRATION_GUIDE.md: Breaking Change dokumentieren
  - [ ] QUICK_REFERENCE.md: Settings-Übersicht aktualisieren

---

## ✅ Textbased Data Restructuring (KOMPLETT - 02.02.2026)

**Status**: Neue Verzeichnisstruktur für textbasierte Daten implementiert ✅

**Alte Struktur (deprecated):**
- `data/input/Additional_info/{assembly_name}.txt`
- `data/input/assembly_order/{assembly_name}.[json|txt]`

**Neue Struktur:**
- `data/input/Textbased_Data/{assembly_name}/`
  - `additional_info_{assembly_name}.txt`
  - `assembly_sequence_{assembly_name}.txt`
  - `remarks_{assembly_name}.txt` (neu)
  - `ground_truth_sequence_{assembly_name}.txt` (neu)

**Implementierte Features:**
- ✅ **agent/config.py**: Neue `textbased_data_root` Property, alte Properties deprecated
- ✅ **agent/core/text_processor.py**: 
  - `load_additional_info()` aktualisiert für neue Struktur
  - `load_assembly_order()` aktualisiert (nur noch TXT, kein JSON mehr)
- ✅ **agent/Assembly_sequence_generation.py**:
  - `attach_additional_info()` aktualisiert
  - `attach_assembly_order()` aktualisiert
  - `attach_remarks()` neu implementiert
  - `attach_ground_truth_sequence()` neu implementiert
- ✅ **run_file_preparation.py**: Erstellt alle 4 Dateien automatisch pro Assembly
- ✅ **Settings erweitert**:
  - `ASG_include_remarks: false` (default aus)
  - `ASG_include_GT_sequence: false` (default aus)
- ✅ **configs/default_settings.yaml** & **configs/experiments/exp1_baseline.yaml**: Neue Settings hinzugefügt

**Verwendung:**
- Remarks: Wichtige Notizen/Hinweise für die Assembly (optional)
- Ground Truth: Referenzsequenz zum Vergleich/Training (optional)
- Beide Features per Setting aktivierbar, erscheinen als separate Sektionen im Prompt

---

## ✅ FFA Ground Truth Encoder (KOMPLETT - 09.02.2026)

**Status**: String → Integer Konvertierung implementiert ✅

**Neue Datei**: `agent/ffa_ground_truth.py`

**Features:**
- ✅ **Enum Mapping Creation**: Automatisches Extrahieren aller FFA-Enums aus structured_output.py
- ✅ **String → Integer Conversion**: Konvertiert `ffa_assessment_stripped.json` zu integer-kodierten Daten
- ✅ **1-basierte Nummerierung**: Antwortoptionen starten bei 1 (null → 0)
- ✅ **Global Mapping File**: `ffa_enum_mapping.json` (einmalig pro Conversion-Run)
- ✅ **Batch Processing**: Verarbeitet alle Assemblies in einem Experiment-Ordner
- ✅ **Error Reporting**: Detaillierter Print-Report mit Assembly-Name + Step-ID

**Output-Struktur:**
```
data/experiments/{run_id}/{config}/
└── evaluation/
    └── run_20260209_143022/
        ├── ffa_enum_mapping.json           # Global mapping (String → Int)
        ├── worm_gear_demonstrator_ffa_assessment_enum.json
        ├── IPA_Cranfield_ffa_assessment_enum.json
        └── ...
```

**Verwendung:**
```bash
python -m agent.ffa_ground_truth data/experiments/run_2026-02-06_112449/default
```

**TODO (Prio 3):**
- [x] **Reverse Conversion**: `convert_ffa_enum_to_string()` implementieren (Integer → String)
  - ✅ Implementiert in agent/ffa_enum_to_str.py
  - ✅ Auto-detection von latest evaluation run
  - ✅ Output: `{assembly}_ffa_assessment_str.json`

---

## ✅ FFA Evaluation System (KOMPLETT - 10.02.2026)

**Status**: Complete ML evaluation pipeline mit Confusion Matrices ✅

**Neue Datei**: `agent/ffa_evaluation.py` (1100+ Zeilen)

**Features:**
- ✅ **3-Level Metrics**:
  - Per-Field (14 FFA-Felder): Accuracy, Precision, Recall, F1-Score (macro)
  - Per-Subprocess (4 Subprocesses): Aggregiert (separation, handling, positioning, joining)
  - Per-Assembly: Field-level metrics für jedes Assembly separat
  - Overall: Weighted + Mean aggregation
- ✅ **Full-Size Confusion Matrices**: Alle möglichen Enum-Klassen (1,2,3,...,N) auch wenn nicht in Daten
- ✅ **Assembly-Level CMs**: 14 Confusion Matrices pro Assembly (gleiche Struktur wie global)
- ✅ **String Labels**: Format `[1] rigid`, `[2] flexible` mit max 20 chars
- ✅ **Auto-Detection**: Latest run in `data/evaluation/` automatisch finden
- ✅ **Custom Farbschema**:
  - Confusion Matrices: Weiß → Grün (#179C7D)
  - Balkendiagramme: Orange (#F58220)
- ✅ **Misclassification Tracking**: Assembly + Step-ID für jeden Fehler

**Output-Struktur:**
```
data/evaluation/run_20260209_120113/evaluation_results/
├── metrics_summary.json              # Overall aggregated metrics
├── metrics_per_field.json            # 14 fields mit CMs + misclassifications
├── metrics_per_subprocess.json       # 4 subprocesses
├── metrics_per_assembly.json         # Per-assembly aggregations
├── confusion_matrices/               # Global field CMs
│   ├── nature_of_provision_cm.png
│   ├── part_rigidity_cm.png
│   └── ... (14 total)
├── confusion_matrices_per_assembly/  # Assembly-specific
│   └── worm_gear_demonstrator/
│       ├── nature_of_provision_cm.png
│       └── ... (14 per assembly)
├── f1_scores_per_field.png          # Bar chart
├── f1_scores_per_subprocess.png     # Bar chart
└── performance_per_assembly.png     # Comparison chart
```

**Verwendung:**
```bash
# Auto-detect latest run
python agent/ffa_evaluation.py

# Specific run
python agent/ffa_evaluation.py data/evaluation/run_20260209_120113
```

**Workflow:**
1. `ffa_str_to_enum.py` → Create enum encoding from latest experiment
2. Manually create/update ground truth files in `data/evaluation/ground_truth/`
3. `ffa_evaluation.py` → Run evaluation, generate metrics + visualizations

---

## � Data Restructuring & Checkpoint System (Prio 1 - IN PROGRESS - Start: 13.02.2026)

**Ziel**: Ermögliche Re-running von FFA Assessment mit variierten Settings ohne Neuberechnung der Sequenz

**Strategie**: Hybrid Checkpoint-System (Option 3) mit referenzierten Stepparser-Renderings

### Phase 1: Checkpoint-Struktur etablieren
- [ ] **Neue Verzeichnisstruktur:**
  ```
  data/checkpoints/
  └── {assembly_name}/
      └── {timestamp}/
          ├── metadata.json              # Settings + stepparser reference
          ├── assembly_sequence.json     # Aus Node 7
          ├── sequence_renderings/       # Aus Node 8
          ├── BOM_enriched.json          # Aus Node 6
          └── enriched_parts/            # Aus Node 5
  ```
  
- [ ] **metadata.json Struktur:**
  ```json
  {
    "assembly_name": "Connecting_Rod",
    "timestamp": "2026-02-13T15:30:00Z",
    "checkpoint_version": 1,
    "stepparser_renderings_path": "../../../stepparser/Connecting_Rod/assembly_Connecting_Rod",
    "sequence_generation_settings": {...},
    "validation_settings": {...}
  }
  ```

### Phase 2: Checkpoint-Erstellung in run_all_nodes
- [ ] **Node 8 (render_assembly_steps) erweitern:**
  - Nach erfolgreichem Rendering → `create_checkpoint()` aufrufen
  - Kopiere assembly_sequence.json, BOM, enriched_parts zu `data/checkpoints/`
  - Schreibe metadata.json mit Settings + stepparser reference
  
- [ ] **New function: `create_checkpoint()`**
  - Input: exp_output_dir, assembly_name, current_settings
  - Output: checkpoint_path (für Logging)
  - Handles: Verzeichnis-Erstellung, Datei-Kopien, metadata.json Schreibenā
  - Location: `agent/workflow.py` oder `agent/utils.py`

### Phase 3: run_assess_ffa_only Workflow (NEW)
- [ ] **New entry point: `run_assess_ffa_only()`**
  - File: `agent/workflow.py` (neben run_all_nodes)
  - Input Parameter:
    - `checkpoint_path`: Pfad zu `data/checkpoints/{assembly}/{timestamp}/`
    - `ffa_settings_overrides`: Dict mit FFA-Setting Overrides (optional)
  - Workflow:
    1. Load metadata.json von checkpoint_path
    2. Validiere dass assembly_sequence.json + sequence_renderings vorhanden
    3. Lade BOM + enriched_parts
    4. Merges FFA_settings (checkpoint defaults + overrides)
    5. Erstelle neue experiment run directory in `data/experiments/{timestamp}/`
    6. Kopiere Checkpoint-Daten zu new experiment run
    7. Führe nur Node 10 (assess_ffa) aus
    8. Speichere ffa_assessment/ in new experiment run
    
- [ ] **build_ffa_only_workflow()**
  - Nur 1 Node: `_node_assess_ffa`
  - Keine Conditional Edges (direktlich zu END)
  - Location: `agent/workflow.py`

### Phase 4: Integration in run_experiments.py
- [ ] **CLI/Argument Support:**
  - Parameter: `--ffa-only` flag
  - Parameter: `--checkpoint-path` für expliziten Checkpoint
  - Parameter: `--ffa-setting-overrides` (JSON string)
  
- [ ] **Smart Checkpoint Detection:**
  - Wenn `--ffa-only` gesetzt: Auto-find latest checkpoint für assembly_name
  - Fallback: User muss explizit angeben

### Phase 5: Documentation
- [ ] **WORKFLOW_DATA_IO_GUIDE.md aktualisieren:**
  - Neue Checkpoint-Struktur dokumentieren
  - `run_assess_ffa_only` Workflow beschreiben
  - Data-Flow Diagramm für FFA-only Modus
  
- [ ] **GETTING_STARTED.md:**
  - Neue Use-Case "Vary FFA Settings" hinzufügen

---

## 📝 Weitere TODOs

### Workflow Integration (Prio 2)
- [x] **FFA Node Integration**: `_node_assess_ffa()` in Workflow_enrich_data.py ✅
  - Bereits implementiert in agent/workflow.py
  
- [ ] **run_assess_ffa_only Workflow**: Siehe Phase 3-5 oben (Prio 1)

### Tests & Validierung (Prio 3)
- [ ] Edge Case Tests: Fehlende Keys, leere Listen mit extract_json_keys_from_file
- [ ] Assembly Sequence v3: Integration Tests mit komplexen Subassemblies
- [ ] FFA Assessment: End-to-end test über Workflow

### FFA Enhancements (Später)
- [ ] **FFA Report**: HTML/PDF Export für manuelle Review
- [ ] **FFA Analytics**: Automation feasibility scoring über alle Steps
- [ ] **FFA Optimization**: Suggest sequence modifications für bessere FFA scores
- [ ] **Batch Evaluation**: Multi-run comparison (Experiment A vs B)
- [ ] **Label Mode Option**: CLI parameter für 'enum' vs 'str' labels in CMs

### Iteration Loop Enhancements (Niedrige Priorität)
- [ ] **Assembly Sequence JSON Update**: Merge validator feedback direkt in assembly_sequence.json
- [ ] **Rendering Optimization**: Skip re-rendering bei unveränderter sequence (hash comparison)
- [ ] **User-Facing Report**: HTML Report mit Iteration-Summary (run_1, run_2, run_3 diffs)

---

## ✅ Checkpoint System Implementation (COMPLETED - 14.02.2026)

**6-Phase Implementation vollständig abgeschlossen:**

### Phase 1: ✅ Checkpoint-Struktur
- Fully standalone design (Option A)
- Per-assembly subdirectories mit vollständigen Daten

### Phase 2: ✅ Utilities (agent/checkpoint_utils.py)
- 4 functions für copy/create/validate/load
- 235 Zeilen, vollständig getestet

### Phase 3: ✅ Node 8 Integration
- Checkpoint creation nach erfolgreichem Rendering
- Non-fatal error handling
- Settings captured in metadata

### Phase 4: ✅ FFA-only Workflow
- `build_ffa_only_workflow()` - Single-node graph
- `run_assess_ffa_only()` - Multi-assembly processor
- 111 Zeilen, vollständig functional

### Phase 5: ✅ CLI Integration (run_experiments.py)
- Argparse-based argument handling
- Checkpoint validation vor execution
- Detailed error messages + summary output
- Exit codes für scripting

### Phase 6: ⏳ Documentation (Next)
- Update WORKFLOW_DATA_IO_GUIDE.md
- Update GETTING_STARTED.md

---

