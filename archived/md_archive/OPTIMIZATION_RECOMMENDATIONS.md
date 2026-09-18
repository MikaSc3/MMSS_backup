# Optimierungs- und Verbesserungsvorschläge für APA_from_CAD

**Datum**: 16. Januar 2026  
**Analysierte Version**: Current State

---

## 🎯 Executive Summary

Das Projekt ist gut strukturiert, aber es gibt mehrere Bereiche für Verbesserungen:
- **Code-Organisation**: Bessere Modularität durch Subfolders
- **Performance**: Caching, Batch-Processing (Parallelisierung niedrige Priorität)
- **Architektur**: Separation of Concerns, Dependency Injection
- **Fehlerbehandlung**: Robustere Error Handling (Retry-Logik später)
- **Testing & Monitoring**: Fehlende Test-Infrastruktur

## 🎯 ZIELZUSTAND & ROADMAP

### Overall Goal: **Fitness for Automation (FFA) Bewertung**

Automatisierte Bewertung der Automatisierungsfähigkeit von CAD-Baugruppen basierend auf STEP-Dateien.

### Workflow-Pipeline (End-to-End)

```
┌─────────────────────┐
│   STEP Files        │
│   + Optional TXT    │  ← User-Input aus data/input/Additional_info/
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   StepParser        │  ← Generiert Renderings + Metadaten
│   (READ-ONLY)       │     (data/processed/stepparser/)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  LLM Enrichment     │  ← Assembly + Monopart Context
│  (Workflow Node 1)  │     Ergänzt: Material, Part Names, Features
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Merge BOM Node     │  ← LLM entscheidet bei Mehrdeutigkeiten
│  (Workflow Node 2)  │     (z.B. "Aluminium 80%" vs. "Kunststoff 60%")
│                     │     → Output: merged_bom.json
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  FFA Assessment     │  ← LLM-basierte Bewertung
│  (Workflow Node 3)  │     Basierend auf Excel-Vorlage
│                     │     → Output: ffa_assessment.json
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Experiment Output  │  ← data/experiments/{exp_name}/
│  (Alle Outputs)     │
└─────────────────────┘
```

### Experiment-Management

**Ordnerstruktur**:
```
data/
├── input/
│   ├── ALL/                          # STEP-Quelldateien
│   ├── Additional_info/              # Optional: User-Beschreibungen (.txt)
│   │   ├── IPA_Cranfield.txt
│   │   └── Gearbox.txt
│   └── assembly_order/               # NEU: Montagereihenfolgen (später)
│       ├── IPA_Cranfield.json        # Assembly Order für FFA-Node
│       └── Gearbox.json
│
├── processed/
│   └── stepparser/                   # READ-ONLY: Stepparser-Output
│       ├── IPA_Cranfield/
│       │   ├── IPA_Cranfield.STEP/
│       │   │   ├── assembly_metadata.json
│       │   │   ├── *.png
│       │   ├── Part_1_unique/
│       │   └── Part_2_unique/
│       └── Gearbox/
│
└── experiments/                      # Experiment-spezifische Outputs
    ├── exp1_baseline/
    │   ├── IPA_Cranfield/
    │   │   ├── enriched_assembly.json
    │   │   ├── enriched_parts/
    │   │   │   ├── Part_1_enriched.json
    │   │   │   └── Part_2_enriched.json
    │   │   ├── merged_bom.json        # NEU: Finale BOM
    │   │   ├── ffa_assessment.json    # NEU: FFA Bewertung
    │   │   └── run_manifest.json
    │   └── Gearbox/
    │
    ├── exp2_high_temp_prompts/
    │   └── ...
    │
    └── exp3_different_examples/
        └── ...
```

**Ziel**: `data/processed/stepparser/` bleibt unverändert → Gleicher Startpunkt für alle Experimente

### Neue Features & Erweiterungen

#### 1. Additional Assembly Information (User Input)

**Feature**: Optionale Text-Beschreibungen vom Auftraggeber/User

**Implementation**:
- Ordner: `data/input/Additional_info/`
- Format: `.txt` Dateien, Name-Matching zu STEP-Dateien
  - `IPA_Cranfield.STEP` → `IPA_Cranfield.txt`
  - `Gearbox.STEP` → `Gearbox.txt`
- Falls keine `.txt` vorhanden oder leer → Info bleibt leer (kein Error)

**Prompt-Integration**:
```
[Bestehender Assembly-Prompt]

--- Hier weitere Informationen vom Auftraggeber: ---
{content_of_txt_file}
```

**Steuerung**: `experiment.yaml`
```yaml
use_additional_assembly_info: true  # false = Feature disabled
```

#### 2. Merge BOM Node (LLM-basierte Entscheidungsfindung)

**Funktion**: Auflösung von Mehrdeutigkeiten in enriched Part-Daten

**Beispiel-Szenario**:
```json
// Part_1_enriched.json
{
  "material_candidates": [
    {"material": "Aluminium", "certainty": 80},
    {"material": "Kunststoff", "certainty": 60}
  ]
}
```

**LLM-Prompt** (vereinfacht):
```
Du hast folgende Material-Vorschläge für Part_1:
- Aluminium (80% Certainty)
- Kunststoff (60% Certainty)

Kontext: [Assembly-Info, Geometric Features]

Entscheide dich für EINE Option und begründe.
```

**Output**: `merged_bom.json` (siehe BOM Class unten)

#### 3. FFA Assessment Node (LLM-basierte Bewertung)

**Funktion**: Bewertung der Automatisierungsfähigkeit basierend auf Excel-Vorlage

**Input**: 
- `merged_bom.json` (Finale Teileliste)
- Assembly Context
- **Assembly Order** (aus `data/input/assembly_order/{assembly_name}.json`)

**Bewertungskriterien** (aus Excel-Vorlage in `Template APA/`):
- **Hinweis**: User überführt Bewertungsschema manuell in Dataclass
- Mehrere Bewertungskriterien mit jeweils 2-4 Auswahlmöglichkeiten
- Beispiele:
  - Anzahl/Art der Verbindungselemente
  - Geometrische Komplexität
  - Materialien & Bearbeitbarkeit
  - Zugänglichkeit für Roboter/Werkzeuge
  - Montagepfad/Reihenfolge

**Output**: `ffa_assessment.json` (siehe APA_Bewertung Class unten)

**Prompt-Varianten**: Steuerbar über `experiment.yaml`
```yaml
prompt_id_ffa: "ffa_detailed_v1"  # oder "ffa_quick_v1", etc.
```

---

## 📦 NEUE PYDANTIC SCHEMAS

### BOM Class (agent/schemas/bom.py)

```python
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class BOMEntry(BaseModel):
    """Einzelner BOM-Eintrag für ein Part."""
    
    part_id: str = Field(..., description="Unique Part ID (z.B. 'Part_1')")
    part_name: str = Field(..., description="Finaler Part-Name (LLM-Entscheidung)")
    part_type: Optional[str] = Field(None, description="Part-Typ (z.B. 'Bracket', 'Shaft')")
    
    # Finale Entscheidungen (jeweils nur EIN Wert)
    material: str = Field(..., description="Finales Material (z.B. 'Aluminium')")
    material_certainty: int = Field(..., ge=0, le=100, description="Confidence in Material")
    
    # Geometrie (aus enriched data)
    volume_mm3: Optional[float] = None
    surface_area_mm2: Optional[float] = None
    bounding_box: Optional[Dict[str, float]] = None
    
    # Features (finale Liste)
    geometric_features: List[str] = Field(default_factory=list, 
                                          description="Liste von Features (z.B. ['M8 Thread', 'Chamfer 1x45°'])")
    
    # Metadaten
    llm_reasoning: Optional[str] = Field(None, description="Begründung für Material-Entscheidung")
    alternative_materials: Optional[List[Dict[str, any]]] = Field(None, 
                                                                   description="Nicht-gewählte Alternativen")

class BOM(BaseModel):
    """Bill of Materials - Finale Baugruppenliste."""
    
    assembly_name: str = Field(..., description="Name der Baugruppe")
    total_parts: int = Field(..., description="Anzahl Parts in BOM")
    
    entries: List[BOMEntry] = Field(default_factory=list, description="BOM-Einträge")
    
    # Metadaten
    created_by: str = Field(default="LLM Workflow", description="Erstellungsmethode")
    experiment_name: Optional[str] = None
    
    # Validierung
    @property
    def unique_materials(self) -> List[str]:
        """Gibt Liste einzigartiger Materialien zurück."""
        return list(set(entry.material for entry in self.entries))
    
    @property
    def average_material_certainty(self) -> float:
        """Durchschnittliche Material-Confidence."""
        if not self.entries:
            return 0.0
        return sum(e.material_certainty for e in self.entries) / len(self.entries)
    
    def to_simplified_dict(self) -> Dict:
        """Vereinfachte Darstellung für FFA-Node."""
        return {
            "assembly": self.assembly_name,
            "parts": [
                {
                    "id": e.part_id,
                    "name": e.part_name,
                    "material": e.material,
                    "features": e.geometric_features
                }
                for e in self.entries
            ]
        }
```

### APA_Bewertung Class (agent/schemas/ffa.py)

**Hinweis**: User überführt Bewertungsschema aus Excel manuell. Hier nur rudimentäre Struktur mit EINER Beispiel-Kategorie.

```python
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field
from enum import Enum

class FFAKategorie(str, Enum):
    """FFA-Bewertungskategorien (basierend auf Excel-Vorlage)."""
    
    # BEISPIEL: Nur eine Kategorie als Platzhalter
    # User wird weitere Kategorien aus Excel ergänzen
    VERBINDUNGSELEMENTE = "Verbindungselemente"
    # TODO: Weitere Kategorien ergänzen

class VerbindungselementeOption(str, Enum):
    """Beispiel: Auswahlmöglichkeiten für Verbindungselemente."""
    OPTION_1 = "Überwiegend Schraubverbindungen"
    OPTION_2 = "Mix aus Schraub- und Schweißverbindungen"
    OPTION_3 = "Überwiegend Schweißverbindungen"
    OPTION_4 = "Sonstige/Spezielle Verbindungen"

class FFAKriterium(BaseModel):
    """Einzelnes Bewertungskriterium."""
    
    kategorie: FFAKategorie
    beschreibung: str = Field(..., description="Was wird bewertet?")
    
    # Auswahlmöglichkeit (2-4 Optionen pro Kategorie)
    selected_option: str = Field(..., description="Gewählte Option aus 2-4 Möglichkeiten")
    
    # Score für diese Option
    score: int = Field(..., ge=0, le=10, description="Punkte für gewählte Option")
    max_score: int = Field(default=10, description="Maximale Punktzahl")
    
    # LLM-Begründung
    reasoning: str = Field(..., description="Warum diese Option?")
    evidence: Optional[List[str]] = Field(None, description="Belege aus BOM/Assembly Order")

class APA_Bewertung(BaseModel):
    """Fitness for Automation Assessment - Gesamtbewertung."""
    
    assembly_name: str
    bom_reference: str = Field(..., description="Pfad zur merged_bom.json")
    assembly_order_reference: Optional[str] = Field(None, description="Pfad zur assembly_order.json")
    
    # Kriterien (User wird weitere ergänzen)
    kriterien: List[FFAKriterium] = Field(default_factory=list)
    
    # Gesamtbewertung
    gesamt_score: int = Field(..., description="Summe aller Scores")
    gesamt_max_score: int = Field(..., description="Summe aller Max-Scores")
    
    @property
    def prozent(self) -> float:
        """FFA-Score in Prozent."""
        if self.gesamt_max_score == 0:
            return 0.0
        return (self.gesamt_score / self.gesamt_max_score) * 100
    
    @property
    def bewertung_text(self) -> str:
        """Textuelle Bewertung."""
        p = self.prozent
        if p >= 80:
            return "Sehr gut automatisierbar"
        elif p >= 60:
            return "Gut automatisierbar"
        elif p >= 40:
            return "Bedingt automatisierbar"
        elif p >= 20:
            return "Schwer automatisierbar"
        else:
            return "Nicht automatisierbar"
    
    # Zusätzliche Insights
    kritische_faktoren: List[str] = Field(default_factory=list, 
                                          description="Haupthindernisse für Automation")
    verbesserungsvorschlaege: List[str] = Field(default_factory=list,
                                                description="Wie könnte Automatisierbarkeit verbessert werden?")
    
    # Metadaten
    llm_model: Optional[str] = Field(None, description="Verwendetes LLM-Modell")
    prompt_id: Optional[str] = Field(None, description="Verwendeter Prompt")
    experiment_name: Optional[str] = None
```

**Beispiel-Output** (`ffa_assessment.json`):
```json
{
  "assembly_name": "IPA_Cranfield",
  "bom_reference": "data/experiments/exp1/IPA_Cranfield/merged_bom.json",
  "assembly_order_reference": "data/input/assembly_order/IPA_Cranfield.json",
  "kriterien": [
    {
      "kategorie": "Verbindungselemente",
      "beschreibung": "Art und Anzahl der Verbindungselemente",
      "selected_option": "Überwiegend Schraubverbindungen",
      "score": 8,
      "max_score": 10,
      "reasoning": "12 M8-Schrauben, standardisiert, gut zugänglich gemäß Assembly Order",
      "evidence": [
        "BOM: 12x M8 Thread detected", 
        "Assembly Order: Step 3-5 show easy screw access"
      ]
    }
  ],
  "gesamt_score": 8,
  "gesamt_max_score": 10,
  "prozent": 80.0,
  "bewertung_text": "Sehr gut automatisierbar",
  "kritische_faktoren": [],
  "verbesserungsvorschlaege": []
}
```

---

## 📁 1. CODE-STRUKTUR: Vorgeschlagene Folder-Reorganisation

### 1.1 Aktueller Stand `agent/`
```
agent/
├── __init__.py
├── prompt_store.py      # Prompt-Management
├── prompt.py            # ???
├── simple_agent.py      # Legacy (nicht mehr aktiv genutzt)
├── structured_output.py # Pydantic Models
├── tools.py            # ~1600 Zeilen! (zu groß)
├── utils.py
└── Workflow_enrich_data.py
```

### 1.2 Vorgeschlagene Neue Struktur

```
agent/
├── __init__.py
│
├── workflows/                    # NEU: Workflow-Orchestrierung
│   ├── __init__.py
│   ├── enrichment_workflow.py   # Haupt-Workflow (ehemals Workflow_enrich_data.py)
│   ├── nodes/                   # Workflow-Nodes separat
│   │   ├── __init__.py
│   │   ├── path_resolver.py     # _node_resolve_paths
│   │   ├── assembly_analyzer.py # _node_run_assembly
│   │   ├── part_analyzer.py     # _node_run_monoparts
│   │   ├── merge_bom.py         # NEU: BOM-Merge Node
│   │   └── ffa_assessment.py    # NEU: FFA Bewertungs-Node
│   └── state.py                 # State-Definitionen
│
├── core/                        # NEU: Kern-Business-Logik
│   ├── __init__.py
│   ├── image_processor.py       # ImageLoader Klasse
│   ├── json_processor.py        # JsonLoader Klasse
│   ├── text_processor.py        # NEU: Additional Info Loader
│   ├── assembly_order_loader.py # NEU: Assembly Order Loader (später)
│   └── llm_client.py           # LLM-Client-Wrapper
│
├── tools/                       # NEU: LangChain Tools separat
│   ├── __init__.py
│   ├── file_tools.py           # read_json_file, write_json_file
│   ├── image_tools.py          # analyse_assembly_img, analyse_monopart_img
│   ├── bom_tools.py            # NEU: merge_bom_entries (LLM-Call)
│   └── ffa_tools.py            # NEU: assess_ffa (LLM-Call)
│
├── schemas/                     # NEU: Alle Pydantic Models
│   ├── __init__.py
│   ├── assembly.py             # AssemblyAnalysis, AssemblyBatchAnalysis
│   ├── part.py                 # SinglePartAnalysis, SinglePartBatchAnalysis
│   ├── bom.py                  # NEU: BOM, BOMEntry
│   ├── ffa.py                  # NEU: APA_Bewertung, FFAKriterium
│   └── common.py               # CertaintyItem, GeometricFeature, PartOverview
│
├── prompts/                     # NEU: Prompt-Management
│   ├── __init__.py
│   ├── loader.py               # get_prompt_template, load_experiment_settings
│   ├── renderer.py             # render_prompt, render_examples_block
│   └── layout.py               # resolve_stepparser_layout_vars
│
├── utils/                       # NEU: Utilities gruppiert
│   ├── __init__.py
│   ├── formatting.py           # format_metadata_files_in_prompt, etc.
│   ├── hashing.py              # sha256_text
│   └── token_tracking.py       # token_usage_from_tool_result
│
└── legacy/                      # NEU: Veraltete Files
    ├── __init__.py
    └── simple_agent.py         # Für zukünftige Referenz
```

**Zusätzlicher Ordner**:
```
APA_Muster/                      # Entfällt - Excel liegt in Template APA/
Template APA/                    # BESTEHT BEREITS
├── ffa_bewertung_vorlage.xlsx  # Excel-Vorlage für FFA-Kriterien (vorhanden)
└── ...
```

### 1.3 Vorteile der neuen Struktur
✅ **Klarere Verantwortlichkeiten** (Single Responsibility Principle)  
✅ **Einfacheres Testing** (jede Komponente isoliert testbar)  
✅ **Bessere Wartbarkeit** (kleinere Files, ~200-300 Zeilen statt 1600)  
✅ **Einfachere Onboarding** (neue Entwickler finden sich schneller zurecht)  
✅ **Reduzierte Merge-Konflikte** (weniger Entwickler arbeiten am selben File)

---

## ⚡ 2. PERFORMANCE-OPTIMIERUNGEN

### 2.1 Parallele Verarbeitung erweitern

**Status**: ⏸️ **NIEDRIGE PRIORITÄT** (Parallelisierung crasht aktuell)

**Problem**: 
- Monopart-Parallelisierung (`parallel=True`) führt zu Crashes
- Workflow läuft aktuell sequentiell ausreichend performant

**Für später** (wenn Performance-Engpass):
- ThreadPoolExecutor-Fehler debuggen
- Alternativen prüfen:
  - `asyncio` statt ThreadPoolExecutor
  - Celery für distributed processing
  - Batch API (siehe 2.3)

```python
# SPÄTER: Debug-Version mit besserer Error Handling
def _node_run_monoparts_parallel(state: WorkflowState) -> WorkflowState:
    """Parallele Monopart-Verarbeitung mit robustem Error Handling."""
    results = []
    failed_parts = []
    
    with ThreadPoolExecutor(max_workers=state["max_workers"]) as executor:
        futures = {
            executor.submit(_run_one_part_safe, part_dir): part_dir
            for part_dir in state["part_dirs"]
        }
        
        for future in as_completed(futures):
            part_dir = futures[future]
            try:
                result = future.result(timeout=300)  # 5min timeout
                results.append(result)
            except Exception as e:
                logger.error(f"Part {part_dir} failed", error=str(e), exc_info=True)
                failed_parts.append({"part_dir": part_dir, "error": str(e)})
    
    return {**state, "part_results": results, "failed_parts": failed_parts}
```

### 2.2 Image-Caching implementieren

**Problem**: Gleiche Bilder werden mehrfach base64-encodiert

```python
# NEU: agent/core/image_processor.py
from functools import lru_cache
import hashlib

class CachedImageLoader(ImageLoader):
    def __init__(self, search_dir: str | Path, cache_size: int = 128):
        super().__init__(search_dir)
        self._cache = {}
        
    def encode_image(self, image_path: Path) -> str:
        # Cache-Key aus File-Path + Modification-Time
        cache_key = f"{image_path}:{image_path.stat().st_mtime}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        encoded = super().encode_image(image_path)
        self._cache[cache_key] = encoded
        return encoded
```

### 2.3 Batch-Processing für LLM-Calls

**Status**: ⏸️ **SPÄTER** (wenn Batch API stabil funktioniert)

**Aktuell**: Einzelne LLM-Calls nacheinander (funktioniert zuverlässig)  
**Vorteil**: OpenAI Batch API ist 50% günstiger, aber asynchron (24h completion window) 

```python
# NEU: agent/core/llm_client.py
from openai import AzureOpenAI

class BatchLLMClient:
    def __init__(self):
        self.client = AzureOpenAI(...)
        
    def submit_batch(self, requests: List[Dict]) -> str:
        """Submit batch job, returns batch_id"""
        batch = self.client.batches.create(
            input_file_id=self._create_batch_file(requests),
            endpoint="/v1/chat/completions",
            completion_window="24h"
        )
        return batch.id
        
    def retrieve_batch(self, batch_id: str) -> List[Dict]:
        """Poll until complete, return results"""
        # Implementation...
```

**Anwendungsfall**: Für Offline-Processing vieler Assemblies

### 2.4 Lazy Loading für Metadaten

**Problem**: Alle JSONs werden sofort geladen, auch wenn nicht benötigt # super

```python
# NEU: agent/core/json_processor.py
class LazyJsonLoader(JsonLoader):
    def find_and_load_lazy(self, keywords: List[str]) -> Dict[str, Callable]:
        """Rückgabe: Dict mit Callables statt Daten"""
        found = self.find_json_files(keywords)
        lazy_dict = {}
        
        for keyword, paths in found.items():
            lazy_dict[keyword] = lambda p=paths: [
                self.load_json_text(path) for path in p
            ]
        
        return lazy_dict
```

---

## 🏗️ 3. ARCHITEKTUR-VERBESSERUNGEN

### 3.1 Dependency Injection für LLM-Client

**Problem**: Globaler State `_IMG_DESCRIBER_LLM` macht Testing schwer

```python
# VORHER (tools.py)
_IMG_DESCRIBER_LLM: Optional[AzureChatOpenAI] = None  # Global!

def _get_img_describer_llm(...):
    global _IMG_DESCRIBER_LLM  # ❌ Schwer zu testen
    ...

# NACHHER (agent/core/llm_client.py)
from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    def invoke(self, messages: List, **kwargs) -> Dict:
        pass

class AzureLLMClient(LLMClient):
    def __init__(self, endpoint: str, api_key: str, ...):
        self.client = AzureChatOpenAI(...)
        
    def invoke(self, messages: List, **kwargs) -> Dict:
        return self.client.invoke(messages, **kwargs)

class MockLLMClient(LLMClient):  # Für Tests
    def invoke(self, messages: List, **kwargs) -> Dict:
        return {"content": "mock response"}

# Nutzung (agent/tools/image_tools.py)
def analyse_assembly_img(
    searchdir: str,
    llm_client: LLMClient = None,  # Injectable!
    **kwargs
) -> Dict[str, Any]:
    if llm_client is None:
        llm_client = AzureLLMClient(...)  # Default
    
    result = llm_client.invoke(...)
    return result
```

### 3.2 Configuration Management verbessern

**Anforderung**: Multiple Experimente mit separaten Outputs

**Lösung**: Experiment-basiertes Output-Routing

```python
# NEU: agent/config.py
from pydantic import BaseSettings, Field

class WorkflowConfig(BaseSettings):
    # Azure Settings
    azure_endpoint: str = Field(..., env="AZURE_ENDPOINT")
    api_key: str = Field(..., env="API_KEY_GPT_4")
    
    # Experiment Settings
    experiment_name: str = Field(default="default", description="Name des Experiments (für Output-Ordner)")
    
    # Image Processing
    img_to_analyse_assy: List[str] = ["explosion", "isometric"]
    img_to_analyse_monopart: List[str] = ["top", "isometric"]
    downscaling_factor: float = 1.0
    
    # LLM Settings
    max_completion_tokens: int = 5000
    temperature: float = 0.0
    
    # Workflow
    parallel: bool = False
    max_workers: int = 4
    
    # Feature Flags
    use_additional_assembly_info: bool = Field(default=False, description="Load .txt from data/input/Additional_info/")
    enable_merge_bom: bool = Field(default=True, description="Enable BOM merge node")
    enable_ffa_assessment: bool = Field(default=True, description="Enable FFA assessment node")
    
    # Prompt Selection
    prompt_id_assembly: str = "assembly_describer_v1"
    prompt_id_monopart: str = "monopart_describer_v1"
    prompt_id_merge_bom: str = "merge_bom_v1"
    prompt_id_ffa: str = "ffa_detailed_v1"
    
    # Output Paths (computed)
    @property
    def experiment_output_root(self) -> Path:
        """Returns: data/experiments/{experiment_name}/"""
        return Path("data/experiments") / self.experiment_name
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "WorkflowConfig":
        """Load from experiment YAML + env overrides.
        
        Example:
            config = WorkflowConfig.from_yaml(Path("configs/experiments/exp1_baseline.yaml"))
        """
        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f)
        
        # Merge with env vars (env takes precedence for secrets)
        return cls(**yaml_data)

# Nutzung
config = WorkflowConfig.from_yaml(Path("configs/experiments/exp1_baseline.yaml"))

# Output wird automatisch nach data/experiments/exp1_baseline/ geleitet
print(config.experiment_output_root)  # Path('data/experiments/exp1_baseline')
```

**Beispiel Experiment-Konfiguration**:

`configs/experiments/exp1_baseline.yaml`:
```yaml
experiment_name: "exp1_baseline"

# Feature Flags
use_additional_assembly_info: true
enable_merge_bom: true
enable_ffa_assessment: true

# Prompts
prompt_id_assembly: "assembly_describer_v1"
prompt_id_monopart: "monopart_describer_v1"
prompt_id_merge_bom: "merge_bom_v1"
prompt_id_ffa: "ffa_detailed_v1"

# LLM Settings
temperature: 0.0
max_completion_tokens: 5000
```

`configs/experiments/exp2_high_temp.yaml`:
```yaml
experiment_name: "exp2_high_temp"

# Unterschied: Höhere Temperatur für kreativere Antworten
temperature: 0.7

# Anderer FFA-Prompt
prompt_id_ffa: "ffa_quick_v1"
```
```

### 3.3 State Management mit TypedDict

**Problem**: State ist `Dict[str, Any]` → keine Type-Safety

```python
# NEU: agent/workflows/state.py
from typing import TypedDict, List, Optional

class WorkflowState(TypedDict, total=False):
    run_id: str
    datasource_root: str
    assembly_dir: str
    part_dirs: List[str]
    
    # Results
    assembly_result: Optional[Dict[str, Any]]
    part_results: List[Dict[str, Any]]
    
    # Config
    use_unique_parts: bool
    parallel: bool
    max_workers: int
    workflow_print: bool
    
    # Runtime
    warnings: List[str]
    runtime_seconds: float
    token_usage_total: Dict[str, int]

# Nutzung in Workflow
def _node_resolve_paths(state: WorkflowState) -> WorkflowState:
    root = Path(state["datasource_root"])
    # IDE autocomplete funktioniert jetzt! ✅
    ...
```

---

## 🛡️ 4. ERROR HANDLING & ROBUSTHEIT

### 4.1 Retry-Logik für LLM-Calls

**Status**: ⏸️ **NICHT BENÖTIGT** (User-Feedback: Crashes sind akzeptabel) 

```python
# NEU: agent/core/llm_client.py
from tenacity import retry, stop_after_attempt, wait_exponential

class ResilientLLMClient(AzureLLMClient):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def invoke(self, messages: List, **kwargs) -> Dict:
        try:
            return super().invoke(messages, **kwargs)
        except Exception as e:
            self._log_error(e)
            raise
```

### 4.2 Validation Layer

**Status**: ⏸️ **FÜR SPÄTER** (bisher keine Probleme mit ungültigen LLM-Outputs) 

```python
# NEU: agent/schemas/validators.py
from pydantic import validator  

class AssemblyAnalysis(BaseModel):
    parts: List[PartOverview] = []
    certainties: List[CertaintyItem] = []
    
    @validator("parts")
    def validate_parts(cls, v):
        if len(v) == 0:
            raise ValueError("Assembly must contain at least one part")
        return v
    
    @validator("certainties")
    def validate_certainties(cls, v):
        for item in v:
            if not 0 <= item.certainty <= 100:
                raise ValueError(f"Certainty must be 0-100, got {item.certainty}")
        return v
```

### 4.3 Graceful Degradation

```python
# agent/workflows/nodes/part_analyzer.py
def _node_run_monoparts(state: WorkflowState) -> WorkflowState:
    results = []
    warnings = []
    failed_parts = []
    
    for part_dir in state["part_dirs"]:
        try:
            res = _run_one_part(part_dir, ...)
            results.append(res)
        except Exception as e:
            warnings.append(f"Part {part_dir} failed: {e}")
            failed_parts.append(part_dir)
            # Weiter mit nächstem Part statt Abbruch! ✅
    
    # Summary
    if failed_parts:
        warnings.append(f"Failed {len(failed_parts)}/{len(state['part_dirs'])} parts")
    
    return {
        **state,
        "part_results": results,
        "failed_parts": failed_parts,  # NEU: Tracking
        "warnings": warnings
    }
```

---

## 📊 5. MONITORING & OBSERVABILITY # gut

### 5.1 Structured Logging

**Problem**: `print()` Statements überall

```python
# NEU: agent/utils/logging.py
import structlog
from pathlib import Path

def setup_logging(log_dir: Path = None):
    log_dir = log_dir or Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.PrintLoggerFactory(
            file=open(log_dir / "workflow.jsonl", "a")
        )
    )
    
    return structlog.get_logger()

# Nutzung
logger = setup_logging()

def _node_run_assembly(state: WorkflowState) -> WorkflowState:
    logger.info("assembly_analysis_started", 
                assembly_dir=state["assembly_dir"],
                run_id=state["run_id"])
    
    try:
        result = analyse_assembly_img.invoke(...)
        logger.info("assembly_analysis_completed",
                    token_usage=result.get("token_usage"),
                    runtime_ms=result.get("runtime_ms"))
    except Exception as e:
        logger.error("assembly_analysis_failed", error=str(e))
        raise
    
    return {...}
```

### 5.2 Metrics Tracking

```python
# NEU: agent/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Metrics definieren
llm_calls_total = Counter("llm_calls_total", "Total LLM API calls", ["task"])
llm_tokens_total = Counter("llm_tokens_total", "Total tokens used", ["type"])
llm_latency = Histogram("llm_latency_seconds", "LLM call latency")
workflow_runtime = Histogram("workflow_runtime_seconds", "Workflow runtime")

# In Code nutzen
@llm_latency.time()
def analyse_assembly_img(...):
    llm_calls_total.labels(task="assembly").inc()
    result = llm.invoke(...)
    llm_tokens_total.labels(type="input").inc(result["input_tokens"])
    llm_tokens_total.labels(type="output").inc(result["output_tokens"])
    return result
```

---

## 🧪 6. TESTING INFRASTRUCTURE # muss für mich nicht sein. nur wenn du denkst, dass das witklich sinn macht

### 6.1 Ordnerstruktur für Tests

```
tests/
├── __init__.py
├── conftest.py              # Pytest Fixtures
├── unit/
│   ├── test_image_processor.py
│   ├── test_json_processor.py
│   ├── test_llm_client.py
│   └── test_prompts.py
├── integration/
│   ├── test_workflow_nodes.py
│   └── test_end_to_end.py
├── fixtures/
│   ├── sample_assembly/
│   │   ├── assembly.png
│   │   └── metadata.json
│   └── sample_part/
└── mocks/
    └── llm_responses.json
```

### 6.2 Beispiel Unit Test

```python
# tests/unit/test_image_processor.py
import pytest
from pathlib import Path
from agent.core.image_processor import CachedImageLoader

@pytest.fixture
def sample_image_dir(tmp_path):
    """Erstelle temporäres Verzeichnis mit Test-Bildern"""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    
    # Erstelle Dummy-PNG
    (img_dir / "test-isometric.png").write_bytes(b"fake_png_data")
    (img_dir / "test-top.png").write_bytes(b"fake_png_data")
    
    return img_dir

def test_find_images_by_keyword(sample_image_dir):
    loader = CachedImageLoader(sample_image_dir)
    matches = loader.find_images(keywords=["isometric"])
    
    assert len(matches["isometric"]) == 1
    assert matches["isometric"][0].name == "test-isometric.png"

def test_cache_hit(sample_image_dir):
    loader = CachedImageLoader(sample_image_dir, cache_size=10)
    img_path = sample_image_dir / "test-isometric.png"
    
    # Erste Encodierung
    encoded1 = loader.encode_image(img_path)
    
    # Zweite Encodierung sollte Cache nutzen
    encoded2 = loader.encode_image(img_path)
    
    assert encoded1 == encoded2
    assert len(loader._cache) == 1  # Cache wurde genutzt
```

### 6.3 Integration Test für Workflow

```python
# tests/integration/test_workflow_nodes.py
from agent.workflows.enrichment_workflow import build_workflow

def test_full_workflow(sample_datasource_root):
    """Test kompletter Workflow mit Mock-LLM"""
    app = build_workflow(llm_client=MockLLMClient())
    
    state = {
        "datasource_root": str(sample_datasource_root),
        "use_unique_parts": True,
        "parallel": False,
        "max_workers": 2
    }
    
    result = app.invoke(state)
    
    assert "assembly_result" in result
    assert len(result["part_results"]) > 0
    assert result["warnings"] == []
```

---

## 📈 7. PERFORMANCE BENCHMARKS

### 7.1 Baseline Measurements # gute idee. hier kommen später weitere metriken hinzu

```python
# NEU: benchmarks/benchmark_workflow.py
import time
from agent.workflows.enrichment_workflow import run_enrichment

def benchmark_workflow(datasource_root: str, runs: int = 3):
    runtimes = []
    token_usages = []
    
    for i in range(runs):
        start = time.perf_counter()
        result = run_enrichment(datasource_root, parallel=False)
        runtime = time.perf_counter() - start
        
        runtimes.append(runtime)
        token_usages.append(result["token_usage_total"]["total_tokens"])
    
    print(f"Avg Runtime: {sum(runtimes)/len(runtimes):.2f}s")
    print(f"Avg Tokens: {sum(token_usages)/len(token_usages):.0f}")
    print(f"Std Dev Runtime: {np.std(runtimes):.2f}s")

if __name__ == "__main__":
    benchmark_workflow("data/processed/stepparser/IPA_Cranfield")
```

### 7.2 Profiling

```python
# benchmarks/profile_workflow.py
import cProfile
import pstats
from agent.workflows.enrichment_workflow import run_enrichment

def profile_workflow():
    profiler = cProfile.Profile()
    profiler.enable()
    
    run_enrichment("data/processed/stepparser/IPA_Cranfield")
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)  # Top 20 Funktionen

if __name__ == "__main__":
    profile_workflow()
```

---

## 🔧 8. DEVELOPER EXPERIENCE IMPROVEMENTS

### 8.1 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.12
  
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--profile", "black"]
  
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ["--max-line-length=120", "--ignore=E203,W503"]
```

### 8.2 Makefile für gängige Tasks

```makefile
# Makefile
.PHONY: install test lint format clean benchmark

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pre-commit install

test:
	pytest tests/ -v --cov=agent --cov-report=html

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

lint:
	flake8 agent/ stepparser/
	mypy agent/ stepparser/

format:
	black agent/ stepparser/ tests/
	isort agent/ stepparser/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage

benchmark:
	python benchmarks/benchmark_workflow.py

run-example:
	python -m agent.workflows.enrichment_workflow
```

### 8.3 Bessere README

```markdown
# APA_from_CAD

Automated Assembly Process Analysis from CAD files using LLMs.

## Quick Start

```bash
# Setup
make install

# Run workflow
python -m agent.workflows.enrichment_workflow

# Run tests
make test

# Benchmark
make benchmark
```

## Architecture

```
┌─────────────────┐
│  STEP Files     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  StepProcessor  │  ← Extracts B-Rep, renders images
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM Workflow   │
│  ├─ Assembly    │  ← GPT-4o Vision analysis
│  └─ Parts       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Enriched JSON  │  ← Structured metadata
└─────────────────┘
```

## Configuration

See `configs/default_settings.yaml` for options.
Override with `experiment.yaml`.

## Development

- `make lint` - Run linters
- `make format` - Format code
- `make test` - Run all tests
```

---

## 🚀 9. ADVANCED FEATURES

### 9.1 Streaming für lange LLM-Responses

```python
# agent/core/llm_client.py
class StreamingLLMClient(AzureLLMClient):
    def invoke_stream(self, messages: List, **kwargs):
        """Generator für Streaming-Responses"""
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content
            
# Nutzung für Real-time Feedback
def analyse_with_progress(searchdir: str):
    client = StreamingLLMClient()
    
    print("Analyzing assembly...")
    full_response = ""
    
    for chunk in client.invoke_stream(...):
        full_response += chunk
        print(chunk, end="", flush=True)  # Live-Output
    
    return parse_response(full_response)
```

### 9.2 Multi-Model Support # multi model support wäre toll. können wir das in den exeriments.yaml definieren? 

```python
# agent/core/llm_client.py
class MultiModelClient:
    def __init__(self):
        self.gpt4o = AzureLLMClient(deployment="gpt-4o")
        self.gpt4o_mini = AzureLLMClient(deployment="gpt-4o-mini")
        
    def invoke_smart(self, messages: List, task: str, **kwargs):
        """Wähle Modell basierend auf Task"""
        if task == "assembly":
            return self.gpt4o.invoke(messages, **kwargs)  # Komplex
        elif task == "monopart":
            return self.gpt4o_mini.invoke(messages, **kwargs)  # Einfach, günstiger
```

### 9.3 Result Caching

```python
# agent/core/result_cache.py
import json
import hashlib
from pathlib import Path

class ResultCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        
    def _cache_key(self, searchdir: str, settings: Dict) -> str:
        """Hash aus searchdir + relevanten Settings"""
        key_data = {
            "searchdir": str(searchdir),
            "prompt_id": settings.get("prompt_id"),
            "downscaling": settings.get("downscaling_factor"),
            # ... weitere relevante Settings
        }
        return hashlib.md5(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()
        
    def get(self, searchdir: str, settings: Dict) -> Optional[Dict]:
        cache_file = self.cache_dir / f"{self._cache_key(searchdir, settings)}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        return None
        
    def set(self, searchdir: str, settings: Dict, result: Dict):
        cache_file = self.cache_dir / f"{self._cache_key(searchdir, settings)}.json"
        cache_file.write_text(json.dumps(result, indent=2))
```

---

## 📋 10. PRIORITÄTEN & ROADMAP

**User-Feedback**: Fokus auf Experiment-System + Additional Infos. Code-Reorganisation hat **niedrige Priorität**.

### Phase 1: Core Features (FOKUS - 1-2 Wochen)
- [ ] **P0**: Experiment-Output-Routing (Separate Ordner pro Experiment)
- [ ] **P0**: Additional Info Loader (TXT-Dateien aus `data/input/Additional_info/`)
- [ ] **P0**: Rudimentäre BOM/FFA Schemas (nur eine Beispiel-Kategorie)
- [ ] **P0**: Merge BOM Node implementieren
- [ ] **P0**: FFA Assessment Node implementieren (nutzt assembly_order Inputs)
- [ ] **P1**: Prompts für Merge BOM & FFA in `configs/prompts.yaml`

### Phase 2: Quick Wins (2-3 Wochen)
- [ ] **P1**: Image Caching
- [ ] **P1**: Configuration Management (Pydantic BaseSettings)
- [ ] **P1**: Structured Logging
- [ ] **P2**: TypedDict für State
- [ ] **P2**: Basic Unit Tests

### Phase 3: Code-Reorganisation (NIEDRIGE PRIORITÄT - 3-4 Wochen)
- [ ] **P2**: Agent-Folder Restructuring (Subfolders)
- [ ] **P2**: Dependency Injection für LLM-Client
- [ ] **P2**: Integration Tests
- [ ] **P2**: Pre-commit Hooks

### Phase 4: Performance (SPÄTER - ongoing)
- [ ] **P3**: Parallelisierung debuggen (crasht aktuell, akzeptabel)
- [ ] **P3**: Result Caching
- [ ] **P4**: Retry-Logik (nicht benötigt laut User)
- [ ] **P4**: Validation Layer (später)
- [ ] **P4**: Batch-Processing Support
- [ ] **P4**: Streaming für UI-Feedback

### Phase 5: Skalierung (ZUKÜNFTIG)
- [ ] Metrics & Monitoring (Prometheus)
- [ ] Distributed Processing (Celery?)
- [ ] Web UI (FastAPI + React)
- [ ] Fine-tuned Models

---

## 🔍 11. SPEZIFISCHE CODE-SMELLS

### 11.1 `tools.py` ist zu groß (1595 Zeilen)

**Problem**: Verletzt Single Responsibility Principle  
**Lösung**: Aufteilung wie in Sektion 1.2 beschrieben

### 11.2 Globaler State in `_IMG_DESCRIBER_LLM`

**Problem**: Macht Testing und Parallelisierung schwer  
**Lösung**: Dependency Injection (siehe Sektion 3.1)

### 11.3 Try-Except ohne Logging

```python
# VORHER
try:
    if exp_path.exists() and exp_path.is_file():
        loaded = yaml.safe_load(...)
except Exception:
    exp_overrides = {}  # ❌ Fehler wird verschluckt

# NACHHER
try:
    if exp_path.exists() and exp_path.is_file():
        loaded = yaml.safe_load(...)
except Exception as e:
    logger.warning("failed_to_load_experiment", 
                   path=exp_path, error=str(e))
    exp_overrides = {}
```

### 11.4 String-basierte Pfade

```python
# VORHER
searchdir: str  # ❌ Keine Validierung
assembly_dir = str(layout.get("assembly_dir"))

# NACHHER
from pathlib import Path

searchdir: Path  # ✅ Type-safe
assembly_dir = Path(layout.get("assembly_dir"))
```

### 11.5 Magic Numbers

```python
# VORHER
img_describer_tokens_per_img: 2500  # ❌ Warum 2500?
max_workers = max(1, min(max_workers, len(part_dirs)))

# NACHHER
class LLMConfig:
    DEFAULT_TOKENS_PER_IMAGE = 2500  # Empirisch ermittelt
    MIN_WORKERS = 1
    
    @staticmethod
    def compute_workers(requested: int, max_possible: int) -> int:
        return max(LLMConfig.MIN_WORKERS, min(requested, max_possible))
```

---

## 📚 12. DOKUMENTATIONS-VERBESSERUNGEN

### 12.1 Docstrings hinzufügen

```python
# agent/workflows/enrichment_workflow.py
def run_enrichment(
    datasource_root: str,
    *,
    use_unique_parts: bool = True,
    parallel: bool = False,
    max_workers: int = 4,
    assembly_limit: int = 8,
    part_limit: int = 8,
) -> Dict[str, Any]:
    """
    Run LLM-based enrichment workflow on CAD assembly data.
    
    Analyzes assembly and part images using GPT-4o Vision to extract:
    - Part names and types
    - Geometric features (holes, threads, chamfers)
    - Material guesses
    - Assembly context
    
    Args:
        datasource_root: Path to processed STEP data (contains assembly + Part_* folders)
        use_unique_parts: If True, only process unique parts (skip duplicates)
        parallel: If True, process parts in parallel
        max_workers: Max thread pool size for parallel processing
        assembly_limit: Max images to analyze for assembly
        part_limit: Max images to analyze per part
        
    Returns:
        Dict containing:
            - assembly_result: Assembly analysis results
            - part_results: List of part analysis results
            - runtime_seconds: Total workflow runtime
            - token_usage_total: Aggregated LLM token usage
            - warnings: List of warnings encountered
            - run_manifest_path: Path to saved run manifest JSON
            
    Raises:
        FileNotFoundError: If datasource_root doesn't exist
        ValueError: If invalid configuration
        
    Example:
        >>> result = run_enrichment(
        ...     "data/processed/stepparser/IPA_Cranfield",
        ...     parallel=True,
        ...     max_workers=8
        ... )
        >>> print(f"Analyzed {len(result['part_results'])} parts")
        >>> print(f"Used {result['token_usage_total']['total_tokens']} tokens")
    """
    ...
```

### 12.2 Architecture Decision Records (ADRs)

```markdown
# docs/adr/0001-use-langgraph-for-workflow.md

# 1. Use LangGraph for Workflow Orchestration

Date: 2026-01-15

## Status
Accepted

## Context
Need to orchestrate multi-step LLM workflow:
1. Analyze assembly images
2. Analyze part images
3. Update metadata

Options considered:
- Custom state machine
- Apache Airflow
- Prefect
- **LangGraph**

## Decision
Use LangGraph for workflow orchestration.

## Consequences

### Positive
- Built-in checkpointing (can resume failed runs)
- Native LangChain integration
- Visual debugging with LangSmith
- Easy conditional branching

### Negative
- Relatively new library (stability risk)
- Smaller community vs Airflow
- Tied to LangChain ecosystem

## Alternatives Considered
- **Airflow**: Overkill for our use case, requires infrastructure
- **Prefect**: Good alternative, but less LLM-focused
```

---

## 🎨 13. OPTIONAL: UI IMPROVEMENTS

### 13.1 Web UI mit Streamlit (Quick Prototype)

```python
# ui/streamlit_app.py
import streamlit as st
from agent.workflows.enrichment_workflow import run_enrichment
from pathlib import Path

st.title("APA from CAD - LLM Enrichment")

# Sidebar Config
st.sidebar.header("Configuration")
datasource_root = st.sidebar.text_input(
    "Datasource Root",
    value="data/processed/stepparser/IPA_Cranfield"
)

parallel = st.sidebar.checkbox("Parallel Processing", value=False)
max_workers = st.sidebar.slider("Max Workers", 1, 16, 4)

# Main Panel
if st.button("Run Enrichment"):
    with st.spinner("Running workflow..."):
        result = run_enrichment(
            datasource_root,
            parallel=parallel,
            max_workers=max_workers
        )
    
    st.success(f"✅ Completed in {result['runtime_seconds']:.2f}s")
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tokens", result['token_usage_total']['total_tokens'])
    col2.metric("Parts Analyzed", len(result['part_results']))
    col3.metric("Warnings", len(result.get('warnings', [])))
    
    # Results Viewer
    st.subheader("Assembly Analysis")
    st.json(result['assembly_result']['analysis'])
    
    st.subheader("Part Results")
    for part_res in result['part_results']:
        with st.expander(f"Part: {Path(part_res['searchdir']).name}"):
            st.json(part_res['analysis'])
```

### 13.2 CLI mit Rich (bessere Terminal-UX)

```python
# cli.py
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from agent.workflows.enrichment_workflow import run_enrichment

app = typer.Typer()
console = Console()

@app.command()
def enrich(
    datasource_root: str,
    parallel: bool = False,
    max_workers: int = 4,
):
    """Run LLM enrichment workflow"""
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running workflow...", total=None)
        
        result = run_enrichment(
            datasource_root,
            parallel=parallel,
            max_workers=max_workers
        )
        
        progress.update(task, completed=True)
    
    # Pretty results table
    table = Table(title="Enrichment Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Runtime", f"{result['runtime_seconds']:.2f}s")
    table.add_row("Tokens", str(result['token_usage_total']['total_tokens']))
    table.add_row("Parts", str(len(result['part_results'])))
    
    console.print(table)

if __name__ == "__main__":
    app()
```

---

## 🔒 14. SECURITY & COMPLIANCE

### 14.1 Secrets Management

```python
# agent/config.py
from pydantic import SecretStr

class WorkflowConfig(BaseSettings):
    azure_endpoint: str
    api_key: SecretStr  # ✅ Wird nicht in Logs geprinted
    
    def get_api_key(self) -> str:
        return self.api_key.get_secret_value()
```

### 14.2 Input Sanitization

```python
# agent/utils/validation.py
from pathlib import Path

def validate_datasource_root(path: str) -> Path:
    """Validiere & sanitize Datasource-Root-Pfad"""
    p = Path(path).resolve()
    
    # Workspace-Boundary check
    workspace = Path(__file__).resolve().parents[2]
    try:
        p.relative_to(workspace)
    except ValueError:
        raise ValueError(f"Path außerhalb Workspace: {p}")
    
    # Directory traversal prevention
    if ".." in str(p):
        raise ValueError(f"Path Traversal detektiert: {p}")
    
    if not p.exists():
        raise FileNotFoundError(f"Path existiert nicht: {p}")
    
    return p
```

---

## 📝 ZUSAMMENFASSUNG

### Top 10 Quick Wins (nach ROI)

1. **Image Caching** → 30-50% Performance-Gewinn (1 Tag) ⭐⭐⭐⭐⭐
2. **Structured Logging** → Besseres Debugging (1 Tag) ⭐⭐⭐⭐
3. **Configuration Management** → Experiment-Support (1 Tag) ⭐⭐⭐⭐⭐
4. **Additional Info Loader** → User-Input Feature (4 Stunden) ⭐⭐⭐⭐
5. **BOM & FFA Schemas** → Neue Datenstrukturen (1 Tag) ⭐⭐⭐⭐⭐
6. **TypedDict für State** → Weniger Bugs (4 Stunden) ⭐⭐⭐⭐
7. **Basic Unit Tests** → Confidence bei Änderungen (2 Tage) ⭐⭐⭐
8. **Docstrings** → Besseres Onboarding (1 Tag) ⭐⭐⭐
9. **Pre-commit Hooks** → Code-Quality (2 Stunden) ⭐⭐⭐
10. **Makefile** → Developer Experience (2 Stunden) ⭐⭐⭐

### Neue Features (Priorität HOCH)

**User-Anforderungen**:
1. **Fokus**: Experiment-System + Additional Infos
2. Code-Reorganisation: **Niedrige Priorität**
3. Schemas: **Rudimentär mit nur einer Kategorie** (User überführt Excel später manuell)

**Implementationsreihenfolge**:
1. **Experiment-Output-Routing** → Separate Ordner pro Experiment (1 Tag)
2. **Additional Assembly Info** → User-Input Integration via TXT (1 Tag)
3. **Rudimentäre Schemas** → BOM + FFA mit einer Beispiel-Kategorie (1 Tag)
4. **Merge BOM Node** → LLM-basierte Entscheidungsfindung (2-3 Tage)
5. **FFA Assessment Node** → Automatisierungsbewertung (2-3 Tage)

### Geschätzte Gesamtaufwände (Aktualisiert)

- **Phase 1 (Core Features - FOKUS)**: ~8-12 Tage
  - Experiment-Output-Routing
  - Additional Info Loader
  - Rudimentäre BOM/FFA Schemas (eine Kategorie)
  - Merge BOM Node
  - FFA Assessment Node
  - Assembly Order Loader (später)

- **Phase 2 (Quick Wins)**: ~10-15 Tage
  - Image Caching
  - Configuration Management
  - Structured Logging
  - Prompts für neue Nodes

- **Phase 3 (Code-Reorganisation - NIEDRIGE PRIORITÄT)**: ~10-15 Tage
  - Agent-Folder Restructuring
  - Dependency Injection
  - Basic Unit Tests

- **Phase 4 (Performance - SPÄTER)**: ~15-20 Tage
  - Parallelisierung Debug (akzeptabel wie es ist)
  - Result Caching
  - Batch API (nicht benötigt)

### ROI-Bewertung (Aktualisiert nach User-Feedback)

**Hinweis**: Fokus auf Experiment-System + Additional Infos. Code-Reorg hat niedrigere Priorität.

| Verbesserung | Aufwand | Impact | Priorität | ROI |
|--------------|---------|--------|-----------|-----|
| **Experiment-System** | Mittel | **Sehr Hoch** | **P0** | ⭐⭐⭐⭐⭐ |
| **Additional Info** | Niedrig | **Hoch** | **P0** | ⭐⭐⭐⭐⭐ |
| **Merge BOM Node** | Hoch | **Sehr Hoch** | **P0** | ⭐⭐⭐⭐⭐ |
| **FFA Assessment** | Hoch | **Sehr Hoch** | **P0** | ⭐⭐⭐⭐⭐ |
| **Assembly Order Input** | Niedrig | Mittel | **P0** | ⭐⭐⭐⭐ |
| Image Caching | Niedrig | Mittel | P1 | ⭐⭐⭐⭐⭐ |
| Structured Logging | Niedrig | Mittel | P1 | ⭐⭐⭐⭐ |
| Config Management | Mittel | Mittel | P1 | ⭐⭐⭐ |
| Code-Reorg | Hoch | Mittel | **P2** | ⭐⭐ |
| Unit Tests | Mittel | Hoch | P2 | ⭐⭐⭐ |
| Parallelisierung | Hoch | Niedrig | **P3** | ⭐ |
| Retry-Logik | Niedrig | Niedrig | **P4** | - |
| Validation Layer | Mittel | Niedrig | **P4** | ⭐ |

### Nächste Schritte

#### Sofort (Diese Woche) - **FOKUS**
1. ✅ `data/experiments/` Ordner erstellen
2. ✅ `data/input/Additional_info/` Ordner erstellen
3. ✅ `data/input/assembly_order/` Ordner erstellen (für FFA Node Input)
4. 🔨 **`agent/schemas/bom.py`** implementieren (rudimentär)
5. 🔨 **`agent/schemas/ffa.py`** implementieren (rudimentär, **eine Kategorie**)
6. 🔨 **`agent/core/text_processor.py`** (Additional Info Loader)

#### Kurzfristig (Nächste 2 Wochen) - **FOKUS**
7. 🔨 **Experiment-Output-Routing** in Workflow integrieren
8. 🔨 **`agent/workflows/nodes/merge_bom.py`** implementieren
9. 🔨 **`agent/workflows/nodes/ffa_assessment.py`** implementieren
10. 🔨 Prompts für Merge BOM & FFA in `configs/prompts.yaml`
11. 🔨 `agent/core/assembly_order_loader.py` (später, wenn Daten vorhanden)

#### Mittelfristig (Nächste 4 Wochen) - Quick Wins
12. Image Caching implementieren
13. Structured Logging einführen
14. Configuration Management mit BaseSettings
15. Basic Unit Tests für neue Nodes

#### Langfristig (Später) - Code-Reorganisation
16. Agent-Folder Restructuring (niedrige Priorität laut User)
17. Dependency Injection für LLM-Client
18. Integration Tests

---

**Ende der Analyse**  
*Erstellt: 16. Januar 2025*  
*Aktualisiert nach User-Feedback: 16. Januar 2025*  
*Finalisiert: 16. Januar 2025 (Excel in Template APA/, Fokus: Experiment-System + Additional Infos)*
