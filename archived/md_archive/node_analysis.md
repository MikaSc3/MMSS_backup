# Detailed Node Analysis & Specification Validation

**Goal**: Map what each of the 11 nodes in workflow.py actually requires and produces, then validate app_workflow_v2.md against reality.

---

## Node-by-Node Breakdown

### **Node 1: resolve_paths** (Line 83)

**Purpose**: Find assembly and part directories within datasource_root

**Input State Keys**:
- `datasource_root`: Path to preprocessed stepparser output
- `use_unique_parts`: Boolean (default: True)

**Function Called**: `resolve_stepparser_layout_vars(str(root))`  
**Location**: agent/prompt_store.py:222

**What It Actually Does**:
- Expands datasource_root path
- Calls resolve_stepparser_layout_vars() which:
  - Looks for `assembly_*` folders OR legacy `.STEP` folders
  - Inside assembly_dir: finds `*_BOM.json` + `*_Overview_Stepparser.json`
  - In parent dir: finds `Part_*` folders
  - Reads `Part_*/Part_*_Data_stepparser.json` to detect copies (if name has "_copy")
  - Returns: assembly_dir, part_dirs, unique_part_dirs, part_count, etc.

**Files It Reads**:
- Scans: `{datasource_root}/` directory structure
- Reads: `Part_*/Part_*_Data_stepparser.json` (to detect copies)

**Output State Keys**:
- `assembly_dir`: String path to assembly directory
- `part_dirs`: List of all Part_* directories
- `unique_part_dirs`: List of Part_* (excluding copies)

**Folder Structure It Expects**:
```
datasource_root/
├── assembly_{name}/
│   ├── assembly_{name}_BOM.json
│   ├── assembly_{name}_Overview_Stepparser.json
│   └── (renderings)
├── Part_1/
│   ├── Part_1_Data_stepparser.json
│   └── ...
├── Part_2/
└── ...
```

**⚠️ CRITICAL**: This function SCANS the filesystem. It doesn't create any output files!

**Environment Variables**: None required

**LLM Calls**: None

---

### **Node 2: run_assembly** (Line 111)

**Purpose**: Analyze assembly structure using LLM (images + metadata)

**Input State Keys**:
- `datasource_root`: String path
- `assembly_dir`: String path (from resolve_paths)
- `assembly_keywords`: Optional list (image keywords to filter)
- `assembly_limit`: Optional int (max images to analyze)
- `overwrite_assembly_metadata`: Optional bool

**Function Called**: `analyse_assembly_img.invoke(payload)` from tools.py

**What It Actually Does**:
1. Builds payload: `{"searchdir": str(assembly_dir), "keywords": ..., "limit": ...}`
2. Calls `tools.analyse_assembly_img.invoke(payload)`
3. This function (tools.py):
   - Searches assembly_dir for image files matching keywords
   - Selects up to `limit` images
   - Sends to Azure LLM with system/user prompts
   - Returns JSON analysis

**Files It Reads**:
- Images in assembly_dir (*.png, *.jpg, etc.)
- Reads metadata JSON files if present (for context)

**Files It Writes**: **NONE** (purely in-memory analysis)

**Output State Keys**:
- `assembly_result`: Dict containing:
  - `analysis`: LLM analysis object
  - `stats`: Token usage, prompt_id, images selected
  - `metadata_written_path`: (sometimes populated)
  - `selected`: List of selected images

**Environment Variables**:
- `AZURE_ENDPOINT_4O`: Azure OpenAI endpoint (from agent/.env)
- `API_KEY_GPT_4`: API key (from agent/.env)

**LLM Calls**: YES (Azure OpenAI gpt-4o)

---

### **Node 3: list_parts** (Line 147)

**Purpose**: Catalog parts (minimal pass-through)

**Input State Keys**:
- `datasource_root`
- `assembly_dir`
- `part_dirs`

**Files It Reads**: None

**Files It Writes**: None

**Output**: Returns state unchanged (just carries forward)

**⚠️ OBSERVATION**: This node does nothing substantive. It's a placeholder.

---

### **Node 4: run_monoparts** (Line ~176)

**Purpose**: Analyze individual parts using LLM (per-part images + metadata)

**Input State Keys**:
- `datasource_root`
- `assembly_dir`
- `part_dirs`: List from resolve_paths
- `part_keywords`: Optional list
- `part_limit`: Optional int
- `parallel`: Boolean (enable parallel execution)
- `max_workers`: Int (if parallel)

**Function Called**: `_run_one_part(part_dir, part_keywords, part_limit)` → calls `analyse_monopart_img.invoke(payload)`

**What It Actually Does**:
1. For each part_dir in part_dirs:
   - Calls `analyse_monopart_img.invoke({"searchdir": part_dir, ...})`
   - LLM analyzes part images
   - Returns analysis JSON
2. If parallel=True: Uses ThreadPoolExecutor to parallelize
3. Accumulates results

**Files It Reads**: Images in each Part_*/

**Files It Writes**: **NONE** (results stay in-memory)

**Output State Keys**:
- `part_results`: List of dicts, one per part
  - Each contains: `analysis`, `stats`, `selected` images

**LLM Calls**: YES (Azure OpenAI gpt-4o, one call per part)

---

### **Node 5: merge_copy_part_data** (Line 325)

**Purpose**: Merge LLM-analyzed part data with stepparser instance metadata

**Input State Keys**:
- `assembly_name`: From state
- `datasource_root`
- `enable_merge_copy_part_data`: Boolean (default: True)

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory path (required!)

**Function Called**: `merge_copy_part_data(assembly_name, experiment_output_dir, stepparser_root)` from agent/merge_enriched.py

**What It Actually Does**:
1. Looks for enriched_parts/ in APA_EXPERIMENT_OUTPUT_DIR
2. Reads: `enriched_parts/*.json` (from merge_bom or direct writing)
3. Reads: `data/processed/stepparser/{assembly_name}/Part_*/Part_*_Data_stepparser.json`
4. Merges LLM analysis + stepparser metadata per part
5. Writes output to enriched_parts/ as `*_Data_enriched_merged.json`

**Files It Reads**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/*.json` (enriched part data)
- `data/processed/stepparser/{assembly_name}/Part_*/Part_*_Data_stepparser.json`

**Files It Writes**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/Part_{N}_Data_enriched_merged.json`
- Overwrites with merged instance-aware data

**Output State Keys**:
- `merge_copy_part_data_result`: Dict with status, merged_count, output_dir

**LLM Calls**: None

**⚠️ CRITICAL DEPENDENCY**: Requires APA_EXPERIMENT_OUTPUT_DIR environment variable!

---

### **Node 6: merge_bom** (Line 246)

**Purpose**: Consolidate all enriched part JSONs into single BOM file

**Input State Keys**:
- `assembly_name`: From state
- `datasource_root`
- `enable_merge_bom`: Boolean (default: True)

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**What It Actually Does**:
1. Looks in `{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/`
2. Finds all `*_Data_enriched_merged.json` files (or fallback to `*_Data_enriched.json`)
3. Loads and concatenates all part data
4. Creates merged BOM structure
5. Writes `{assembly_name}_BOM_enriched.json` to APA_EXPERIMENT_OUTPUT_DIR

**Files It Reads**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/*_Data_enriched_merged.json`

**Files It Writes**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/{assembly_name}_BOM_enriched.json`

**Output State Keys**:
- `merged_bom_path`: String path to written BOM file

**LLM Calls**: None

**⚠️ CRITICAL DEPENDENCY**: Requires APA_EXPERIMENT_OUTPUT_DIR environment variable!

---

### **Node 7: generate_assembly_sequence** (Line 394)

**Purpose**: Generate assembly sequence using LLM-based step reasoning

**Input State Keys**:
- `assembly_name`
- `datasource_root`
- `sequence_run_counter`: Int (iteration number, default 0)
- `enable_assembly_sequence`: Boolean (default: True)

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**Function Called**: `generate_assembly_sequence(assembly_name, assembly_dir, exp_output_dir, json_dir, image_keywords, json_keywords, remarks_context)` from agent/Assembly_sequence_generation.py

**What It Actually Does**:
1. Resolves assembly_dir from stepparser: `data/processed/stepparser/{assembly_name}/assembly_{assembly_name}/`
2. Determines current iteration: `run_folder_name = f"assembly_sequence_run{current_run}"`
3. Creates: `{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N}/`
4. If current_run >= 1: reads `assembly_sequence_run{N-1}/remarks.json` (previous remarks)
5. Calls generate_assembly_sequence() function with remarks_context
6. LLM generates step-by-step assembly plan
7. Writes per-step images + metadata
8. Writes: `assembly_sequence_run{N}/assembly_sequence.json`

**Files It Reads**:
- Assembly images from stepparser
- Previous remarks: `{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N-1}/remarks.json`
- BOM/enriched parts for context

**Files It Writes**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N}/assembly_sequence.json`
- `{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N}/step_{K}/` (per-step renderings)
- `{APA_EXPERIMENT_OUTPUT_DIR}/assembly_sequence_run{N}/step_{K}/step_metadata.json`

**Output State Keys**:
- `assembly_sequence_path`: Path to assembly_sequence.json
- `assembly_sequence_data`: Parsed sequence data
- `sequence_run_counter`: Incremented to N+1

**LLM Calls**: YES (Azure OpenAI, for sequence reasoning)

**⚠️ CRITICAL**: 
- Requires APA_EXPERIMENT_OUTPUT_DIR
- Requires remarks.json to exist at specific path for re-generation
- Creates `assembly_sequence_run{N}/` directory structure

---

### **Node 8: render_assembly_steps** (Line 596)

**Purpose**: Generate step-by-step visualizations of assembly sequence

**Input State Keys**:
- `assembly_name`
- `assembly_sequence_path`: From generate_assembly_sequence
- `enable_step_rendering`: Boolean (default: True)
- `sequence_run_counter`: Current iteration
- `last_rendered_run_counter`: Avoid re-rendering same iteration
- `current_sequence_run_dir`: Optional override for iteration directory

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**Function Called**: `render_assembly_steps(...)` from agent/Assembly_sequence_validation.py

**What It Actually Does**:
1. Checks if rendering already done for this iteration (skips if so)
2. Calls render_assembly_steps() function
3. Generates incremental visualizations
4. Saves step images to `sequence_renderings/` folder

**Files It Reads**:
- assembly_sequence.json
- Assembly CAD model + rendered images

**Files It Writes**:
- `{run_dir}/sequence_renderings/step_{K}.png` (per-step images)
- `{run_dir}/sequence_renderings/` directory

**Output State Keys**:
- `last_rendered_run_counter`: Set to current sequence_run_counter

**LLM Calls**: None (pure visualization)

**⚠️ CRITICAL**:
- requires APA_EXPERIMENT_OUTPUT_DIR
- Uses `current_sequence_run_dir` override if available (for iteration-specific rendering)

---

### **Node 9: interaction_analysis** (Line 760)

**Purpose**: Analyze geometric interactions (contacts, collisions, alignment) between assembly parts

**Input State Keys**:
- `assembly_name`
- `assembly_sequence_path`: From generate_assembly_sequence
- `datasource_root`
- `current_sequence_run_dir`: Optional override

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**Function Called**: `analyze_assembly_sequence_interactions(...)` from agent/Interaction_analysis.py

**Files It Reads**:
- `{run_dir}/assembly_sequence.json`
- `{run_dir}/sequence_renderings/` (per-step images)
- `data/processed/stepparser/{assembly_name}/` (part metadata)
- `{APA_EXPERIMENT_OUTPUT_DIR}/{assembly_name}_BOM_enriched.json`

**Files It Writes**:
- `{run_dir}/interaction_analysis.json` (interaction findings)

**Output State Keys**:
- `interaction_analysis_data`: Dict with interaction findings

**LLM Calls**: YES (Azure OpenAI, for interaction analysis)

**⚠️ CRITICAL**:
- Requires APA_EXPERIMENT_OUTPUT_DIR
- Depends on: assembly_sequence.json + sequence_renderings/ + BOM file
- Uses `current_sequence_run_dir` override if available

---

### **Node 10: validate_assembly_sequence** (Line 877)

**Purpose**: Validate assembly sequence feasibility (LLM per-step validation)

**Input State Keys**:
- `assembly_name`
- `datasource_root`
- `sequence_run_counter`: Current iteration
- `sequence_max_iterations`: Max allowed (from config)
- `current_sequence_run_dir`: Optional override

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**Function Called**: `validate_assembly_sequence(assembly_name, experiment_name, settings, exp_output_dir)` from agent/Assembly_sequence_validation.py

**What It Actually Does**:
1. Validates sequence if `ASV_mode != "disabled"`
2. Calls validate_assembly_sequence() function
3. LLM validates each step
4. Returns: overall_valid, all_parts_processed, step-by-step remarks
5. Writes remarks.json
6. Determines: should regenerate or finished?

**Files It Reads**:
- `{run_dir}/assembly_sequence.json`
- `{run_dir}/sequence_renderings/`
- BOM files

**Files It Writes**:
- `{run_dir}/remarks.json` (validation feedback)
- `assembly_sequence_validation/assembly_sequence_validation_merged.json` (if ASV_mode=enable)

**Output State Keys**:
- `assembly_sequence_validation_path`: Path to validation output
- Logic to determine: retry sequence generation or finish?

**LLM Calls**: YES (Azure OpenAI, for per-step validation)

**⚠️ CRITICAL**:
- Writes remarks.json that can trigger regeneration
- Conditional logic: if validation fails AND iterations left → regenerate
- Can loop back to generate_assembly_sequence node

---

### **Node 11: assess_ffa** (Line 1031)

**Purpose**: Assess automation fitness of assembly sequence

**Input State Keys**:
- `assembly_name`
- `datasource_root`
- `current_sequence_run_dir`: Optional override
- `interaction_analysis_data`: Optional (from IA node)

**Environment Variables**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Output directory (required!)

**Function Called**: `assess_assembly_sequence_ffa(...)` from agent/FFA_assessment.py

**Files It Reads**:
- `{run_dir}/assembly_sequence.json` (or from current_sequence_run_dir)
- `{run_dir}/sequence_renderings/`
- `{APA_EXPERIMENT_OUTPUT_DIR}/{assembly_name}_BOM_enriched.json`
- `{APA_EXPERIMENT_OUTPUT_DIR}/enriched_parts/`
- Optional: interaction_analysis.json (if include_interaction=true)

**Files It Writes**:
- `{APA_EXPERIMENT_OUTPUT_DIR}/ffa_assessment/ffa_assessment.json` (main output)
- Other supporting files in ffa_assessment/ folder

**Output State Keys**:
- `ffa_assessment_path`: Path to ffa_assessment/ directory

**LLM Calls**: YES (Azure OpenAI, for FFA assessment per step)

**⚠️ CRITICAL**:
- Searches for BOM: `*_BOM_enriched.json` in APA_EXPERIMENT_OUTPUT_DIR root
- FFA output goes to exp_output_root, NOT iteration folder (unlike sequence)
- Requires: sequence_renderings + BOM + enriched_parts

---

## Summary: Critical Dependencies & Folder Structure

### **Environment Variables (MUST BE SET)**:
- `APA_EXPERIMENT_OUTPUT_DIR`: Where all workflow outputs go. Set by orchestrator before calling nodes.
- `AZURE_ENDPOINT_4O`, `API_KEY_GPT_4`: Azure LLM credentials (from agent/.env)
- `APA_EXPERIMENT_YAML`: Path to experiment config YAML (optional but recommended)

### **Input Structure (datasource_root)**:
```
data/processed/stepparser/{assembly_name}/
├── assembly_{assembly_name}/
│   ├── assembly_{assembly_name}_BOM.json
│   ├── assembly_{assembly_name}_Overview_Stepparser.json
│   ├── images/
│   │   ├── iso1_transp_0_0.png
│   │   ├── exploded_iso1.png
│   │   └── ...
│   └── metadata.json
├── Part_1/
│   ├── Part_1_Data_stepparser.json
│   ├── images/
│   └── ...
└── Part_N/
```

### **Output Structure (APA_EXPERIMENT_OUTPUT_DIR)**:
```
{APA_EXPERIMENT_OUTPUT_DIR}/
├── enriched_parts/
│   ├── Part_1_Data_enriched_merged.json
│   └── ...
├── {assembly_name}_BOM_enriched.json
├── assembly_sequence_run1/
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   ├── step_1.png
│   │   └── ...
│   ├── step_1/
│   │   ├── step_image.png
│   │   └── step_metadata.json
│   └── remarks.json
├── assembly_sequence_run2/  (if regenerated)
│   ├── assembly_sequence.json
│   ├── remarks.json
│   └── ...
├── interaction_analysis.json  (from node 9, if enabled)
├── assembly_sequence_validation/  (from node 10, if enabled)
│   └── assembly_sequence_validation_merged.json
└── ffa_assessment/  (from node 11, if enabled)
    └── ffa_assessment.json
```

---

## Key DISCREPANCIES with app_workflow_v2.md

### **Issue 1: Where does enriched_parts/ come from?**

**Spec says**: merge_copy_part_data reads from enriched_parts/  
**Reality**: enriched_parts/ is written by merge_copy_part_data OR must pre-exist (from previous run or merge_bom)

**Actual flow**:
1. run_monoparts returns part_results (in-memory only)
2. merge_copy_part_data needs enriched_parts/*.json to exist
3. But who writes the initial enriched_parts/ ???

**Finding**: The workflow assumes enriched_parts/ is pre-populated (maybe by a different workflow path?). This is unclear in current nodes.

### **Issue 2: phase_1 should NOT call run_assembly?**

**Spec says**: Part 1 calls run_assembly (initial pass)  
**Reality**: run_assembly just calls LLM. It returns assembly_result but doesn't write files.

**Problem**: If we want Agent 1 context before Part 2 starts, run_assembly needs to be called in Part 1. But the spec says it happens twice (Part 1 + Part 2).

**Solution**: Either:
- A) Part 1 calls run_assembly once, Part 2 skips it
- B) Part 1 does lightweight filesystem scan, Part 2 calls run_assembly with full context + Agent 1 notes
- C) Create a separate "initial_assembly_analysis" node that's lightweight

### **Issue 3: remarks.json vs remarks.txt**

**Spec says**: remarks.txt (text file)  
**Reality**: validate_assembly_sequence writes remarks.json with structured data

**What should happen for iteration loop?**
- Agent 2 collects user remarks → writes remarks.txt (human feedback)
- Part 2 re-runs generate_assembly_sequence with remarks context
- OR: Part 2 reads remarks.json from validation node?

### **Issue 4: When are enriched_parts files created?**

**Spec**: merge_copy_part_data reads enriched_parts/  
**Reality**: Who creates enriched_parts/ in first place?

Looking at node 5 code: it reads from enriched_parts/ that should exist. But if this is the first run, where do these files come from?

**Hypothesis**: Nodes expect enriched_parts/ to be pre-populated by an earlier phase we're not seeing. Or they should be created by run_monoparts before being passed to merge_copy_part_data.

### **Issue 5: remarks.json structure for feedback loop**

**Theory**: validate_assembly_sequence writes remarks.json with validation findings. But for the feedback loop (Agent 2 → Part 2), we need to signal Part 2 to re-run generate_assembly_sequence.

**How?** 
- Does generate_assembly_sequence read remarks.json from validate node?
- Or does Agent 2 write a separate remarks.txt, and Part 2 reads that?
- Or both?

---

## Clarification Questions for User

1. **enriched_parts/ creation**: Where/when are enriched_parts/*.json files first created? Is run_monoparts supposed to write them directly? Or is there a step we're missing?

2. **run_assembly duplication**: Should Part 1 call run_assembly (lightweight, for Agent 1 context), then Part 2 calls it again (full analysis)? Or once per workflow?

3. **remarks feedback mechanism**: For Agent 2 → Part 2 loop:
   - User gives feedback to Agent 2
   - Should Agent 2 write remarks.txt (human-approved feedback)?
   - Then Part 2 reads remarks.txt and re-runs generate_assembly_sequence with remarks as context?

4. **Iteration directory naming**: When generate_assembly_sequence re-runs after remarks, does it create:
   - `assembly_sequence_run1_iteration_2/` ?
   - Or `assembly_sequence_run2/` ?
   - Current node uses `assembly_sequence_run{counter}` (flat, no iteration nesting)

5. **Validate node intent**: Should validate_assembly_sequence run AFTER user approves in Agent 2? Or before? Or both?

---

**Next**: Once you clarify these, I can update app_workflow_v2.md with exact folder structures and data flows that match reality.
