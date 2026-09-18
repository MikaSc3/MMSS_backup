# run_all_nodes Workflow: Data Input/Output Guide

**Purpose:** Complete APA pipeline for assembly enrichment, sequence generation/validation, interaction analysis, and FFA assessment.

---

## Overview

The `run_all_nodes` workflow consists of **11 nodes** executing sequentially (with 1 conditional retry loop):

```
resolve_paths
    ↓
run_assembly
    ↓
list_parts
    ↓
run_monoparts
    ↓
merge_copy_part_data
    ↓
merge_bom
    ↓
generate_assembly_sequence
    ↓
render_assembly_steps
    ↓
interaction_analysis ✅ NEW (23.02.2026)
    ↓
validate_assembly_sequence ◄─── (retry loop back)
    ↓
assess_ffa (with optional interaction context)
    ↓
END
```

---

## Node Details

### 1. **resolve_paths**

**Purpose:** Resolve directory layout and identify assembly/parts folders.

**Inputs (from state):**
- `datasource_root` - Root directory of assembly data (e.g., `data/ground_truth/assembly_X/`)
- `use_unique_parts` - Boolean (default: `True`). If `True`, use `unique_part_dirs`; else use `part_dirs`

**Loads from:**
- **Directories:** Recursively scanned for assembly/parts structure

**Saves:** None

**Returns to state:**
- `assembly_dir` - Full path to assembly folder (e.g., `.../assembly_X/Assemly/`)
- `part_dirs` - List of unique part directories (e.g., `['.../Part_1/', '.../Part_2/', ...]`)

---

### 2. **run_assembly**

**Purpose:** Analyze assembly images using LLM-based image analysis tool.

**Inputs (from state):**
- `assembly_dir` - Directory containing assembly images/metadata
- `assembly_keywords` - Optional list of keywords to filter images
- `assembly_limit` - Max images to process (default: 8)
- `overwrite_assembly_metadata` - Boolean (default: `True`)

**Loads from:**
- **Files in `assembly_dir`:**
  - Assembly images (detected by `analyse_assembly_img` tool)
  - Optional metadata files (e.g., `-Metadata.json`, `-Metadata_enriched.json`)

**Saves:** None (results in memory only)

**Returns to state:**
- `assembly_result` - Complex dict with:
  - `analysis` - Analysis results
  - `stats` - Stats including `prompt_id`, `prompt_preview`
  - `selected` - Selected images analyzed
  - `analysis.stats.tokens_used` - Token usage data

---

### 3. **list_parts**

**Purpose:** Placeholder node. Validates that `part_dirs` exist.

**Inputs (from state):**
- `part_dirs` - List of part directories

**Loads from:** None

**Saves:** None

**Returns to state:** Unchanged (carry-through)

---

### 4. **run_monoparts**

**Purpose:** Analyze individual part images (parallel or sequential).

**Inputs (from state):**
- `part_dirs` - List of part directories to analyze
- `parallel` - Boolean (default: `False`). If `True`, process parts in parallel
- `max_workers` - Number of parallel workers (default: 4)
- `part_keywords` - Optional keywords to filter images
- `part_limit` - Max images per part (default: 8)

**Loads from:**
- **Files in each `part_dir`:**
  - Part images (detected by `analyse_monopart_img` tool)
  - Optional metadata files (e.g., `-Metadata.json`)

**Saves:** None (results in memory only)

**Returns to state:**
- `part_results` - List of analysis results (one per part):
  - Each result has same structure as `assembly_result`
- `warnings` - List of warning strings (failed parts, etc.)

---

### 5. **merge_copy_part_data**

**Purpose:** Merge enriched part JSON files with instance-specific Stepparser metadata (Phase 4.2: instance-aware enrichment).

**Inputs (from state):**
- `assembly_name` - Name of assembly (e.g., `assembly_1`)
- `enable_merge_copy_part_data` - Boolean (default: `True`). Skip if `False`

**Loads from:**
- **Stepparser metadata:** `data/processed/stepparser/{assembly_name}/` 
  - Looks for assembly-specific JSON files with part metadata
- **Previous enrichment:** `{exp_output_dir}/enriched_parts/` (if present)

**Saves to:**
- `{exp_output_dir}/enriched_parts/` 
  - `*_Data_enriched_merged.json` files (instance-aware, one per part)
  - Merges LLM enrichment with Stepparser instance metadata

**Returns to state:**
- `merge_copy_part_data_result` - Dict with:
  - `status` - "success" or "error"
  - `merged_count` - Number of parts merged
  - `output_dir` - Output directory path
  - `errors` - List of error messages

---

### 6. **merge_bom**

**Purpose:** Consolidate all enriched part JSON files into a single Bill of Materials (BOM).

**Inputs (from state):**
- `assembly_name` - Assembly name
- `enable_merge_bom` - Boolean (default: `True`). Skip if `False`

**Loads from:**
- **Primary:** `{exp_output_dir}/enriched_parts/`
  - Prefers `*_Data_enriched_merged.json` (Phase 4.2 output)
  - Fallback to `*_Data_enriched.json` (legacy)
- **Legacy fallback:** `{exp_output_dir}/` (root level)

**Saves to:**
- `{exp_output_dir}/{assembly_name}_BOM_enriched.json`

**File structure:**
```json
{
  "schema_version": 2,
  "timestamp": "2026-02-12T...",
  "datasource_root": "...",
  "parts": [
    { "part_id": "...", "part_name_guess": "...", ... },
    ...
  ],
  "total_parts": N,
  "source": "instance_aware_enrichment" | "monopart_enrichment",
  "instance_aware": true | false
}
```

**Returns to state:**
- `merged_bom_path` - Path to generated BOM file

---

### 7. **generate_assembly_sequence**

**Purpose:** Generate assembly sequence using LLM (per-step generation with iteration support).

**Inputs (from state):**
- `assembly_name` - Assembly name
- `assembly_dir` - Full path to assembly (from stepparser output)
- `enable_assembly_sequence` - Boolean (default: `True`). Skip if `False`
- `sequence_run_counter` - Current iteration (starts at 0)

**Loads from:**
- **Stepparser data:** `data/processed/stepparser/{assembly_name}/assembly_{assembly_name}/` or `{assembly_name}.STEP/`
  - CAD geometry, part relationships, etc.
- **BOM:** `{exp_output_dir}/{assembly_name}_BOM_enriched.json`
- **Remarks (for feedback loop):** `{exp_output_dir}/assembly_sequence_run{N}/remarks.json` (from previous iteration)
- **Settings:** `configs/prompts.yaml`, experiment settings

**Saves to:**
- `{exp_output_dir}/assembly_sequence_run{N}/` (iteration subfolder)
  - `assembly_sequence.json` - Generated sequence
  - Other intermediate files

**File structure (assembly_sequence.json):**
```json
{
  "assembly_name": "...",
  "steps": [
    {
      "step_number": 1,
      "step_description": "...",
      "parts_involved": [...],
      ...
    },
    ...
  ]
}
```

**Returns to state:**
- `assembly_sequence_path` - Path to `assembly_sequence.json`
- `assembly_sequence_data` - Parsed JSON dict
- `sequence_run_counter` - Incremented to `N`
- `current_sequence_run_dir` - `{exp_output_dir}/assembly_sequence_run{N}/`
- `sequence_max_iterations` - Max iterations (from settings)
- `previous_remarks_context` - Remarks from previous iteration (or `None` for run 1)

---

### 8. **render_assembly_steps**

**Purpose:** Create visual renderings of assembly steps (incremental 3D visualizations).

**Inputs (from state):**
- `assembly_name` - Assembly name
- `assembly_sequence_path` - Path to `assembly_sequence.json`
- `current_sequence_run_dir` - Iteration directory
- `enable_sequence_validation` - Must be `True` (render only if validation runs)

**Loads from:**
- **Sequence:** `{current_sequence_run_dir}/assembly_sequence.json`
- **Geometry:** Stepparser data (STEP file from `data/input/ALL/`)
- **Settings:** `ASV_transparency_values` (list of transparency levels, e.g., `[0.0, 0.3]`), `headless_mode`

**Saves to:**
- `{current_sequence_run_dir}/sequence_renderings/` (flat, all files in one folder)

**File naming convention:** `step_{id:02d}_{view}{transp_suffix}[_entropy_{X}_{YZ}].png`

| View type | Filename example |
|-----------|------------------|
| ISO view | `step_03_iso1_transp_0_0.png` |
| Explosion view | `step_03_iso1_exp_transp_0_0.png` |
| Section XY – before | `step_03_section_xy_before_transp_0_0_entropy_4_54.png` |
| Section XY – after | `step_03_section_xy_after_transp_0_0_entropy_4_54.png` |
| Section XZ – before/after | `step_03_section_xz_{state}_transp_0_0_entropy_X_XX.png` |
| Section YZ – before/after | `step_03_section_yz_{state}_transp_0_0_entropy_X_XX.png` |

**Notes:**
- ISO and explosion views render for all configured transparency values
- Section views render only at `transparency=0.0` (opaque)
- Section view filenames embed the Shannon entropy of the image (`entropy_X_XX`)
- Each step renders 2 ISO views × transparencies + 2 explosion views + up to 6 section views (3 planes × before/after)
- Section views are **currently enabled** – disable by commenting out the `=== SECTION VIEWS ===` block in `Assembly_sequence_validation.py:render_assembly_steps()`

**Returns to state:**
- `assembly_renderings_path` - Path to `sequence_renderings/` folder
- `last_rendered_run_counter` - Marks iteration as rendered (skips re-render if run again)

---

### 9. **interaction_analysis** ✅ NEW (23.02.2026)

**Purpose:** Analyze geometric interactions between assembly parts per step (contact surfaces, alignment challenges, collision risks). Assembly step context automatically injected.

**Inputs (from state):**
- `assembly_name` - Assembly name
- `assembly_sequence_path` - Path to `assembly_sequence.json`
- `assembly_renderings_path` - Path to `sequence_renderings/` folder
- `current_sequence_run_dir` - Iteration directory
- `IA_mode` - "disabled", "enabled", or "validate_only" (from settings, default: "enabled")
- `joining_process` - Assembly step joining information (auto-passed to IA)
- `belongs_to` - Assembly context (auto-passed to IA)

**Loads from:**
- **Sequence:** `{current_sequence_run_dir}/assembly_sequence.json`
- **Step Renderings:** `{current_sequence_run_dir}/sequence_renderings/`
- **Part Metadata:** `{exp_output_dir}/{assembly_name}_BOM_enriched.json`
- **Monopart Renderings:** `data/processed/stepparser/{assembly_name}/` (optional)
- **Settings:** IA_mode, IA_*_prompt_id, IA_*_img_keywords, IA_*_json_keys

**Saves to:**
- `{current_sequence_run_dir}/interaction_analysis.json` - Complete interaction analysis
- Also copied to checkpoint: `data/checkpoints/{timestamp}/{assembly_name}/interaction_analysis.json`

**Output Structure (interaction_analysis.json):**
```json
{
  "analysis_metadata": {
    "assembly_name": "IPA_Reducer_Case",
    "analysis_timestamp": "2026-02-24T...",
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
        "accuracy_of_target_position": "Medium precision (±0.5mm) needed for bore concentricity",
        "positioning_aids": "Cylindrical shaft centers bearing; shoulder provides axial reference",
        "additional_orientation_by_rotation": "Bearing has rotational symmetry; free to rotate",
        "accessibility_to_joining_position": "Full access from assembly top; manual/automated insertion",
        "joining_motion": "Linear axial insertion along shaft center; ~50mm insertion depth",
        "joining_tolerances": "Tight H7/n6 fit required for load transmission",
        "stability_in_positioned_state": "Bearing axially stable once seated; shoulder prevents removal",
        "feeding_of_joining_element": "Manual/automated bearing feed to shaft position; pre-alignment not needed",
        "fixing_of_mounted_part": "Press-fit creates mechanical lock; no additional fasteners needed"
      }
    },
    ...
  ],
  "summary": {
    "total_steps_analyzed": 2,
    "average_confidence": 0.90
  }
}
    "warnings_count": 1,
    "average_confidence": 0.90
  }
}
```

**Returns to state:**
- `interaction_analysis_path` - Path to `interaction_analysis.json`
- `interaction_analysis_data` - Full analysis dict (for optional FFA integration)

**Note:** Interaction analysis data is preserved in state and checkpoints for optional use by FFA node via `FFA_include_interaction_analysis` flag.

---

### 10. **validate_assembly_sequence**

**Purpose:** Validate assembly sequence using LLM (per-step validation with retry loop).

**Inputs (from state):**
- `assembly_name` - Assembly name
- `assembly_sequence_path` - Path to `assembly_sequence.json`
- `assembly_renderings_path` - Path to `sequence_renderings/` folder
- `current_sequence_run_dir` - Iteration directory
- `interaction_analysis_data` - Optional interaction analysis context (preserved from node 9)
- `ASV_mode` - "disabled", "generate_only", "validate_only", or "default" (from settings)
- `sequence_run_counter` - Current iteration
- `sequence_max_iterations` - Max allowed iterations

**Loads from:**
- **Sequence:** `{current_sequence_run_dir}/assembly_sequence.json`
- **Renderings:** `{current_sequence_run_dir}/sequence_renderings/`
- **BOM:** `{exp_output_dir}/{assembly_name}_BOM_enriched.json`
- **Settings:** Validation prompts, image keywords, part JSON keys

**Saves to:**
- `{current_sequence_run_dir}/assembly_sequence_validation/`
  - `assembly_sequence_validation_merged.json` - Validation results
  - Other validation artifacts
- `{current_sequence_run_dir}/remarks.json` - Feedback for next iteration (if regeneration needed)

**File structure (remarks.json):**
```json
{
  "overall_valid": true | false,
  "all_parts_processed": true | false,
  "missing_parts": [...],
  "summary": {...},
  "steps": [
    {
      "step_number": 1,
      "is_valid": true | false,
      "remarks": "...",
      "geometric_issues": [...],
      "suggested_improvements": [...],
      "risk_level": "LOW" | "MEDIUM" | "HIGH"
    },
    ...
  ]
}
```

**Conditional Edge Logic:**
- If `overall_valid == True` AND `all_parts_processed == True`: → Go to **assess_ffa** (node 11)
- If `needs_regeneration == True` AND `current_run < max_iterations`: → **Retry** back to **generate_assembly_sequence** (node 7)
- If `current_run >= max_iterations`: → Go to **assess_ffa** (exhausted retries)

**Returns to state:**
- `assembly_sequence_validation_path` - Path to validation output directory
- `assembly_sequence_validation_result` - Full validation result dict
- `last_validation_overall_valid` - Boolean
- `last_validation_all_parts_processed` - Boolean
- `latest_remarks_path` - Path to `remarks.json`
- `sequence_needs_regeneration` - Boolean (should retry?)
- `sequence_iterations_exhausted` - Boolean (max iterations reached?)
- `last_validated_run_counter` - Current iteration number

---

### 11. **assess_ffa**

**Purpose:** Assess assembly steps for Fitness for Automation (FFA) criteria with optional interaction context.


**Inputs (from state):**
- `assembly_name` - Assembly name
- `assembly_sequence_path` - Path to `assembly_sequence.json`
- `assembly_renderings_path` - Path to `sequence_renderings/` folder
- `current_sequence_run_dir` - Iteration directory (for sequence/renderings)
- `FFA_mode` - "disabled", "validate_only", or "default" (from settings)

**Loads from:**
- **Sequence:** `{current_sequence_run_dir}/assembly_sequence.json` (from last validated iteration)
- **Renderings:** `{current_sequence_run_dir}/sequence_renderings/`
- **BOM:** `{exp_output_dir}/{assembly_name}_BOM_enriched.json`
- **Enriched parts:** `{exp_output_dir}/enriched_parts/` (for detailed metadata)
- **Settings:** FFA prompts, image keywords, part JSON keys, image downscale factor

**Saves to:**
- `{exp_output_dir}/ffa_assessment/`
  - `ffa_assessment.json` - FFA assessment results
  - Other FFA artifacts

**File structure (ffa_assessment.json):**
```json
{
  "assembly_name": "...",
  "timestamp": "...",
  "total_steps": N,
  "assessed_steps": N,
  "steps": [
    {
      "step_number": 1,
      "ffa_score": 0.0-100.0,
      "ffa_rating": "LOW" | "MEDIUM" | "HIGH",
      "criteria": {
        "part_access": "...",
        "tool_accessibility": "...",
        ...
      },
      "automation_recommendation": "...",
      ...
    },
    ...
  ]
}
```

**Returns to state:**
- `ffa_assessment_path` - Path to FFA output directory
- `ffa_assessment_result` - Full assessment result dict

---

## Directory Structure Summary

### Input Directories

| Node | Input | Path |
|------|-------|------|
| resolve_paths | Assembly/parts | `datasource_root/` |
| run_assembly | Images/metadata | `{datasource_root}/Assembly/` |
| run_monoparts | Images/metadata | `{datasource_root}/Part_1/`, `Part_2/`, ... |
| generate_assembly_sequence | CAD data | `data/processed/stepparser/{assembly_name}/` |
| generate_assembly_sequence | Previous remarks | `{exp_output_dir}/assembly_sequence_run{N-1}/remarks.json` |
| validate_assembly_sequence | Sequence + images | `{exp_output_dir}/assembly_sequence_run{N}/` |
| assess_ffa | All data | BOM + enriched parts + sequence + renderings |

### Output Directories

| Node | Output | Path |
|------|--------|------|
| merge_copy_part_data | Enriched parts | `{exp_output_dir}/enriched_parts/*_Data_enriched_merged.json` |
| merge_bom | BOM | `{exp_output_dir}/{assembly_name}_BOM_enriched.json` |
| generate_assembly_sequence | Sequence | `{exp_output_dir}/assembly_sequence_run{N}/assembly_sequence.json` |
| render_assembly_steps | Renderings | `{exp_output_dir}/assembly_sequence_run{N}/sequence_renderings/` |
| interaction_analysis | Interaction data | `{exp_output_dir}/assembly_sequence_run{N}/interaction_analysis.json` |
| validate_assembly_sequence | Validation | `{exp_output_dir}/assembly_sequence_run{N}/assembly_sequence_validation/` |
| validate_assembly_sequence | Remarks | `{exp_output_dir}/assembly_sequence_run{N}/remarks.json` |
| assess_ffa | FFA assessment | `{exp_output_dir}/ffa_assessment/ffa_assessment.json` |

### Key State Variables

**Core:**
- `run_id` - Unique execution ID
- `datasource_root` - Input directory
- `assembly_name` - Name (e.g., "assembly_1")
- `experiment_name` - Experiment label

**Paths:**
- `assembly_dir`, `part_dirs`
- `assembly_sequence_path`, `assembly_renderings_path`
- `merged_bom_path`, `ffa_assessment_path`

**Results (large):**
- `assembly_result`, `part_results`
- `assembly_sequence_data`, `assembly_sequence_validation_result`
- `ffa_assessment_result`

**Iteration tracking:**
- `sequence_run_counter` - Current iteration (1, 2, 3, ...)
- `sequence_max_iterations` - Max retries
- `sequence_needs_regeneration` - Should retry?
- `sequence_iterations_exhausted` - Max reached?

---

## Experiment Output Directory

Set via environment variable: `APA_EXPERIMENT_OUTPUT_DIR`

Typical structure:
```
data/experiments/debug_ASG_20260120_151649/
├── enriched_parts/
│   ├── part_1_Data_enriched_merged.json
│   ├── part_2_Data_enriched_merged.json
│   └── ...
├── assembly_1_BOM_enriched.json
├── assembly_sequence_run1/
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   ├── iso1_transp_0_0/
│   │   │   ├── step_1.png
│   │   │   ├── step_2.png
│   │   │   └── ...
│   │   ├── iso1_transp_0_3/
│   │   │   └── ...
│   │   └── ...
│   ├── assembly_sequence_validation/
│   │   └── assembly_sequence_validation_merged.json
│   └── remarks.json
├── assembly_sequence_run2/
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   ├── assembly_sequence_validation/
│   └── remarks.json
└── ffa_assessment/
    └── ffa_assessment.json
```

---

## Settings File References

Settings loaded from: `configs/prompts.yaml` + experiment YAML overrides

**Important settings:**
- `use_unique_parts` - Partition unique vs all parts
- `ASG_image_keywords`, `ASG_json_keywords` - Sequence generation
- `ASV_transparency_values` - Rendering transparency levels (e.g., `[0.0, 0.3, 0.5]`)
- `ASV_mode` - "disabled", "generate_only", "validate_only", "default"
- `ASV_max_iterations` - Max sequence generation retries (default: 3)
- `FFA_mode` - FFA assessment mode
- `image_downscale_factor` - Global image downscaling (0.0-1.0)
- `workflow_print` - Verbose logging

---

## Next Steps for New Workflows

Based on this structure, you can create:

1. **`run_up_to_render_assy_steps`**: Nodes 1-8
   - Stops after rendering assembly steps
   - Saves all intermediate data for later reuse
   - Useful for: experimenting with sequence generation + rendering without validation overhead

2. **`run_assess_ffa_only`**: Node 10 only
   - Input: Pre-existing sequence + renderings + BOM
   - Output: FFA assessment
   - Useful for: varying FFA settings/prompts without regenerating sequences
   - Key insight: Load sequence/renderings/BOM from disk instead of computing them

Both workflows will reuse the same state dictionary structure for consistency.

---

# Data Folder Structure

## Overview

The `data/` folder is organized into 4 main directories:

```
data/
├── experiments/       ← Workflow outputs (main results)
├── ground_truth/      ← Ground truth f data for evaluation
├── input/             ← Raw input STEP files + datasets
└── processed/         ← Pre-processed stepparser CAD data
```

---

## 1. data/experiments/

**Purpose:** Contains all workflow execution results organized by run timestamp.

### Directory naming conventions:

- **`debug_ASG_YYYYMMDD_HHMMSS`** - Debug runs (ASG = Assembly Sequence Generation)
- **`run_YYYY-MM-DD_HHMMSS`** - Production runs
- **`direct_run/`** - Single direct execution (overwrites on each run)
- **`exp1_baseline/`, `exp2/`** - Named experiment outputs
- **`Debug_data_worm_reducer/`** - Specific assembly debug folder
- **`experiments_summary.json`** - Aggregated results metadata

### Inside each run folder (e.g., `run_2026-02-10_154526/`):

```
run_2026-02-10_154526/
├── enriched_parts/
│   ├── part_1_Data_enriched_merged.json    ← From node 5 (merge_copy_part_data)
│   ├── part_2_Data_enriched_merged.json
│   └── ...
├── {assembly_name}_BOM_enriched.json       ← From node 6 (merge_bom)
├── assembly_sequence_run1/                 ← Iteration 1
│   ├── assembly_sequence.json              ← From node 7
│   ├── sequence_renderings/                ← From node 8
│   │   ├── iso1_transp_0_0/
│   │   │   ├── step_1.png
│   │   │   ├── step_2.png
│   │   │   └── ...
│   │   ├── iso1_transp_0_3/
│   │   │   └── (same steps, different transparency)
│   │   └── ...
│   ├── assembly_sequence_validation/       ← From node 9
│   │   └── assembly_sequence_validation_merged.json
│   └── remarks.json                        ← From node 9 (feedback for next iteration)
├── assembly_sequence_run2/                 ← Iteration 2 (if retry happened)
│   └── (same structure as run1)
└── ffa_assessment/                         ← From node 10 (assess_ffa)
    ├── ffa_assessment.json
    └── (other FFA artifacts)
```

### Key files in run output:

| File | Purpose | Created by | Usage |
|------|---------|-----------|-------|
| `enriched_parts/*.json` | Part enrichment (monopart LLM + stepparser metadata) | Node 5 | Input to Node 6 (BOM), Node 10 (FFA) |
| `*_BOM_enriched.json` | Bill of Materials combining all parts | Node 6 | Input to Nodes 7, 9, 10 |
| `assembly_sequence.json` | Generated assembly sequence with steps | Node 7 | Input to Nodes 8, 9, 10 |
| `sequence_renderings/*.png` | Step-by-step 3D visualizations | Node 8 | Input to Node 9, 10 |
| `assembly_sequence_validation_merged.json` | Validation results + per-step remarks | Node 9 | Feedback for retry loop |
| `remarks.json` | Structured feedback for regeneration | Node 9 | Input to next iteration of Node 7 |
| `ffa_assessment.json` | FFA scores + automation recommendations | Node 10 | Final output |

---

## 2. data/ground_truth/

**Purpose:** Ground truth data for evaluation/validation purposes.

### Contents:

```
ground_truth/
├── Connecting_Rod_ffa_assessment_enum_gt.json
├── IPA_Cranfield_ffa_assessment_enum_gt.json
├── Simple gear keychain_ffa_assessment_enum_gt.json
├── Simple_Valve_ffa_assessment_enum_gt.json
├── Stehlager_Sicherungsring_ffa_assessment_enum_gt.json
├── worm gear demonstrator_ffa_assessment_enum_gt.json
└── ffa_enum_mapping.json
```

**Usage:** 
- Ground truth FFA enum values for validation
- `ffa_enum_mapping.json` - Maps between enum names and numeric values
- Used in `/evaluation/` module for FFA assessment evaluation

---

## 3. data/input/

**Purpose:** Raw input datasets and STEP files.

### Structure:

```
input/
├── ALL/                    ← All 41 STEP assembly files
│   ├── Connecting_Rod.STEP
│   ├── IPA_Cranfield.STEP
│   ├── Simple_Valve.STEP
│   ├── worm gear demonstrator.STEP
│   ├── Gearbox.STEP
│   ├── (37 more assemblies...)
│   └── ...
├── Dataset1/               ← Dataset partition 1
├── Dataset2/               ← Dataset partition 2
├── STEP/                   ← Additional STEP files
└── Textbased_Data/         ← Text-based assembly descriptions
```

**Usage:**
- Input to Stepparser (extracts geometry, BOM, part relationships)
- Each assembly can be passed as `datasource_root` to `run_all_nodes`
- Example: `data/input/ALL/Connecting_Rod.STEP` → process with `run_all_nodes(datasource_root="data/input/ALL/")`

---

## 4. data/processed/

**Purpose:** Pre-processed CAD data from Stepparser (OCC/STEP parsing).

### Structure:

```
processed/
├── stepparser/              ← Main processed output
│   ├── Connecting_Rod/
│   ├── IPA_Cranfield/
│   ├── Simple_Valve/
│   ├── Simple gear keychain/
│   ├── Stehlager_Sicherungsring/
│   ├── worm gear demonstrator/
│   └── (6 assemblies with detailed step parsing)
├── stepparser_archive/      ← Older/backup stepparser runs
├── Dataset2/                ← Pre-processed dataset 2
└── File preparation/        ← Data prep utilities
```

### Inside each assembly folder (e.g., `Connecting_Rod/`):

```
Connecting_Rod/
├── assembly_Connecting_Rod/           ← Assembly-level data
│   ├── Connecting_Rod.STEP-iso1_transp_0_0.png    ← 3D renderings (different viewpoints & transparency)
│   ├── Connecting_Rod.STEP-iso1_transp_0_3.png
│   ├── Connecting_Rod.STEP-iso2_transp_0_0.png
│   ├── Connecting_Rod.STEP-iso2_transp_0_3.png
│   ├── Connecting_Rod_BOM.csv         ← Bill of materials (CSV format)
│   ├── Connecting_Rod_BOM.json        ← Bill of materials (JSON format)
│   └── Connecting_Rod_Overview_Stepparser.json    ← Assembly metadata from stepparser
│
├── part_001/                          ← Individual part data (one folder per part)
│   ├── part_001-highlighted-in-assy-isometric.png     ← Part highlighted in assembly
│   ├── part_001-iso1_transp_0_0.png                   ← Part-specific 3D renderings
│   ├── part_001-iso1_transp_0_3.png
│   ├── part_001-iso2_transp_0_0.png
│   ├── part_001-iso2_transp_0_3.png
│   └── part_001_Data_stepparser.json                  ← Part metadata from stepparser
│
├── part_002/                          ← (same structure as part_001)
├── part_003/
├── part_004/
└── part_005/
```

### Image naming convention:

Images use a pattern: `{name}-{viewpoint}_transp_{opacity}.png`

- **Viewpoints:** 
  - `iso1` - Isometric view 1
  - `iso2` - Isometric view 2
  - `exp_` prefix - Exploded view variant

- **Transparency:** 
  - `0_0` - Fully opaque (opacity 0.0)
  - `0_3` - 30% transparent (opacity 0.3)
  - `0_5` - 50% transparent (opacity 0.5)

### Key JSON files:

| File | Purpose | Structure |
|------|---------|-----------|
| `*_Overview_Stepparser.json` | Assembly-level metadata | Assembly name, part count, BOM structure |
| `part_XXX_Data_stepparser.json` | Part-level metadata | Part ID, name, geometry info, relationships |
| `*_BOM.json` | Bill of materials | Parts list with IDs, names, quantities |
| `*_BOM.csv` | Bill of materials (tabular) | Spreadsheet-compatible format |

### Data flow into run_all_nodes:

```
Stepparser Output (processed/)
    ↓
node 7 (generate_assembly_sequence):
  - Reads CAD geometry from assembly_Connecting_Rod/
  - Reads part metadata from part_*/
  - Uses images for understanding geometry
    ↓
node 8 (render_assembly_steps):
  - Uses existing renderings (iso1_transp_0_3, etc.) as reference
  - Renders new step-specific images to sequence_renderings/
    ↓
node 10 (assess_ffa):
  - Uses rendered steps from node 8
  - Uses BOM info from processed/
  - Uses enriched part data from workflow output
```

---

## Data Directory Relationships

### Read flow (Where data comes FROM):

```
input/ALL/ (STEP files)
    ↓ (processed by Stepparser separately)
    ↓
processed/stepparser/ (CAD geometry + metadata)
    ├→ Loaded by node 7 (generate_assembly_sequence)
    ├→ Used by node 8 (render_assembly_steps)
    └→ Used by node 10 (assess_ffa)

ground_truth/ (FFA GT values)
    └→ Used by evaluation/ module for validation
```

### Write flow (Where data goes TO):

```
run_all_nodes workflow
    ├→ experiments/{run_id}/ (all workflow outputs)
    │   ├→ enriched_parts/ (node 5)
    │   ├→ *_BOM_enriched.json (node 6)
    │   ├→ assembly_sequence_run*/ (nodes 7-9, with iteration support)
    │   └→ ffa_assessment/ (node 10)
    │
    └→ evaluation/ffa_evaluation_orchestrator.py
        └→ Processes experiments/{run_id}/ outputs
            ├→ Compares against ground_truth/
            └→ Generates evaluation metrics
```

---

## Summary: Which folder for what?

| Task | Folder | Notes |
|------|--------|-------|
| Run full workflow | Use `datasource_root = "data/input/ALL/"` or specific assembly | Input STEP files |
| Find processed CAD | `data/processed/stepparser/{assembly_name}/` | Pre-parsed geometry, part metadata, images |
| Check workflow output | `data/experiments/run_YYYY-MM-DD_*/` or `direct_run/` | Enriched parts, BOM, sequence, FFA results |
| Validate FFA results | Compare `experiments/*/ffa_assessment.json` against `ground_truth/*_enum_gt.json` | Used by evaluation module |
| Debug sequence generation | Look in `experiments/debug_ASG_*/assembly_sequence_run*/` | Iterative sequence + validation attempts |
| Find 3D renderings | `processed/stepparser/{assembly}/assembly_{name}/` (stepparser) or `experiments/{run}/assembly_sequence_run*/sequence_renderings/` (workflow) | Two sources depending on what you need |



---

## 🔄 FFA-Only Workflow (run_assess_ffa_only)

**Purpose:** Re-run FFA assessment from a checkpoint without re-computing sequences (for sensitivity analysis, parameter tuning).

### Unified Run Structure

Both `run_all_nodes` and `run_assess_ffa_only` use **identical directory structure** for consistency with evaluation:

```
data/experiments/
└── run_YYYY-MM-DD_HHMMSS/           ← Single run directory
    ├── exp1_baseline/               ← Full workflow experiment
    │   ├── Connecting_Rod/
    │   │   ├── assembly_sequence.json
    │   │   ├── sequence_renderings/
    │   │   ├── ffa_assessment/
    │   │   └── ...
    │   ├── IPA_Cranfield/
    │   └── Simple_Valve/
    │
    ├── exp2_other/                  ← Another full workflow experiment
    │   └── assembly/
    │
    └── ffa_only_exp1/               ← FFA-only experiment (NEW)
        ├── Connecting_Rod/
        │   ├── assembly_sequence.json (from ground_truth)
        │   ├── sequence_renderings/ (from ground_truth)
        │   ├── BOM_enriched.json (from checkpoint)
        │   ├── enriched_parts/ (from checkpoint)
        │   └── ffa_assessment/ (NEW OUTPUT)
        ├── IPA_Cranfield/
        └── Simple_Valve/
```

### Key Features

1. **Shared run directory** with full experiments
2. **Checkpoint flexibility**: Can have multiple FFA-only experiments in same run
3. **Ground truth reuse**: Sequences/renderings come from `data/ground_truth/assembly_sequence_ground_truth/`
4. **Evaluation compatible**: Discovery logic finds both full and FFA-only experiments

### CLI Usage

**Single FFA-only experiment:**
```bash
python run_experiments.py --ffa-only \
  --checkpoint-path data/checkpoints/20260214_153000/ \
  --ffa-experiment-name "ffa_only_exp1"
```

**With FFA setting overrides:**
```bash
python run_experiments.py --ffa-only \
  --checkpoint-path data/checkpoints/20260214_153000/ \
  --ffa-experiment-name "ffa_only_exp1_no_images" \
  --ffa-setting-overrides '{"FFA_mode": "disabled"}'
```

**Default experiment name:**
```bash
python run_experiments.py --ffa-only \
  --checkpoint-path data/checkpoints/20260214_153000/
# Creates: data/experiments/run_YYYY-MM-DD_*/ffa_only/
```

### Data Flow

**Input:**
- Checkpoint: `data/checkpoints/{timestamp}/{assembly_name}/`
  - `BOM_enriched.json`
  - `enriched_parts/`
  - `stepparser_renderings/`
  - `metadata.json`

- Ground Truth: `data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/`
  - `sequence.json`
  - `renderings/`

**Output:**
- `data/experiments/run_YYYY-MM-DD_HHMMSS/{experiment_name}/{assembly_name}/ffa_assessment/`
  - `ffa_assessment.json`
  - `ffa_assessment.xlsx`
  - `ffa_assessment.csv`

### Evaluation Integration

FFA-only experiments are automatically discovered and evaluated:

```bash
python evaluation/ffa_evaluation_orchestrator.py data/experiments/run_2026-02-14_153000/
# Processes both exp1_baseline AND ffa_only_exp1
```

Ground truth files from `data/ground_truth/ffa_ground_truth/` are compared against both experiment types.

---

## Evaluation System (NEW)

### Overview

**Macro-Average focused evaluation** for handling class-imbalanced FFA ground truth.

**Problem:** Many FFA fields have heavily imbalanced class distributions (e.g., Class 1: 10 samples, Class 2: 1 sample). Weighted-average metrics obscure poor performance on minority classes. **Solution:** Macro-Average metrics (equal weight per class).

### Structure

```
data/experiments/ffa_experiments/
├── evaluation/                          ← ROOT evaluation output
│   ├── enum_cache/                      ← Converted enum files (internal)
│   │   └── Connecting_Rod_ffa_assessment_enum.json
│   ├── summary.json                     ← Overall metrics
│   ├── macro_f1_comparison.png          ← All experiments F1 comparison
│   ├── assembly_ranking.png             ← Best→Worst assemblies
│   └── FFA_only_tryout_exp1_baseline/   ← Per-experiment folder
│       ├── summary.json
│       └── Connecting_Rod/              ← Per-assembly folder
│           ├── metrics.json
│           ├── confusion_matrix_nature_of_provision.png
│           ├── confusion_matrix_part_rigidity.png
│           ├── ... (one per FFA field)
│           ├── per_class_nature_of_provision.png
│           ├── assembly_summary.png
│           ├── class_distribution_heatmap.png
│           └── step_overview.png
└── FFA_only_tryout_exp2/
    ├── Connecting_Rod/
    │   ├── ffa_assessment/
    │   │   └── Connecting_Rod_ffa_assessment_enum.json
    │   └── ... (assembly files)
    └── ...
```

### Key Files

**1. evaluation/ffa_metrics.py** (285 lines)
- Core metric calculation functions
- Main functions:
  - `load_ffa_data()` - Loads predictions vs GT, handles wrapped/unwrapped formats
  - `extract_field_values()` - Extracts FFA field values (handles flat & nested structures)
  - `calculate_macro_metrics()` - **Primary:** Macro F1, Macro Precision, Macro Recall (± Micro Accuracy, Weighted F1 for reference)
  - `calculate_per_class_metrics()` - Per-class: Precision, Recall, F1, TP/FP/FN (all classes, including missing ones)
  - `calculate_confusion_matrix_data()` - Confusion matrices with all possible labels
  - `evaluate_assembly()` - Evaluates single assembly across 14 FFA fields
  - `evaluate_experiment()` - Evaluates all assemblies in experiment
  - `rank_assemblies()` - Sorts assemblies by macro_f1 (best → worst)
  - `create_class_distribution_analysis()` - Analyzes class imbalance

**2. evaluation/ffa_visualization.py** (350+ lines)
- 7 visualization functions for different analysis perspectives
- Functions:
  - `save_confusion_matrix()` - Heatmap per field per assembly (PNG)
  - `save_per_class_metrics_chart()` - Bar chart (Precision/Recall/F1 per class)
  - `save_assembly_summary_chart()` - All fields for one assembly (color-coded: green >0.7, orange >0.5, red <0.5)
  - `save_class_distribution_heatmap()` - Shows imbalance across fields
  - `save_macro_comparison_chart()` - Compare macro_f1 across experiments
  - `save_assembly_ranking_chart()` - Rank assemblies (red→green gradient)
  - `save_step_overview_chart()` - Step-level metadata

**3. run_ffa_evaluation.py** (NEW - Main Orchestrator)
- Discovers all experiments in `data/experiments/ffa_experiments/`
- For each experiment:
  - Auto-discovers assemblies
  - Loads FFA assessments (enum format)
  - Converts stripped format → enum if needed (saves to `enum_cache/`)
  - Calculates Macro metrics for all 14 FFA fields
  - Creates per-assembly visualizations
- Generates root-level comparison charts
- Outputs nested folder structure with JSON summaries

### Usage

**Run evaluation on all experiments:**
```bash
python run_ffa_evaluation.py
```

**Output:**
- `data/experiments/ffa_experiments/evaluation/` folder structure
- Console output with Macro F1 scores and assembly rankings

### Metrics Explained

**Macro-Average Metrics:**
- **Macro F1:** Average F1 across all classes (unaffected by imbalance)
- **Macro Precision:** Average precision across classes
- **Macro Recall:** Average recall across classes
- **Micro Accuracy:** Overall accuracy (for reference, can be misleading with imbalance)

**Per-Class Metrics:**
- **Precision:** TP / (TP + FP) - Correctness of positive predictions
- **Recall:** TP / (TP + FN) - Coverage of ground truth positives
- **F1:** Harmonic mean of precision & recall
- **Support:** Number of samples in ground truth
- **TP/FP/FN:** True/False positives, False negatives

### 14 FFA Fields Evaluated

```
1. nature_of_provision
2. part_rigidity
3. gripping_areas
4. orientation_features
5. surface_sensibility
6. accuracy_of_target_position
7. positioning_aids
8. additional_orientation_by_rotation
9. accessibility_to_joining_position
10. positioning_motion
11. positioning_tolerances
12. stability_in_positioned_state
13. feeding_of_joining_element
14. fixing_of_mounted_part
```

### File Format Requirements

**Predictions:** `{assembly}_ffa_assessment_enum.json`
- Format: Nested structure with `step_assessments` list
- Each step has `assessment.{category}.{field_name}` = integer (0-5 typically)

**Ground Truth:** `{assembly}_ffa_assessment_enum_gt.json`
- Same structure as predictions
- Located in `data/ground_truth/ffa_ground_truth/`

### Data Processing

1. **Load:** Read predictions & GT JSON files
2. **Extract:** Pull field values from nested structure
3. **Calculate:** Compute macro metrics per field
4. **Aggregate:** Average across all fields for assembly-level F1
5. **Visualize:** Create confusion matrices, bar charts, heatmaps
6. **Report:** Generate JSON summaries & comparison charts


