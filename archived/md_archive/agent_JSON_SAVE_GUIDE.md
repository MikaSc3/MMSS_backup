# JSON Save Guide - Dynamic Schema Management

## Problem
Wenn ihr Pydantic Models ändert, müssen auch alle JSON-Speicherorte manuell angepasst werden. Das ist fehleranfällig und nicht dynamisch.

## Lösung: `save_structured_json()`

Eine zentrale Utility-Funktion in `agent/tools.py`, die automatisch:
1. **Pydantic Models erkennt** und `.model_dump()` nutzt
2. **Schema-Metadaten** hinzufügt (Name, Felder, Timestamp)
3. **Konsistente JSON-Speicherung** garantiert
4. **Atomic Writes** unterstützt (via Temp-File)

---

## Usage Examples

### 1. Pydantic Model direkt speichern
```python
from agent.structured_output import AssemblySequence
from agent.tools import save_structured_json

# LLM gibt AssemblySequence zurück
sequence = AssemblySequence(...)

# Speichern (automatisch mit Schema-Info)
save_structured_json("output.json", sequence)
```

**Resultat JSON:**
```json
{
  "_schema_info": {
    "schema_name": "AssemblySequence",
    "schema_module": "agent.structured_output",
    "schema_fields": ["assembly_name", "steps", "sequence_notation", ...],
    "created_at": "2026-02-01T14:52:21.123Z",
    "format_version": "1.0"
  },
  "assembly_name": "Worm Gear Demonstrator",
  "steps": [...],
  ...
}
```

### 2. Dict mit Schema-Reference speichern
```python
# Ihr habt bereits ein dict, wollt aber Schema-Info
sequence_dict = sequence.model_dump(exclude_none=True)
sequence_dict["custom_field"] = "extra_data"

save_structured_json("output.json", sequence_dict, schema=AssemblySequence)
```

### 3. Ohne Metadaten (Legacy-Kompatibilität)
```python
# Wenn ihr keine Schema-Info wollt
save_structured_json("output.json", data, add_metadata=False)
```

### 4. Non-Atomic Write (Debugging)
```python
# Für Debugging (ohne temp file)
save_structured_json("output.json", data, atomic=False)
```

---

## Vorteile

### ✅ Schema-Versionierung
Jedes JSON weiß, welches Schema es verwendet:
```json
{
  "_schema_info": {
    "schema_name": "FFA_Assessment_Complete",
    "schema_fields": ["step_number", "base_part_id", "joining_part_id", ...],
    "created_at": "2026-02-01T14:52:21Z"
  },
  ...
}
```

### ✅ Automatische Anpassung
Wenn ihr ein Pydantic Field hinzufügt/ändert:
- `.model_dump()` gibt automatisch die neuen Felder aus
- Schema-Fields werden automatisch aktualisiert
- Keine Code-Änderungen nötig!

### ✅ Debugging
Wenn ein JSON nicht geladen werden kann:
```python
# Ihr seht sofort welches Schema verwendet wurde
with open("output.json") as f:
    data = json.load(f)
    print(data["_schema_info"]["schema_name"])  # "AssemblySequence"
    print(data["_schema_info"]["schema_fields"])  # ["assembly_name", ...]
```

### ✅ Migration-Detection
```python
# Ihr könnt prüfen ob JSON alt ist
created = datetime.fromisoformat(data["_schema_info"]["created_at"])
if created < datetime(2026, 2, 1):
    print("Old JSON format - needs migration")
```

---

## Updated Files

Die folgenden Files nutzen jetzt `save_structured_json()`:

1. **Assembly_sequence_generation.py** (Line ~485)
   ```python
   save_structured_json(output_path, sequence_dict, schema=AssemblySequence)
   ```

2. **FFA_assessment.py** (Line ~822)
   ```python
   save_structured_json(output_file, result, add_metadata=True)
   ```

3. **Assembly_sequence_validation.py** (Line ~1421, ~1653)
   ```python
   save_structured_json(merged_path, merged_validation, add_metadata=True)
   ```

4. **tools.py - _save_assembly_metadata_enriched()** (Line ~1280)
   ```python
   save_structured_json(target, metadata, schema=AssemblyAnalysis, add_metadata=True)
   ```

5. **tools.py - _save_monopart_metadata_enriched()** (Line ~1316)
   ```python
   save_structured_json(target, metadata, schema=SinglePartAnalysis, add_metadata=True)
   ```

---

## Migration Guide für weitere Files

### Vorher (Manual):
```python
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
```

### Nachher (Dynamic):
```python
from agent.tools import save_structured_json
save_structured_json(output_file, data, schema=YourPydanticModel)
```

---

## TODO: Weitere Files zu migrieren

Diese Files nutzen noch manuelles `json.dump()`:

1. **workflow.py** (Line 318, 711)
   - Merge BOM
   - Remarks payload

2. **Workflow_enrich_data.py** (Line 318, 685)
   - Gleiche Stellen wie workflow.py

3. **merge_enriched.py** (Line 200)
   - Merged part metadata

4. **Assembly_sequence_validation.py** (Line 550)
   - Individual step validation JSON

---

## Best Practices

### ✅ DO:
- Nutzt `save_structured_json()` für alle LLM-Outputs
- Nutzt `schema=` Parameter wenn ihr Dicts speichert
- Fügt `_schema_info` zu allen JSONs hinzu (außer Legacy-Kompatibilität)

### ❌ DON'T:
- Manuell `json.dump()` für structured outputs
- Schema-Info entfernen (außer bei Bedarf)
- Metadaten ändern/überschreiben

---

## Future: Schema Validation

```python
# TODO: Utility zum Validieren von alten JSONs gegen neue Schemas
def validate_json_schema(json_path: Path, expected_schema: BaseModel):
    with open(json_path) as f:
        data = json.load(f)
    
    # Check schema info
    if "_schema_info" not in data:
        raise ValueError("No schema info found")
    
    schema_name = data["_schema_info"]["schema_name"]
    if schema_name != expected_schema.__name__:
        raise ValueError(f"Schema mismatch: {schema_name} != {expected_schema.__name__}")
    
    # Validate against current schema
    try:
        expected_schema(**data)
    except ValidationError as e:
        print(f"Schema validation failed: {e}")
```

---

## Questions?

- **Wo ist die Funktion?** → `agent/tools.py` (Line ~1163)
- **Welche Parameter?** → `output_path`, `data`, `schema`, `add_metadata`, `atomic`
- **Wie aktivieren?** → `from agent.tools import save_structured_json`
