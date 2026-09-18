# Checkpoint System Update (13.02.2026)

## NEUE ANFORDERUNGEN - Vollständig Standalone Checkpoints

Basierend auf User-Feedback vom 13.02.2026

---

## Finale Checkpoint-Struktur (Option A - Vollständig Standalone)

```
processed/checkpoints/
└── {timestamp}/
    ├── checkpoint_metadata.json      # Global: Liste aller Assemblies
    ├── Connecting_Rod/
    │   ├── metadata.json              # Assembly-spezifisch: Settings
    │   ├── assembly_sequence.json     # Von Node 7
    │   ├── sequence_renderings/       # Von Node 8 (step-specific)
    │   ├── stepparser_renderings/     # KOPIERT von processed/stepparser
    │   │   ├── Connecting_Rod.STEP-iso1_transp_0_0.png
    │   │   ├── Connecting_Rod.STEP-iso1_transp_0_3.png
    │   │   └── ... (alle Views)
    │   ├── BOM_enriched.json          # Von Node 6
    │   └── enriched_parts/            # Von Node 5
    ├── IPA_Cranfield/
    │   └── (gleiche Struktur)
    └── Simple_Valve/
        └── (gleiche Struktur)
```

**Unterschied zu vorheriger Planung:**
- ❌ ENTFERNT: `stepparser_renderings_path` in metadata.json
- ✅ HINZUGEFÜGT: Komplette Kopie von Stepparser-Renderings in `stepparser_renderings/`
- ✅ RESULT: 100% Standalone - keine Abhängigkeiten mehr

---

## Implementierungs-Phases

### Phase 2: `copy_stepparser_renderings()` Function

```python
def copy_stepparser_renderings(assembly_name: str, checkpoint_assembly_dir: Path) -> List[str]:
    """
    Kopiere alle Stepparser-Renderings zu Checkpoint.
    
    Sucht in processed/stepparser/{assembly}/assembly_{assembly}/ nach Bildern
    Pattern: {assembly}.STEP-*.png, {assembly}.step-*.png, {assembly}-*.png
    
    Returns: List von kopierten Dateien (für Logging)
    """
```

### Phase 3: `create_checkpoint()` Function

**Wird aufgerufen von Node 8 (render_assembly_steps) NACH erfolgreichem Rendering**

```python
def create_checkpoint(
    exp_output_dir: Path,
    assembly_name: str,
    checkpoint_base_path: str = "processed/checkpoints",
    current_settings: Optional[Dict] = None
) -> Path:
    """
    Tasks:
    1. Determine checkpoint_timestamp
    2. Create {base}/{timestamp}/{assembly_name}/ Verzeichnis
    3. Kopiere:
       - assembly_sequence.json
       - sequence_renderings/
       - BOM_enriched.json
       - enriched_parts/
    4. Aufrufen von copy_stepparser_renderings()
    5. Schreibe metadata.json (Assembly-spezifisch)
    6. Update/Create checkpoint_metadata.json (Global)
    
    Returns: Path zum Checkpoint-Assembly-Ordner
    """
```

### Phase 4: `run_assess_ffa_only()` Function

**Neue Einstiegsfunktion neben `run_all_nodes`**

```python
def run_assess_ffa_only(
    checkpoint_path: str,
    ffa_settings_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Führe FFA Assessment für ALLE Assemblies in Checkpoint aus.
    
    Workflow pro Assembly:
    1. Load checkpoint/metadata.json
    2. Validiere erforderliche Dateien (sequence.json, renderings/, etc.)
    3. Lade State mit Checkpoint-Daten
    4. Merge FFA_settings (checkpoint defaults + overrides)
    5. Erstelle new experiment run: data/experiments/{timestamp}/{assembly}/
    6. Kopiere Checkpoint-Daten
    7. Führe Node 10 (assess_ffa) aus
    8. Speichere ffa_assessment/ in experiment run
    
    Returns: Summary dict mit processed/failed counts
    """
```

### Phase 5: CLI Integration in run_experiments.py

```
--ffa-only                          # Flag: Use run_assess_ffa_only statt run_all_nodes
--checkpoint-path PATH              # Pfad zu processed/checkpoints/{timestamp}/
--ffa-setting-overrides JSON        # Optional: {"FFA_mode": "enabled"}
```

**Validation vor Execution:**
- ✓ checkpoint_path existiert
- ✓ checkpoint_metadata.json vorhanden
- ✓ Mindestens 1 Assembly im Checkpoint
- ✓ Print Summary mit Assembly-Liste

---

## Manuelle Workflow für Checkpoint-Merging

User kann manuell Checkpoints zusammenführen (KEINE speziellen Tools nötig):

```bash
# Checkpoint aus Run 1 kopieren
cp -r processed/checkpoints/run1_20260213_153000/* processed/checkpoints/final_merged/

# Fehlende Assemblies aus Run 2 hinzufügen
cp -r processed/checkpoints/run2_20260215_110000/IPA_Cranfield/ processed/checkpoints/final_merged/
```

✅ Funktioniert, weil Struktur vollständig self-contained ist!

---

## ToDo-Integration

Diese Anforderungen wurden zu **ToDos.md** hinzugefügt unter:
**"Data Restructuring & Checkpoint System (Prio 1)"**

6 Phasen dokumentiert:
1. ✅ Struktur
2. ✅ Stepparser-Renderings kopieren
3. ✅ Checkpoint-Erstellung in run_all_nodes
4. ✅ run_assess_ffa_only Workflow
5. ✅ CLI Integration
6. ✅ Documentation

