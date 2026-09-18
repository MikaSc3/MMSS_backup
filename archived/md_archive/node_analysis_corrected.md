# CORRECTED NODE ANALYSIS - Actual Behavior vs Specification

**Status**: Complete investigation of all 11 nodes  
**Date**: 2026-03-24

---

## Node 1: resolve_paths

**Input State**: `datasource_root` (path to preprocessed stepparser)  
**Output State**: Adds `assembly_dir`, `part_dirs`, `unique_part_dirs` (strings)  
**Files Written**: None (pure filesystem scan)  
**Files Read**: Part_*/Part_*_Data_stepparser.json (to detect copies)

---

## Node 2: run_assembly (Part 1 INITIAL PASS)

**Purpose**: Analyze assembly images + create context

**Input State**:
- `datasource_root`
- `assembly_dir` (from resolve_paths)
- `assembly_keywords` (optional)
- `assembly_limit` (optional)

**Function**: `analyse_assembly_img.invoke(payload)` from tools.py

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/
└── {assembly_name}-Metadata_assembly_enriched.json
```

**Output State**:
- `assembly_result`: Contains:
  - `searchdir`: resolved directory
  - `metadata_written_path`: path to the enriched JSON (in exp output dir)
  - `analysis`: LLM analysis results
  - `warnings`: list of warnings

**LLM Call**: YES (Azure OpenAI gpt-4o)

**Special**:
- Reads existing assembly metadata (if exists) to inject into prompt
- Merges stepparser metadata + LLM analysis into enriched file
- If APA_EXPERIMENT_OUTPUT_DIR is set: writes to experiment output dir (this enables file reuse across runs)

---

## Node 3: list_parts

**Purpose**: Placeholder, catalog parts

**Input State**: `datasource_root`, `assembly_dir`, `part_dirs`

**Output State**: Returns same state (pure pass-through)

**Files Written**: None

**Files Read**: None

**LLM Call**: No

**⚠️ This node is a stub. It does nothing.**

---

## Node 4: run_monoparts (Part 2 FULL PASS)

**Purpose**: Analyze individual parts with LLM

**Input State**:
- `datasource_root`
- `assembly_dir`
- `part_dirs` (list from resolve_paths)
- `part_keywords` (optional)
- `part_limit` (optional)
- `parallel` (boolean)
- `max_workers` (int)

**Function**: `analyse_monopart_img.invoke(payload)` for each part (from tools.py)

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/
├── Part_1-Metadata_enriched.json
├── Part_2-Metadata_enriched.json
└── ...
```

**Output State**:
- `part_results`: List of result dicts
  - Each contains: `searchdir`, `metadata_written_path`, `analysis`, `warnings`, etc.

**LLM Call**: YES (Azure OpenAI gpt-4o, one call per part)

**Special**:
- Can run parallel via ThreadPoolExecutor (if config allows)
- Injects part metadata + assembly context into prompts
- Merges stepparser metadata + LLM analysis into enriched files
- Writes directly to `enriched_parts/` subdirectory of experiment output

---

## Node 5: merge_copy_part_data

**Purpose**: Enhance enriched parts with instance-specific stepparser metadata

**Input State**:
- `assembly_name`
- `datasource_root`
- Expects: enriched_parts/ already populated by run_monoparts

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR` (required)

**Function**: `merge_copy_part_data(assembly_name, experiment_output_dir, stepparser_root)` from agent/merge_enriched.py

**What It Reads**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/
├── Part_1-Metadata_enriched.json
└── ...

data/processed/stepparser/{assembly_name}/
├── Part_1/Part_1_Data_stepparser.json
└── ...
```

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/
├── Part_1_Data_enriched_merged.json  ← instance-aware merged
└── ...
```

**Output State**: `merge_copy_part_data_result` dict

**LLM Call**: No

**Key Flow**:
1. Reads LLM-enriched metadata from run_monoparts
2. Reads stepparser instance metadata (per-part, detects duplicates)
3. Merges both into instance-aware enriched files with "_merged" suffix

---

## Node 6: merge_bom

**Purpose**: Consolidate all part data into single BOM file

**Input State**:
- `assembly_name`
- `datasource_root`
- Expects: enriched_parts/*_Data_enriched_merged.json (from merge_copy_part_data)

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR` (required)

**What It Reads**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/
├── Part_1_Data_enriched_merged.json
├── Part_2_Data_enriched_merged.json
└── ...
```

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/
└── {assembly_name}_BOM_enriched.json
```

**Output State**: `merged_bom_path` (string path)

**LLM Call**: No

**Key**: Reads all enriched parts, concatenates into single BOM structure with metadata

---

## Node 7: generate_assembly_sequence

**Purpose**: Generate step-by-step assembly sequence using LLM

**Input State**:
- `assembly_name`
- `datasource_root`
- `sequence_run_counter` (default: 0)
- Expects: assembly_sequence_run{N}/remarks.json (if N > 0, for feedback context)

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR` (required)

**Function**: `generate_assembly_sequence(...)` from agent/Assembly_sequence_generation.py

**What It Reads** (on first run):
- Assembly images from `data/processed/stepparser/{assembly_name}/assembly_{assembly_name}/`
- Assembly metadata (BOM, Overview_Stepparser.json)
- Part images for context

**What It Reads** (on iteration N > 1):
```
{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N-1}/
└── remarks.json  ← human feedback from previous iteration
```

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/
└── assembly_sequence_run{N}/
    ├── assembly_sequence.json  ← the sequence plan
    ├── step_1/
    │   ├── step_image.png
    │   └── step_metadata.json
    ├── step_2/
    └── ...
```

**Output State**:
- `assembly_sequence_path`: Path to sequence.json
- `assembly_sequence_data`: Parsed sequence dict
- `sequence_run_counter`: Incremented (0→1, 1→2, etc)

**LLM Call**: YES (Azure OpenAI gpt-4o, for sequence reasoning)

**Iteration Logic**:
```
if previous_run >= 1:
  read remarks.json from assembly_sequence_run{previous}/
  pass to LLM as "remarks_context" (injected into prompt)
```

**Critical**: Counter-based naming (run1, run2, run3...) not iteration-nested

---

## Node 8: render_assembly_steps

**Purpose**: Generate step visualizations

**Input State**:
- `assembly_name`
- `assembly_sequence_path` (from node 7)
- `enable_step_rendering` (default: True)
- `sequence_run_counter` / `last_rendered_run_counter` (skip if already rendered)

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR`

**Function**: `render_assembly_steps(...)` from Assembly_sequence_validation.py

**What It Reads**:
- `assembly_sequence.json` (from node 7)
- Assembly CAD model

**What It Writes**:
```
{run_dir}/sequence_renderings/
├── step_1.png
├── step_2.png
└── ...
```

**Output State**: `last_rendered_run_counter` (set to current counter)

**LLM Call**: No

---

## Node 9: interaction_analysis

**Purpose**: Analyze geometric interactions between parts per step

**Input State**:
- `assembly_name`
- `assembly_sequence_path` (from node 7)
- Current sequence run directory

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR`

**Function**: `analyze_assembly_sequence_interactions(...)` from Interaction_analysis.py

**What It Reads**:
```
{run_dir}/assembly_sequence.json
{run_dir}/sequence_renderings/step_*.png
{APA_EXPERIMENT_OUTPUT_DIR}/{assembly_name}_BOM_enriched.json
data/processed/stepparser/{assembly_name}/  (part geometry)
```

**What It Writes**:
```
{run_dir}/interaction_analysis.json
```

**Output State**: `interaction_analysis_data` dict

**LLM Call**: YES (per-step interaction analysis)

---

## Node 10: validate_assembly_sequence

**Purpose**: [DEPRECATED FOR APP_WORKFLOW_V2] Validate sequence feasibility

**Note**: User said this automated validation approach didn't work well. Agent 2 (human interaction) replaces this role. But node remains in workflow.py for reference.

**Input State**: Various (assembly_name, sequence path, etc)

**Function**: `validate_assembly_sequence(...)` from Assembly_sequence_validation.py

**What It Writes**:
```
{run_dir}/remarks.json (validation findings)
assembly_sequence_validation/assembly_sequence_validation_merged.json
```

**LLM Call**: YES

**For app_workflow_v2**: This node is SKIPPED. Agent 2 handles validation via user interaction.

---

## Node 11: assess_ffa

**Purpose**: Assess automation fitness of assembly

**Input State**:
- `assembly_name`
- Sequence and BOM paths
- Optional: `interaction_analysis_data`

**Environment Variable**: `APA_EXPERIMENT_OUTPUT_DIR`

**Function**: `assess_assembly_sequence_ffa(...)` from FFA_assessment.py

**What It Reads**:
```
{sequence_run_dir}/assembly_sequence.json
{sequence_run_dir}/sequence_renderings/
{APA_EXPERIMENT_OUTPUT_DIR}/{assembly_name}_BOM_enriched.json
{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/ (optional)
```

**What It Writes**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/ffa_assessment/
└── ffa_assessment.json
```

**Output State**: `ffa_assessment_path` (string)

**LLM Call**: YES (per-step FFA scoring)

---

## KEY FINDINGS FOR APP_WORKFLOW_V2

### Part 1: Preprocessing + Initial Context
1. **resolve_paths**: Scan, no writes
2. **run_assembly (initial)**: Write `{assembly_name}-Metadata_assembly_enriched.json` to exp output dir
3. **Agent 1 reads**: assembly_result JSON + created additional_info.txt

### Part 2: Enrichment + Sequence
1. **run_assembly (full)**: Re-run with Agent 1 additional_info as context, overwrites same JSON
2. **list_parts**: Pure pass-through (do nothing)
3. **run_monoparts**: Write `enriched_parts/Part_*-Metadata_enriched.json`
4. **merge_copy_part_data**: Enhance to `enriched_parts/Part_*_Data_enriched_merged.json`
5. **merge_bom**: Write `{assembly_name}_BOM_enriched.json` to root
6. **generate_assembly_sequence (run1)**: Write `assembly_sequence_run1/assembly_sequence.json`
7. **render_assembly_steps**: Write `assembly_sequence_run1/sequence_renderings/step_*.png`
8. **Agent 2 awakes**: Reads sequence.json, presents to user, collects remarks

### Part 3: Iterative Refinement (Agent 2 ↔ Part 2 Loop)
1. User gives remarks to Agent 2
2. Agent 2 writes: `assembly_sequence_run1/remarks.txt` (human-readable feedback)
3. **Decision**: Should we write remarks.json OR remarks.txt for workflow to read?
   - **Option A**: Agent 2 writes both .txt and .json
   - **Option B**: Workflow converts .txt → .json
   - **Option C**: Both agents use .json, .txt is just for user display
4. If feedback: signal Part 2 to re-run generate_assembly_sequence with remarks context
5. generate_assembly_sequence increments counter: `assembly_sequence_run2/`
6. Loop continues until user says approval keyword

### Part 4: Quality Assessment
1. **render_assembly_steps**: Ensure final approved sequence is rendered
2. **interaction_analysis**: Analyze final sequence
3. **assess_ffa**: Assess automation fitness in `ffa_assessment/`
4. **Agent 3 awakes**: Reads FFA results, explains to user

---

## CLARIFICATION NEEDED: remarks.txt vs remarks.json

**Current Understanding**:
- Agent 2 collects user feedback
- User wants remarks.txt (like additional_info.txt)
- Workflow needs to re-run generate_assembly_sequence with remarks as context
- generate_assembly_sequence code reads `remarks.json` from previous run

**Three Options**:

**A) Agent writes both**:
```
Agent 2 writes:
  assembly_sequence_run1/remarks.txt (human feedback, any format)
  assembly_sequence_run1/remarks.json (structured for workflow)
```

**B) Workflow converts**:
```
Agent 2 writes: assembly_sequence_run1/remarks.txt
Part 2 in-between step: Convert remarks.txt → remarks.json
generate_assembly_sequence reads: remarks.json
```

**C) Standardize on .json**:
```
Agent 2 writes: assembly_sequence_run1/remarks.json (both for workflow + display)
remarks.txt is not created
```

**User Preference?** The user said "remarks.txt works best, use identical utils like additional_info.txt". So probably **Option A**: write both for maximum compatibility and clarity.

---

## ITERATION NAMING CONFIRMATION

**Current Node Logic**: `assembly_sequence_run{N}` where N increments

**Examples**:
- First generation: `assembly_sequence_run1/assembly_sequence.json`
- User gives feedback → Agent 2 writes `assembly_sequence_run1/remarks.txt`
- Re-run generation: `assembly_sequence_run2/assembly_sequence.json` (created with remarks context from run1/)
- User gives more feedback: `assembly_sequence_run2/remarks.txt`
- Re-run again: `assembly_sequence_run3/...`

This is **flat naming**, not nested. ✅ Confirmed.

---

## ENVIRONMENT VARIABLE REQUIREMENT

**Critical**: All nodes from node 5 onward **require** `APA_EXPERIMENT_OUTPUT_DIR` to be set.

**Orchestrator Responsibility** (app_workflow_part1, part2, part4):
```python
session_root = Path("data/sessions/{timestamp}")
exp_output_dir = session_root / "phase_2"  # or whatever phase
exp_output_dir.mkdir(parents=True, exist_ok=True)

os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(exp_output_dir)

# Then call workflow
```

**⚠️ If not set**: Nodes will either fail or write to stepparser directory (legacy fallback)

---

## ACTUAL DATA FLOW DIAGRAM

```
Part 1:
  └─ resolve_paths (scan, no write)
  └─ run_assembly (INITIAL pass)
     └─ writes: {assembly_name}-Metadata_assembly_enriched.json v1
  └─ SIGNAL: Agent 1 awakes
  └─ Agent 1 reads assembly_result.json, writes additional_info.txt

Part 2:
  └─ run_assembly (FULL pass with additional_info context)
     └─ overwrites: {assembly_name}-Metadata_assembly_enriched.json v2
  └─ list_parts (pass-through, no-op)
  └─ run_monoparts (parallel analysis per part)
     └─ writes: enriched_parts/Part_*-Metadata_enriched.json
  └─ merge_copy_part_data
     └─ enhances: enriched_parts/Part_*_Data_enriched_merged.json
  └─ merge_bom
     └─ writes: {assembly_name}_BOM_enriched.json (consolidated)
  └─ generate_assembly_sequence (run1)
     └─ writes: assembly_sequence_run1/assembly_sequence.json
  └─ render_assembly_steps
     └─ writes: assembly_sequence_run1/sequence_renderings/step_*.png
  └─ SIGNAL: Agent 2 awakes

Part 3 (Loop):
  Agent 2:
    └─ Display: assembly_sequence_run1/assembly_sequence.json
    └─ Collect user remarks
    └─ Write: assembly_sequence_run1/remarks.txt + remarks.json

  Part 2 (re-triggered):
    └─ generate_assembly_sequence (run2, reads remarks from run1/)
       └─ writes: assembly_sequence_run2/assembly_sequence.json
    └─ render_assembly_steps
       └─ writes: assembly_sequence_run2/sequence_renderings/step_*.png
    └─ BACK TO: Agent 2 shows run2 sequence

  Until user approves:
    └─ Agent 2 writes: approved/remarks.txt
    └─ SIGNAL: Part 4 starts

Part 4:
  └─ render_assembly_steps (final)
  └─ interaction_analysis
     └─ writes: interaction_analysis.json
  └─ assess_ffa
     └─ writes: ffa_assessment/ffa_assessment.json
  └─ SIGNAL: Agent 3 awakes
  
  Agent 3:
    └─ Display: FFA results
    └─ Answer user questions
```

---

**Next Steps**: 
1. Confirm remarks.txt vs .json strategy
2. Update app_workflow_v2.md with corrected actual behavior
3. Ready to start Part 1 implementation
