# FFA Split-Calls Spezifikation & Implementierungs-TODO

## 📋 Anforderungsübersicht

**Ziel:** Ersetze den monolithischen `assess_assembly_sequence_ffa()` Call durch 4 serielle LLM-Calls (Separation, Handling, Positioning, Joining).

**Motivation:** Besseres Testing, granularere Fehlerbehandlung, Flexibilität bei Modelländerungen pro Kategorie.

---

## 1️⃣ EXECUTION PATTERN

### Seriell pro Step:
```
Step 1:
  → Separation Call
  → Handling Call
  → Positioning Call
  → Joining Call
  → Assembly → FFA_Assessment (Step 1)

Step 2:
  → Separation Call
  → ... (parallel mit Step 1 Calls starten, aber intern seriell)
```

### Implementation:
- Step 1 & Step 2 Separation-Calls können parallel laufen
- Aber Step 1 Separation→Handling→Positioning→Joining müssen seriell sein
- **Einfachster Ansatz**: Temp-Folder mit Step-spezifischen Subfoldern:
  ```
  data/experiments/<run>/ffa_assessment_intermediate/
    ├── step_001/
    │   ├── separation_output.json
    │   ├── handling_output.json
    │   ├── positioning_output.json
    │   └── joining_output.json
    ├── step_002/
    │   ├── separation_output.json
    │   └── ...
  ```

---

## 2️⃣ PROMPT MANAGEMENT

### Neue Prompts in `configs/prompts.yaml`:
- Bestehende Prompts NICHT ändern (Backward-Compatibility)
- **Neue Duplikate** für Split-Calls:
  - `ffa_separation_V1` (kopiert aus `ffa_seperation_V1` Human-Task)
  - `ffa_handling_V1` (neu)
  - `ffa_positioning_V1` (neu)
  - `ffa_joining_V1` (neu)

### Prompt-ID Konvention:
```yaml
# System Prompts (unchanged)
automation_expert_v2_neutral:
  ...

# Human Task Prompts für Split-Calls
ffa_separation_V1:  # from configs/prompts.yaml (existing)
  text: |
    [Kopie des ffa_seperation_V1 Prompt von oben]

ffa_handling_V1:
  text: |
    [Kopie des ffa_handling_V1 Prompt von oben]

ffa_positioning_V1:
  text: |
    [Kopie des ffa_positioning_V1 Prompt von oben]

ffa_joining_V1:
  text: |
    [Kopie des ffa_joining_V1 Prompt von oben]
```

---

## 3️⃣ DATA FILTERING & PAYLOAD

### Anforderung: *Erst mal alle Daten, später filtern*

**Payload pro Call:**
```json
{
  "step_id": 1,
  "step_description": "Place lever arm on assembly table",
  "base_part_metadata": {...all fields...},      // Alle Daten, kein Filtering
  "joining_part_metadata": {...all fields...},   // Alle Daten
  "prior_step_images": [...],
  "current_step_images": [...]
}
```

**Future Optimization:**
- Filtering könnte per-Call optimiert werden (z.B. Separation braucht nur joining_part)
- Aber für Phase 1: *alles mitgeben*

---

## 4️⃣ OUTPUT STRUCTURE

### Sub-Outputs (Mini-Responses):

#### `separation_output.json`:
```json
{
  "step_id": 1,
  "category": "separation",
  "options_analysis": "...",
  "nature_of_provision": "in magazine (defined position and orientation)",
  "reasoning": "...",
  "evidence": ["..."],
  "status": "success",        // or "retry_exceeded", "endpoint_error"
  "model": "gpt-4o-2024-08-06",
  "timestamp": "2026-03-13T..."
}
```

#### `handling_output.json`:
```json
{
  "step_id": 1,
  "category": "handling",
  "options_analysis": "...",
  "part_rigidity": "rigid",
  "gripping_areas": "pronounced gripping area existing",
  "orientation_features": "mechanical self-adjustement in gripper possible",
  "surface_sensibility": "immune",
  "reasoning": "...",
  "evidence": ["..."],
  "status": "success",
  "model": "gpt-4o-2024-08-06",
  "timestamp": "2026-03-13T..."
}
```

#### `positioning_output.json`:
```json
{
  "step_id": 1,
  "category": "positioning",
  "options_analysis": "...",
  "accuracy_of_target_position": "base part position defined / joining point position defined",
  "positioning_aids": "insertion chamfers and stopping edge",
  "additional_orientation_by_rotation": "not required",
  "accessibility_to_joining_position": "visibility given / tool clearances given",
  "positioning_motion": "linear joining motion",
  "tolerances": "+/- 0.1 mm",
  "stability_in_positioned_state": "stable, self-holding",
  "reasoning": "...",
  "evidence": ["..."],
  "status": "success",
  "model": "gpt-4o-2024-08-06",
  "timestamp": "2026-03-13T..."
}
```

#### `joining_output.json`:
```json
{
  "step_id": 1,
  "category": "joining",
  "options_analysis": "...",
  "feeding_of_joining_element": "not necessary",
  "fixing_of_mounted_part": "automatable with standard solution",
  "reasoning": "...",
  "evidence": ["..."],
  "status": "success",
  "model": "gpt-4o-2024-08-06",
  "timestamp": "2026-03-13T..."
}
```

### Final FFA_Assessment (Assembled):
```json
{
  "step_id": 1,
  "step_description": "...",
  "assessment": {
    "separation": {...from separation_output.json},
    "handling": {...from handling_output.json},
    "positioning": {...from positioning_output.json},
    "joining": {...from joining_output.json}
  },
  "metadata": {
    "source": "split_calls",
    "intermediate_dir": "ffa_assessment_intermediate/step_001/",
    "assembly_timestamp": "2026-03-13T...",
    "all_calls_successful": true,   // Flag: whether all 4 calls succeeded
    "failed_categories": []         // List of failed categories (for debugging)
  }
}
```

---

## 5️⃣ FALLBACK & ERROR HANDLING

### Retry-Logik (Existing Pattern):
```python
# Use existing HTTPx + exponential backoff from tools.py / langchain
max_retries = 3
retry_delay = [2, 5, 10]  # seconds

for attempt in range(max_retries):
    try:
        response = llm_call(...)
        break
    except (TimeoutError, HTTPError) as e:
        if attempt < max_retries - 1:
            time.sleep(retry_delay[attempt])
        else:
            # Mark category as failed, set status flag
            sub_output["status"] = "retry_exceeded"
            sub_output["error"] = str(e)
```

### Flags in Output:
- `status`: "success" | "retry_exceeded" | "endpoint_error" | "validation_error"
- `error`: error message (if status != success)
- `all_calls_successful`: boolean in final FFA_Assessment

### End-of-Run Analysis:
- Parse all intermediate folders
- Count successful vs failed calls
- Flag steps with incomplete assessments for manual review
- Write summary report: `ffa_assessment_run_summary.json`

---

## 6️⃣ STRUCTURE: WORKFLOW + SCRIPTS

### New Workflow: `workflow_ffa_split_calls.py`
```
Workflow("FFA_Split_Calls")
├── Node: load_checkpoint_data
├── Node: iterate_over_steps (for each assembly step)
│   ├── Node: ffa_separation_node        (prompts: ffa_separation_V1, system: automation_expert_v2_neutral)
│   ├── Node: ffa_handling_node          (prompts: ffa_handling_V1, system: automation_expert_v2_neutral)
│   ├── Node: ffa_positioning_node       (prompts: ffa_positioning_V1, system: automation_expert_v2_neutral)
│   ├── Node: ffa_joining_node           (prompts: ffa_joining_V1, system: automation_expert_v2_neutral)
│   └── Node: assemble_ffa_assessment    (combines 4 outputs → final FFA_Assessment JSON)
├── Node: finalize_outputs (collect all step assessments, generate summary)
└── Node: log_intermediate_cleanup (optional: cleanup temp folder or keep for debugging)
```

### New Script: `run_ffa_only_seperate_calls.py`
```python
"""
Load checkpoint → Run workflow_ffa_split_calls → Output to evaluation JSON

Usage:
  python run_ffa_only_seperate_calls.py data/checkpoints/2026-03-03_133817-4o/exp_baseline_seq_gt_run1
  python run_ffa_only_seperate_calls.py --checkpoint-root <path> --output-dir data/experiments/<run>/
"""
```

---

## 7️⃣ OUTPUT STRUCTURE (Final)

```
data/experiments/<run>/ffa_assessment_split_calls/
├── step_001/
│   ├── separation_output.json
│   ├── handling_output.json
│   ├── positioning_output.json
│   ├── joining_output.json
│   └── ffa_assessment_step_001.json   (assembled)
├── step_002/
│   ├── ...
├── ...
├── ffa_assessment_complete.json        (all steps, like current output)
└── ffa_assessment_run_summary.json     (meta: success counts, errors, etc.)
```

---

## 8️⃣ ASSEMBLY LOGIC (Pseudo-Code)

```python
def assemble_ffa_from_split_outputs(step_id: int, intermediate_dir: Path) -> FFA_Assessment:
    """
    Read 4 JSON files (separation, handling, positioning, joining).
    Combine into single FFA_Assessment object matching current schema.
    """
    sep = load_json(intermediate_dir / f"step_{step_id:03d}" / "separation_output.json")
    hdl = load_json(intermediate_dir / f"step_{step_id:03d}" / "handling_output.json")
    pos = load_json(intermediate_dir / f"step_{step_id:03d}" / "positioning_output.json")
    joi = load_json(intermediate_dir / f"step_{step_id:03d}" / "joining_output.json")
    
    ffa_assessment = FFA_Assessment(
        step_id=step_id,
        separation=sep,
        handling=hdl,
        positioning=pos,
        joining=joi,
        metadata={
            "source": "split_calls",
            "all_successful": all(o["status"] == "success" for o in [sep, hdl, pos, joi])
        }
    )
    return ffa_assessment
```

---

## 9️⃣ IMPLEMENTATION PLAN

### Phase 1: Specification & Setup ✅ (THIS FILE)
- [ ] User reviews & clarifies requirements
- [ ] Confirm data payload structure
- [ ] Confirm output format

### Phase 2: Prompts & Schema
- [ ] Copy 4 prompts → `configs/prompts.yaml`
- [ ] Define/verify output schemas (FFA_Assessment_Separation, etc.)
- [ ] Check structured output compatibility per category

### Phase 3: Workflow Development
- [ ] Create `agent/workflow_ffa_split_calls.py`
- [ ] Implement 4 Node functions (separation, handling, positioning, joining)
- [ ] Implement assembly function
- [ ] Add retry/fallback logic

### Phase 4: Run Script
- [ ] Create `run_ffa_only_seperate_calls.py`
- [ ] Load checkpoint data
- [ ] Call workflow
- [ ] Save outputs (intermediate + final)
- [ ] Generate summary report

### Phase 5: Testing
- [ ] Test single step (manual)
- [ ] Test full assembly sequence
- [ ] Compare output format vs. current FFA assessments
- [ ] Validate error handling (simulate endpoint failure)

### Phase 6: Integration & Cleanup
- [ ] Merge to main branch (if all tests pass)
- [ ] Document usage in README
- [ ] Optional: add run_ffa_only_seperate_calls to evaluation orchestration

---

## 🔟 QUESTIONS TO CLARIFY

1. **Parallelization:** Do you want Steps 1+2 to start in parallel (but each Step internally serial)? Or fully serial (Step 1 → Step 2)?
   - Recommendation: Parallel Step execution, serial Category execution per Step.

2. **Intermediate Folder Cleanup:** Keep temp folder after run or delete?
   - Recommendation: Keep for debugging; add flag `--cleanup-intermediate` to delete after final export.

3. **Output Compatibility:** Should final JSON match current `ffa_assessment.json` schema exactly?
   - Recommendation: Yes, nested structure with `separation`, `handling`, `positioning`, `joining` as sub-objects.

4. **Model Selection:** Do all 4 calls use the same LLM model, or per-category model selection?
   - Recommendation: Same model (consistent), but structure allows per-category override in future.

5. **Data Filtering Phase 2:** When to implement filtering (e.g., Separation only needs joining_part)?
   - Recommendation: Phase 1 = no filtering (all data). Phase 2 = optimize payload per category.

---

## 📌 SUMMARY

| Component | Status | Owner | Timeline |
|-----------|--------|-------|----------|
| Spec (this file) | ✅ Draft | You → User | Now |
| Prompts (4×) | 🔲 Write | TBD | After spec approval |
| Workflow | 🔲 Code | TBD | After prompts |
| Run script | 🔲 Code | TBD | After workflow |
| Testing | 🔲 Test | TBD | After all code |
| Integration | 🔲 Merge | TBD | End |

