# Quick Reference: Assembly Sequence & Interaction Analysis Nodes

**Für Entwickler & Projektpartner**

Schneller Überblick über die Assembly Sequence, Validation, und Interaction Analysis Features.

---

## 🎯 Was wird gebaut?

Drei neue Workflow Nodes:

1. **generate_assembly_sequence**: LLM analysiert Bilder → schlägt Montagereihenfolge vor
2. **validate_assembly_sequence**: Rendert jeden Schritt → LLM prüft Feasibility
3. **interaction_analysis** ✅ NEW: Analysiert geometrische Interaktionen (Contact/Alignment/Collision)

---

## 📊 Workflow-Reihenfolge

```
┌──────────────────┐
│  resolve_paths   │
└────────┬─────────┘
         │
┌────────▼─────────┐
│  run_assembly    │  ← Vision LLM: Assembly Bilder analysieren
└────────┬─────────┘
         │
┌────────▼─────────┐
│  run_monoparts   │  ← Vision LLM: Einzelteil Bilder analysieren
└────────┬─────────┘
         │
┌────────▼─────────┐
│   merge_bom      │  ← Alle part JSONs konkatenieren
└────────┬─────────┘
         │
┌────────▼──────────────────────┐
│ generate_assembly_sequence    │  ⭐ Montagereihenfolge generieren
└────────┬───────────────────────┘
         │
┌────────▼──────────────────────┐
│ render_assembly_steps         │  ← Rendert Schritt-Visualisierungen
└────────┬───────────────────────┘
         │
┌────────▼──────────────────────┐
│ interaction_analysis          │  ✅ NEW: Geometrische Interaktionen (Contact/Alignment/Collision)
└────────┬───────────────────────┘
         │
┌────────▼──────────────────────┐
│ validate_assembly_sequence    │  ← Optional: Per-Step LLM Validierung
└────────┬───────────────────────┘
         │
┌────────▼──────────────────────┐
│ assess_ffa                    │  ← FFA mit optionalem Interaction Context
└────────┬───────────────────────┘
         │
       ┌─▼─┐
       │END│
       └───┘
```

---

## 🔧 Konfiguration (exp.yaml)

```yaml
# configs/experiments/exp_custom.yaml

# Workflow Aktivierung
enable_merge_bom: true
enable_assembly_sequence: true              # Generierung einschalten
enable_sequence_validation: true            # ⭐ UPDATED: Validierung per exp1/exp2
enable_ffa_assessment: false                # TBD

# Bilder für Assembly Sequence Generation
assembly_sequence_image_keywords:
  - "exploded"                              # Explosionszeichnung
  - "isometric"                             # 3D Ansicht

# JSONs für Assembly Sequence Generation
assembly_sequence_json_keywords:
  - "merged_bom"                            # Input: merged BOM

# Validierung: Bilder für Step-by-Step Prüfung
validate_sequence_step_img_keywords:
  - "isometric"
ASV_step_img_keywords:
  - "isometric"                             # Pro Schritt: isometric View
  # Optional: ["isometric", "front", "top", "side"] für alle 4 Views
ASV_json_keywords:
  - "merged_bom"                            # Input: BOM für Validierung
ASV_finished_assy_keywords:
  - "isometric"                             # Fertige Assembly Views

# ✅ NEW: Interaktionsanalyse
IA_mode: "enabled"                          # "disabled", "enabled", "validate_only"
IA_sequence_step_img_keywords:
  - "iso1_transp_0_3"                       # Transparent rendering für Step Analysis
IA_monopart_img_keywords:
  - "iso1_transp_0_0"                       # Opaque parts
  - "iso1_transp_0_3"                       # Transparent parts
IA_include_monopart_renderings: true        # Analyse mit Einzelteil-Bildern

# Optional: Interaction Context för FFA
FFA_include_interaction_analysis: false     # Set to true to enrich FFA with interaction context

# Interaction Analysis Prompts (configurable)
IA_system_prompt_id: "Interaction_Analyst_V2"  # Your custom prompts
IA_human_prompt_id: "Analyse_Interaction_V2"   # Or: interaction_analyst_system_v1 + interaction_analysis_task_v1
```

**Assembly Step Information Auto-Injected**:
- IA prompts automatically receive `joining_process` and `belongs_to` context
- Available in all prompt variants (V2, V1, system_v1, task_v1)
- No prompt modification needed - integrated automatically

---

## 📁 Output Struktur

```
data/experiments/exp_custom/IPA_Cranfield/
├── IPA_Cranfield_Overview_Enriched.json           # Von run_assembly
├── enriched_parts/
│   ├── part_001_Data_enriched.json                # Von run_monoparts
│   ├── part_001_Data_enriched_merged.json         # With stepparser data
│   ├── part_002_Data_enriched.json
│   └── ...
├── IPA_Cranfield_BOM_enriched.json                # merge_bom
├── assembly_sequence_run1/
│   ├── assembly_sequence.json                     # generate_assembly_sequence
│   ├── sequence_renderings/
│   │   ├── step_01_iso1_transp_0_3.png           # render_assembly_steps
│   │   └── step_02_iso1_transp_0_3.png
│   ├── interaction_analysis.json                  # ✅ interaction_analysis (NEW)
│   └── assembly_sequence_validation/              # validate_assembly_sequence
│       ├── step_01_validation.json
│       ├── step_02_validation.json
│       └── assembly_sequence_validation_merged.json
```

---

## 📋 JSON Schemas

### assembly_sequence.json

```json
{
  "assembly_sequence_id": "abc-123-...",
  "assembly_name": "IPA_Cranfield",
  "method": "llm_vision",
  "confidence": 0.85,
  
  "base_part": {
    "part_id": "Part_1",
    "part_name": "Gehäuseoberteil",
    "reason": "Largest, most stable part"
  },
  
  "steps": [
    {
      "step_number": 1,
      "description": "Gehäuseoberteil auf Tisch legen",
      "base_part": "Part_1",
      "joining_part": null,
      "joining_process": "place_on_table",
      "orientation": "Flachseite nach unten",
      "subassembly": null,
      "certainty": 95,
      "notes": "Basisteil, stabile Position"
    },
    {
      "step_number": 2,
      "description": "Lager auf Zahnrad pressen",
      "base_part": "Part_5",
      "joining_part": "Part_7",
      "joining_process": "press_fit",
      "subassembly": {
        "id": "SubAssy_1",
        "name": "Zahnrad_mit_Lager",
        "parts": ["Part_5", "Part_7"],               // ⭐ NEU
        "rationale": "Lager muss VOR Gehäuse montiert werden"  // ⭐ NEU
      },
      "certainty": 90
    }
  ],
  
  "subassemblies": [
    {
      "id": "SubAssy_1",
      "name": "Zahnrad_mit_Lager",
      "parts": ["Part_5", "Part_7"],                   // ⭐ NEU
      "formed_at_step": 2,
      "rationale": "Lager muss VOR Gehäuse montiert werden"  // ⭐ NEU
    }
  ],
  
  "total_steps": 4
}
```

### assembly_sequence_validation.json

```json
{
  "validation_id": "xyz-456-...",
  "assembly_sequence_id": "abc-123-...",  // Ref zu generierter Sequence
  "validated_at": "2026-01-18T14:30:00Z",
  
  "overall_confidence": 0.88,
  "validation_result": "APPROVED_WITH_SUGGESTIONS",
  
  "feedback": {
    "step_1": {
      "status": "OK",
      "comment": "Base part correct"
    },
    "step_2": {
      "status": "WARNING",
      "comment": "Press-fit orientation unclear from images",
      "suggested_change": null
    },
    "step_3": {
      "status": "CRITICAL",
      "comment": "Collision detected: Screw access blocked",
      "suggested_change": "Swap step 2 and 3"
    }
  },
  
  "corrected_sequence": {
    "changes_made": true,
    "modified_steps": [2, 3],
    "new_order": [1, 3, 2, 4]
  }
}
```

### interaction_analysis.json (NEW - ✅ 24. Feb 2026)

```json
{
  "analysis_metadata": {
    "assembly_name": "IPA_Reducer_Case",
    "analysis_timestamp": "2026-02-23T08:16:33Z",
    "config": {
      "system_prompt_id": "Interaction_Analyst_V2",
      "human_prompt_id": "Analyse_Interaction_V2"
    }
  },
  "steps": [
    {
      "step_id": 1,
      "belongs_to": "Assembly (basic config)",
      "base_part": "part_001",
      "joining_part": ["part_002"],
      "step_description": "Insert bearing into shaft",
      
      "interaction_analysis": {
        "analysis_summary": "Press-fit interface with high contact area",
        
        "accuracy_of_target_position": "Medium precision (±0.5mm) for bore concentricity",
        "positioning_aids": "Cylindrical shaft centers bearing; shoulder provides axial reference",
        "additional_orientation_by_rotation": "Bearing has rotational symmetry; free to rotate",
        "accessibility_to_joining_position": "Full access from assembly top; manual/automated insertion",
        "joining_motion": "Linear axial insertion; ~50mm depth along shaft",
        "joining_tolerances": "Tight H7/n6 fit for load transmission",
        "stability_in_positioned_state": "Axially stable post-seating; shoulder prevents removal",
        "feeding_of_joining_element": "Bearing manually/robotically fed; self-alignment via shaft",
        "fixing_of_mounted_part": "Press-fit creates mechanical lock; no additional fasteners",
        
        "analysis_metadata": {
          "images_used": {
            "sequence_renderings": ["step_01_iso1_transp_0_3.png"],
            "monopart_renderings": {
              "part_001": ["part_001-iso1_transp_0_0.png"],
              "part_002": ["part_002-iso1_transp_0_0.png", "part_002-iso1_transp_0_3.png"]
            }
          },
          "analysis_tokens_used": 1843,
          "model": "gpt-4o-vision"
        }
      }
    }
  ],
  
  "summary": {
    "total_steps_analyzed": 2,
    "average_confidence": 0.90
  }
}
```

**Key: 9 Interaction Categories** 
- All fields are automatically validated by Pydantic schema
- Assembly step context (joining_process, belongs_to) automatically injected into prompt
- Structured output enforced at LLM response level

---

## 🖼️ Prompt Attachments System

### Bilder mit Keywords filtern

```python
from agent.core.prompt_builder import attach_images_by_keywords

# Lädt NUR Bilder mit "exploded" oder "Top" im Dateinamen
images = attach_images_by_keywords(
    searchdir="data/processed/stepparser/IPA_Cranfield/Assembly_1",
    keywords=["exploded", "Top"]
)

# Result:
# [
#   {"path": "...-exploded.png", "b64": "...", "mime": "image/png"},
#   {"path": "...-Top.png", "b64": "...", "mime": "image/png"}
# ]
```

### JSONs mit Keywords filtern

```python
from agent.core.prompt_builder import attach_jsons_by_keywords

# Lädt NUR JSONs mit "merged_bom" im Dateinamen
jsons = attach_jsons_by_keywords(
    searchdir="data/experiments/exp1/IPA_Cranfield",
    keywords=["merged_bom"]
)

# Result:
# [
#   {"filename": "IPA_Cranfield_BOM_enriched.json", "content": {...}}
# ]
```

### Optional: Additional Info TXT

```python
from agent.core.prompt_builder import attach_additional_info

# Lädt data/input/Additional_info/IPA_Cranfield.txt (falls vorhanden)
txt = attach_additional_info("IPA_Cranfield")

# Result: String oder None
```

### Optional: Manuelle Assembly Order

```python
from agent.core.prompt_builder import attach_assembly_order

# Lädt data/input/assembly_order/IPA_Cranfield.json (falls vorhanden)
manual_order = attach_assembly_order("IPA_Cranfield")

# Result: dict oder None
```

---

## 🎨 Rendering System

### Views die gerendert werden

Für jeden Montageschritt werden **ALLE** Views gerendert:

1. **isometric**: 3D Ansicht von schräg oben
2. **front**: Frontansicht
3. **top**: Draufsicht
4. **side**: Seitenansicht
5. **explosion**: Explosionszeichnung mit nächstem Teil highlighted

### Farben bleiben konsistent!

Der Renderer aus `stepparser.rendering.Renderer` nutzt die bereits zugewiesenen Farben:
- Gleiche Geometrie = Gleiche Farbe (basierend auf Geometry Hash)
- Farben bleiben über alle Renderings hinweg konsistent

### Beispiel: Step 2 Renderings

```
visualizations/
  step_02_isometric.png   ← Zeigt: Part_1 + Part_5 in Endposition
  step_02_front.png       ← Zeigt: Part_1 + Part_5 in Endposition
  step_02_top.png         ← Zeigt: Part_1 + Part_5 in Endposition
  step_02_side.png        ← Zeigt: Part_1 + Part_5 in Endposition
  step_02_explosion.png   ← Zeigt: Part_1 + Part_5 exploded + Part_7 highlighted
```

**Hinweis**: Dem LLM werden nur die Views geschickt, die in `sequence_validation_view_keywords` definiert sind!

---

## 🧪 Testing

### Test einzelne Funktionen

```bash
# Test Prompt Builder
python -c "
from agent.core.prompt_builder import attach_images_by_keywords
imgs = attach_images_by_keywords('data/processed/stepparser/IPA_Cranfield/Assembly_1', ['exploded'])
print(f'Found {len(imgs)} images')
"

# Test Merge BOM
python -m agent.workflows.nodes.merge_bom

# Test Assembly Sequence Generation
python -m agent.workflows.nodes.generate_assembly_sequence
```

### Test End-to-End

```bash
# Mit Validation deaktiviert
python run_experiments.py

# Mit Validation aktiviert (in exp.yaml: enable_sequence_validation: true)
python run_experiments.py
```

---

## 💡 Tipps für Entwicklung

### 1. Debugging: Welche Bilder werden geladen?

```python
# In Node Code:
images = attach_images_by_keywords(assembly_dir, image_keywords)
print(f"[DEBUG] Loaded {len(images)} images:")
for img in images:
    print(f"  - {img['path']}")
```

### 2. Rendering Performance

Große Assemblies (>50 Parts) können langsam sein beim Rendern:
- **Workaround**: Nur wichtige Views rendern (z.B. nur isometric + front)
- **Config**: `render_all_views: false` + manuell Views auswählen (Future Feature)

### 3. Token Limits

Bei sehr vielen Bildern (>10) kann Token Limit erreicht werden:
- **Workaround**: Weniger Keywords nutzen, z.B. nur `["exploded"]`
- **Alternative**: Bilder downscalen (Future Feature)

### 4. Validation Optional machen

Validation ist rechenintensiv (viele Renderings + LLM Calls):
- **Default**: `enable_sequence_validation: false`
- **Aktivieren**: Nur wenn nötig, z.B. für kritische Assemblies

---

## 🎲 FFA Evaluation (Macro-Average)

### Schnell starten

```bash
# Evaluiert alle Experimente in ffa_experiments/
python run_ffa_evaluation.py

# Output: data/experiments/ffa_experiments/evaluation/
```

### Was es macht

1. **Entdeckt** alle Experimente in `data/experiments/ffa_experiments/`
2. **Lädt** FFA Assessment Predictions (enum format)
3. **Konvertiert** stripped format → enum (wenn nötig)
4. **Berechnet** Macro-Average Metriken für 14 FFA Felder
5. **Erstellt** Confusion Matrices, Bar Charts, Heatmaps
6. **Generiert** Experiment-Vergleich & Assembly Ranking

### Output Struktur

```
data/experiments/ffa_experiments/evaluation/
├── summary.json                          ← Gesamt-Metriken
├── macro_f1_comparison.png               ← Alle Experimente
├── assembly_ranking.png                  ← Best→Worst
└── exp_name/
    └── assembly_name/
        ├── confusion_matrix_*.png        (14 Felder)
        ├── per_class_*.png               (14 Felder)
        ├── assembly_summary.png          (Farb-coded)
        ├── class_distribution_heatmap.png
        ├── step_overview.png
        └── metrics.json
```

### Metriken erklärt

| Metrik | Bedeutung | Best für |
|--------|-----------|----------|
| **Macro F1** | Durchschnitt F1 über alle Klassen | Unausgewogene Daten (PRIMARY) |
| Macro Precision | Durchschnitt Präzision | Gleichgewicht prüfen |
| Macro Recall | Durchschnitt Recall | Gleichgewicht prüfen |
| Micro Accuracy | Gesamtgenauigkeit | Reference (kann irreführend sein) |

### Class Imbalance

**Problem:** Manche FFA-Felder haben wenige Samples in manchen Klassen
- Klasse 1: 10 Samples ✓
- Klasse 2: 1 Sample ✗ (Minority)
- Klasse 3: 0 Samples ✗ (Missing)

**Lösung:** Macro-Average ignoriert Imbalance, zeigt echte Per-Class Performance

### Farb-Codes in Charts

- 🟢 **Grün (>0.7):** Exzellent
- 🟠 **Orange (0.5-0.7):** Akzeptabel
- 🔴 **Rot (<0.5):** Schlecht (Minority-Klasse Problem?)

---

## 🔗 Weiterführende Dokumentation

- **Evaluations-Details**: [WORKFLOW_DATA_IO_GUIDE.md](WORKFLOW_DATA_IO_GUIDE.md) - Evaluation System
- **Detaillierte Implementation**: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- **Architektur Entscheidungen**: [OPTIMIZATION_RECOMMENDATIONS.md](OPTIMIZATION_RECOMMENDATIONS.md)
- **Projekt Übersicht**: [README.md](README.md)
- **Aufgaben & Status**: [ToDos.md](ToDos.md)

---

## 📞 Fragen?

**Assembly Sequence**: Siehe [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) Phase 2-3  
**Rendering**: Siehe `stepparser/rendering/renderer.py`  
**Prompts**: Siehe `configs/prompts.yaml`  
**FFA Evaluation**: Siehe `run_ffa_evaluation.py` & `evaluation/ffa_metrics.py`

---

**Letztes Update**: 13. Februar 2026  
**Maintainer**: KAB-MS
