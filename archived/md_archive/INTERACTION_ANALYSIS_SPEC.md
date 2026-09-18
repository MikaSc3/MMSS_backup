# Interaction Analysis Node - Complete Specification

**Date**: 24. Februar 2026  
**Status**: ✅ FULLY IMPLEMENTED & INTEGRATED (24. Februar 2026)
**Latest**: Structured output schema + Assembly step context + YZ-plane rendering inversion

---

## 🎯 Overview

New workflow node **`interaction_analysis`** for analyzing geometric/spatial interactions between assembly parts.

- **Position in Workflow**: After `render_assembly_steps`, before `validate_assembly_sequence`
- **Purpose**: Per-step geometric interaction analysis (touching surfaces, alignment issues, collision risks)
- **Output Format**: Separate `interaction_analysis.json` file
- **Integration**: Optional input to FFA-Node via `include_interaction_analysis` flag

---

## 📊 Workflow Integration

```
render_assembly_steps
        ↓
interaction_analysis        ✅ IMPLEMENTED
        ↓
validate_assembly_sequence
        ↓
assess_ffa (with optional interaction context) ✅ INTEGRATED
        ↓
END
```

**Implementation Status:**
- ✅ Node function: `agent/Interaction_analysis.py` (570 lines)
- ✅ Workflow integration: `agent/workflow.py` - `_node_interaction_analysis()`
- ✅ Configuration: `configs/default_settings.yaml` + `configs/full_workflow/expX_*.yaml`
- ✅ Checkpoint support: `create_checkpoint_from_run.py` copies `interaction_analysis.json`
- ✅ FFA integration: `agent/FFA_assessment.py` accepts optional interaction context
- ✅ FFA-only support: `run_assess_ffa_only()` loads interaction data from checkpoints
- ✅ Prompts: `configs/prompts.yaml` - System + Task prompts (configurable)
- ✅ User's choice: `Interaction_Analyst_V2` + `Analyse_Interaction_V2` (recommended)
- ✅ Alternative: `interaction_analyst_system_v1` + `interaction_analysis_task_v1` (detailed schema)

---

## � Implementation Details

### Core Node: `agent/Interaction_analysis.py`

**Main Function**: `analyze_assembly_sequence_interactions()`

**Key Helper Functions**:
- `normalize_part_id()` - Remove `_copy*` suffixes for duplicate handling
- `get_step_renderings()` - Load assembly step images with keyword filtering
- `get_monopart_renderings()` - Load individual part images (handles part_003_copy1 mapping)
- `analyze_step_interaction()` - Single-step LLM analysis with GPT-4o Vision

**Workflow Integration**: `agent/workflow.py` → `_node_interaction_analysis()`
- Loads settings from `IA_*` config keys
- Checks `IA_mode` (disabled|enabled|validate_only)
- Saves `interaction_analysis.json` to `assembly_sequence_run{N}/`
- Returns `interaction_analysis_path` + `interaction_analysis_data` to state

### Configuration

**Settings** (in `configs/default_settings.yaml`):
```yaml
IA_system_prompt_id: "Interaction_Analyst_V2"  # Or: "interaction_analyst_system_v1"
IA_human_prompt_id: "Analyse_Interaction_V2"   # Or: "interaction_analysis_task_v1"
IA_sequence_step_img_keywords: ["iso1_transp_0_3"]
IA_monopart_img_keywords: ["iso1_transp_0_0", "iso1_transp_0_3"]
IA_base_part_json_keys: ["part_id", "geometry_features", "mating_or_interface_features"]
IA_joining_part_json_keys: ["part_id", "geometry_features", "mating_or_interface_features"]
IA_include_monopart_renderings: true
IA_mode: "enabled"  # Can be "disabled", "enabled", "validate_only"
FFA_include_interaction_analysis: false  # Optional FFA integration flag
```

### FFA Integration

**In `agent/FFA_assessment.py`:**
- `assess_step_ffa()` now accepts optional `interaction_context` parameter
- Context automatically extracted per step from `interaction_analysis_data` dict
- Appended to FFA prompt under "GEOMETRIC INTERACTION ANALYSIS" section with all 9 categories
- Includes detailed positioning, accessibility, joining motion, tolerances, and stability data
- `assess_assembly_sequence_ffa()` now accepts `interaction_analysis_data` parameter

**Assembly Step Context Integration**:
- `joining_process` and `belongs_to` parameters automatically passed to IA analysis
- Injected as **ASSEMBLY STEP INFORMATION** section in analysis prompt
- Available for all prompt variants (user's custom prompts or default variants)
- Context appears regardless of prompt choice - automatic metadata enhancement

**In Workflow:**
- If `FFA_include_interaction_analysis=true` in settings
- FFA node loads `interaction_analysis_data` from state
- Passes to FFA assessment function
- Full IA context (including assembly step info) included in FFA prompt

**In FFA-Only Mode** (`run_assess_ffa_only()`):
- Loads `interaction_analysis.json` from checkpoint if exists
- Passes to state for FFA node
- Graceful degradation if not present

### Checkpoints

**In `create_checkpoint_from_run.py`:**
- New checkpoint step copies `interaction_analysis.json` from run directory
- Located after `sequence_renderings` copy (lines ~191-206)
- Graceful if file doesn't exist (logged as optional)

### Prompts

**In `configs/prompts.yaml`:**

**System Prompt** - `Interaction_Analyst_V2` (User's recommended):
- Your role: Geometric interaction analysis expert
- Core competencies: Contact surfaces, alignment challenges, collision risks, assembly feasibility
- Methodology: Evidence-based analysis using provided renderings and BOM metadata

**Task Prompt** - `Analyse_Interaction_V2` (User's recommended):
- Analyze the geometric interaction between current base_part and joining_part
- Focus on NEW contact surfaces and spatial relationships (not overall assembly)
- **Assembly Step Information** (auto-injected):
  - joining_process: How parts are joined (e.g., "press-fit", "snap", "screw")
  - belongs_to: Assembly context (e.g., "basic config", "optional module")
- Output format: Structured analysis with 9 detailed categories
- Nine analysis categories: (see below -Structured Output Schema section)

**Alternative System Prompts** - `interaction_analyst_system_v1`:
- Detailed role definition with interaction modality examples
- Explicit competency list for positioning, accessibility, joining motion, tolerances, stability

**Alternative Task Prompts** - `interaction_analysis_task_v1`:
- Structured task with templated sections for all 9 analysis categories
- Detailed instructions for each category (accuracy, aids, orientation, accessibility, motion, tolerances, stability, feeding, fixing)

---

## �📁 Input Sources

### 1. Assembly Sequence
**Path**: `{exp_output_dir}/{assembly_name}/assembly_sequence_run{N}/assembly_sequence.json`

**Usage**: 
- Extract steps with `base_part`, `joining_part`, `step_id`
- Iterate per step (only "new" interactions, not accumulative)

**Example**:
```json
{
  "steps": [
    {
      "step_id": 1,
      "base_part": "part_001",
      "joining_part": ["part_002"],
      "step_description": "Insert bearing into shaft"
    },
    {
      "step_id": 2,
      "base_part": "part_001",
      "joining_part": ["part_003"],
      "step_description": "Add washer"
    }
  ]
}
```

### 2. Step Renderings (Sequence Renderings)
**Path**: `{exp_output_dir}/{assembly_name}/assembly_sequence_run{N}/sequence_renderings/`

**Files Pattern**: `step_{id}_{view}_{transp}.png`

**Keyword Filtering**: Via config
```yaml
interaction_sequence_step_img_keywords: ["iso1_transp_0_3"]
```

**Usage**: Show current step state (all parts accumulated up to step N)

---

### 3. Monopart Renderings (Optional)
**Path**: `data/processed/stepparser/{assembly_name}/`

**Applies to**: 
- `base_part` (single part)
- `joining_part` (may be list, e.g. ["part_003", "part_003_copy1"])

**Duplicate Handling Rule**:
- If `joining_part` contains ["part_003_copy1", "part_003_copy2"]
  - Use only `part_003_copy1` rendering (first item)
- If contains ["part_003"]
  - Use `part_003` rendering normally
- Alternative: Map copies to base → `part_003_copy1` maps to `part_003` rendering

**Keyword Filtering**: Via config
```yaml
interaction_sequence_monopart_keywords: ["iso1_transp_0_0", "iso1_transp_0_3"]
```

**Usage**: Show individual parts for detailed surface analysis

---

### 4. BOM Metadata
**Path**: `{exp_output_dir}/{assembly_name}/{assembly_name}_BOM_enriched.json`

**Extraction**: Via `extract_json_keys_from_file()` (existing utility)

**Keyword Filtering**: Via config (like FFA-Node)
```yaml
interaction_json_file_keyword: "BOM_enriched"
interaction_base_part_json_keys: ["part_id", "part_name_guess", "geometry_description"]
interaction_joining_part_json_keys: ["part_id", "part_name_guess", "material_word", "geometry_description", "functional_surfaces"]
interaction_part_id_name_list: []  # Empty = all parts
```

---

## 📝 Output Format

### File Location
```
{exp_output_dir}/{assembly_name}/assembly_sequence_run{N}/
├── assembly_sequence.json               (existing)
├── sequence_renderings/                 (existing)
└── interaction_analysis.json            ⭐ NEW
```

### File Structure: `interaction_analysis.json`

```json
{
  "analysis_metadata": {
    "assembly_name": "IPA_Reducer_Case",
    "analysis_timestamp": "2026-02-23T08:16:33Z",
    "node_version": "1.0",
    "config": {
      "system_prompt_id": "Interaction_Analyst_V1",
      "human_prompt_id": "Analyse_Interaction_V1",
      "step_img_keywords": ["iso1_transp_0_3"],
      "monopart_img_keywords": ["iso1_transp_0_0", "iso1_transp_0_3"],
      "include_monopart_renderings": true
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
        "analysis_summary": "Two cylindrical parts with press-fit interface. High contact area, some misalignment risk.",
        
        "geometric_interactions": {
          "contact_surfaces": [
            {
              "surface_type": "cylindrical",
              "primary_part": "part_001",
              "secondary_part": "part_002",
              "estimated_contact_area": "medium",
              "surface_condition": "smooth"
            }
          ],
          
          "alignment_challenges": [
            {
              "type": "radial_offset",
              "affected_parts": ["part_001", "part_002"],
              "severity": "low",
              "description": "Minor radial eccentricity visible in renderings"
            }
          ],
          
          "collision_risks": [
            {
              "risk_type": "edge_contact",
              "parts_involved": ["part_001", "part_002"],
              "probability": "low",
              "mitigation": "Chamfered edges should prevent edge loading"
            }
          ]
        },

        "assembly_feasibility": {
          "overall_assessment": "FEASIBLE",
          "confidence": 0.85,
          "critical_issues": [],
          "warnings": [
            "Alignment tolerance tight - requires precision tooling"
          ],
          "recommendations": [
            "Use fixture to maintain radial alignment during insertion"
          ]
        },

        "analysis_metadata": {
          "images_used": {
            "sequence_renderings": [
              "step_01_iso1_transp_0_3.png"
            ],
            "monopart_renderings": {
              "part_001": ["part_001-iso1_transp_0_0.png"],
              "part_002": ["part_002-iso1_transp_0_0.png", "part_002-iso1_transp_0_3.png"]
            }
          },
          "analysis_tokens_used": 1843,
          "model": "gpt-4o-vision"
        }
      }
    },

    {
      "step_id": 2,
      "belongs_to": "Assembly (basic config)",
      "base_part": "part_001",
      "joining_part": ["part_003"],
      "step_description": "Add washer",

      "interaction_analysis": {
        "analysis_summary": "Flat washer on cylindrical shaft. Simple planar interface.",
        "geometric_interactions": {
          "contact_surfaces": [
            {
              "surface_type": "planar_to_cylindrical",
              "primary_part": "part_003",
              "secondary_part": "part_001",
              "estimated_contact_area": "small",
              "surface_condition": "smooth"
            }
          ],
          "alignment_challenges": [],
          "collision_risks": []
        },
        "assembly_feasibility": {
          "overall_assessment": "FEASIBLE",
          "confidence": 0.95,
          "critical_issues": [],
          "warnings": [],
          "recommendations": []
        },
        "analysis_metadata": {
          "images_used": {
            "sequence_renderings": [
              "step_02_iso1_transp_0_3.png"
            ],
            "monopart_renderings": {
              "part_001": ["part_001-iso1_transp_0_0.png"],
              "part_003": ["part_003-iso1_transp_0_0.png"]
            }
          },
          "analysis_tokens_used": 1256,
          "model": "gpt-4o-vision"
        }
      }
    }
  ],

  "summary": {
    "total_steps_analyzed": 2,
    "feasible_interactions": 2,
    "critical_issues_found": 0,
    "warnings_count": 1,
    "average_confidence": 0.90
  }
}
```

---

## 🤖 Prompting Strategy

### System Prompt: `Interaction_Analyst_V1`
**Definition Location**: `configs/prompts.yaml` (User to define)

**Expected Focus**:
- Geometric surface interactions
- Alignment challenges
- Collision/interference detection
- Assembly feasibility from spatial perspective
- Material contact implications

### Human Prompt: `Analyse_Interaction_V1`
**Definition Location**: `configs/prompts.yaml` (User to define)

**Should Include**:
- Current step description (base_part + joining_part)
- **Instruction for NEW interactions only**: 
  > "Analyze the geometric interaction between {base_part} and {joining_part} being added in this step. Focus on NEW contact surfaces and spatial relationships, not the overall assembly."

- BOM metadata (selectively via `interaction_*_json_keys`)
- Step rendering images
- Monopart renderings (optional, if available)

**Output Structure**: Structured/semi-structured response:
```
ANALYSIS_SUMMARY: [one-liner]
CONTACT_SURFACES: [list with details]
ALIGNMENT_CHALLENGES: [list]
COLLISION_RISKS: [list]
ASSEMBLY_FEASIBILITY: [FEASIBLE|RISKY|INFEASIBLE + confidence 0-100]
RECOMMENDATIONS: [list of suggestions]
```

---

## 📋 Structured Output Schema & Validation

**Location**: `agent/structured_output.py` - `InteractionAnalysisDetailed` model

**Validation Method**: Pydantic v2 with `llm.with_structured_output(InteractionAnalysisDetailed, include_raw=True)`
- LLM responses validated at output level (not manual parsing)
- Enforces all 9 required fields from schema
- Graceful fallback to manual JSON parsing for backward compatibility with older LangChain versions

**Nine Analysis Categories** (Pydantic BaseModel fields):

1. **accuracy_of_target_position** (str)
   - Precision requirements and achievability for joining position
   - Example: "Medium precision (±0.5mm) needed for bearing bore concentricity"

2. **positioning_aids** (str)
   - Guides, fixtures, or geometric features helping correct placement
   - Example: "Cylindrical shaft acts as self-centering guide; shoulder provides axial reference"

3. **additional_orientation_by_rotation** (str)
   - Ability to rotate/reorient during insertion
   - Values: flexible/constrained/fixed rotation

4. **accessibility_to_joining_position** (str)
   - Physical access for assembly operation
   - Values: full/partial/restricted access

5. **joining_motion** (str)
   - Movement types required during joining
   - Example: "Linear axial insertion along shaft center; ~50mm insertion depth"

6. **joining_tolerances** (str)
   - Tolerance stack analysis and fitting tightness
   - Values: loose/nominal/tight fit

7. **stability_in_positioned_state** (str)
   - Part stability after joining before final fixation
   - Example: "Bearing axially stable once seated; shoulder prevents removal"

8. **feeding_of_joining_element** (str)
   - How joining element is supplied to assembly position
   - Values: manual/automated/pre-positioned

9. **fixing_of_mounted_part** (str)
   - Methods to fix part after joining
   - Example: "Press-fit creates mechanical lock; no additional fasteners needed"

**FFA Integration**:
- All 9 categories formatted into human-readable context section
- Included in FFA prompt under "GEOMETRIC INTERACTION ANALYSIS" heading
- Available for downstream FFA assessment regardless of IA prompt choice
- Assembly step information (joining_process, belongs_to) automatically injected as context

---

## ⚙️ Configuration (configs/default_settings.yaml)

### New Settings

```yaml
# ========================================================================
# Interaction Analysis (IA) - Geometric interaction analysis
# ========================================================================

IA_system_prompt_id: "Interaction_Analyst_V2"  # System prompt (user's choice)
IA_human_prompt_id: "Analyse_Interaction_V2"   # Human/task prompt (user's choice)

# Interaction Analysis - Image settings
IA_sequence_step_img_keywords: ["iso1_transp_0_3"]  # Step renderings (current assembly state)
IA_monopart_img_keywords: ["iso1_transp_0_0", "iso1_transp_0_3"]  # Individual part renderings

# Interaction Analysis - JSON/BOM settings
IA_json_file_keyword: "BOM_enriched"  # File to load for metadata
IA_base_part_json_keys: ["part_id", "part_name_guess", "geometry_description", "part_is_touching"]
IA_joining_part_json_keys: ["part_id", "part_name_guess", "material_word", "geometry_description", "functional_surfaces", "part_is_touching"]
IA_part_id_name_list: []  # Empty = all parts, or specific list

# Interaction Analysis - Processing
IA_include_monopart_renderings: true  # Load individual part images for base + joining parts
IA_monopart_duplicate_handling: "first"  # "first" = use first copy (e.g., part_003_copy1), "base" = map to base part (part_003)
IA_max_completion_tokens: 3000  # LLM output token limit per step
IA_mode: "enabled"  # "disabled", "enabled", "validate_only"

# Image downscaling (shared with global setting)
# Use global image_downscale_factor (defined at top of file)
```

### Experiment Override Example

```yaml
# In configs/experiments/expX_most_info.yaml

IA_system_prompt_id: "Interaction_Analyst_V2"  # User's recommended prompts
IA_human_prompt_id: "Analyse_Interaction_V2"   # Or use alternative variants (V1, system_v1, task_v1)
IA_sequence_step_img_keywords: ["iso1_transp_0_3"]
IA_monopart_img_keywords: ["iso1_transp_0_0", "iso1_transp_0_3"]
IA_mode: "enabled"  # Can be overridden per experiment
```

---

## 🔄 FFA-Node Integration

### Flag: `include_interaction_analysis`

**In default_settings.yaml**:
```yaml
FFA_include_interaction_analysis: false  # Default: don't include

# If true, append interaction analysis to FFA step prompt at end
# Gives FFA-Node additional context about part interactions
```

**In experiment override**:
```yaml
FFA_include_interaction_analysis: true  # Enable for this experiment
```

### Implementation in FFA-Node

When building FFA step prompt:
```python
# Step 1: Build normal FFA prompt (existing code)
ffa_prompt = build_normal_ffa_prompt(...)

# Step 2: Optionally append interaction analysis
if include_interaction_analysis and interaction_analysis_available:
    step_interaction = load_step_interaction(step_id)
    ffa_prompt += f"""

---
GEOMETRIC INTERACTION CONTEXT:
{step_interaction['analysis_summary']}

Contact Surfaces: {step_interaction['geometric_interactions']['contact_surfaces']}
Alignment Challenges: {step_interaction['geometric_interactions']['alignment_challenges']}
Assembly Feasibility: {step_interaction['assembly_feasibility']['overall_assessment']}
"""

# Step 3: Send to LLM (existing code)
```

---

## 🛠️ Implementation Checklist

- [ ] Create node function: `interaction_analysis()` in `agent/Assembly_sequence_validation.py` (or new file)
- [ ] Load assembly_sequence.json per step
- [ ] Load step renderings (sequence_renderings/)
- [ ] Load monopart renderings (stepparser/) with duplicate handling
- [ ] Load BOM metadata via `extract_json_keys_from_file()`
- [ ] Build image list (sequence + monopart)
- [ ] Call LLM with system/human prompts
- [ ] Parse LLM response into JSON structure
- [ ] Save as `interaction_analysis.json`
- [ ] Add to workflow.py as node (before validate_assembly_sequence)
- [ ] Add state variables: `interaction_analysis_path`, `interaction_analysis_data`
- [ ] Update `create_checkpoint_from_run()` to copy interaction_analysis.json
- [ ] Update `run_ffa_only_experiments.py` to load interaction_analysis.json
- [ ] Add config settings to `configs/default_settings.yaml`
- [ ] Add to FFA-Node: optional append to FFA prompt (if flag enabled)

---

## 📋 State Variables

### Input to Node
```python
state = {
    "assembly_name": "IPA_Reducer_Case",
    "current_sequence_run_dir": Path(".../assembly_sequence_run1/"),
    "assembly_sequence_data": {...},  # Loaded from assembly_sequence.json
    "assembly_dir": Path(".../stepparser/IPA_Reducer_Case/"),
    # Settings
    "IA_system_prompt_id": "Interaction_Analyst_V1",
    "IA_human_prompt_id": "Analyse_Interaction_V1",
    ...
}
```

### Output from Node
```python
state = {
    ...existing...,
    "interaction_analysis_path": Path(".../assembly_sequence_run1/interaction_analysis.json"),
    "interaction_analysis_data": {...},  # Parsed JSON dict
    "last_node_execution": "interaction_analysis"
}
```

---

## 🔄 Checkpoint Integration

### create_checkpoint_from_run() Changes

**Current**: Copies `assembly_sequence.json`, `sequence_renderings/`

**Updated**: Also copy `interaction_analysis.json`

```python
def create_checkpoint(...):
    # ...existing code...
    
    # Copy interaction_analysis.json if exists
    interaction_file = run_dir / "interaction_analysis.json"
    if interaction_file.exists():
        shutil.copy(
            interaction_file,
            checkpoint_assembly_dir / "interaction_analysis.json"
        )
        checkpoint_files.append(str(interaction_file.name))
    
    # ...rest of code...
```

### run_ffa_only_experiments.py Changes

**Current**: Loads assembly_sequence.json from checkpoint

**Updated**: Also load interaction_analysis.json if `include_interaction_analysis=True`

```python
def run_ffa_only(...):
    # Load assembly sequence
    sequence_path = checkpoint_dir / "assembly_sequence.json"
    sequence_data = load_json(sequence_path)
    
    # NEW: Load interaction analysis if available
    interaction_path = checkpoint_dir / "interaction_analysis.json"
    interaction_data = None
    if interaction_path.exists():
        interaction_data = load_json(interaction_path)
    
    # Pass to FFA-Node
    state["interaction_analysis_data"] = interaction_data
    result = ffa_assessment_node(state)
```

---

## 🚀 Execution Example

### Full Workflow Run
```
Step 1: render_assembly_steps
  → Creates sequence_renderings/step_01_*.png, step_02_*.png, ...
  ✓ State: assembly_sequence_data, current_sequence_run_dir

Step 2: interaction_analysis  ⭐ NEW
  → Loads assembly_sequence.json
  → For step 1:
     - Render: step_01_iso1_transp_0_3.png
     - Monoparts: part_001-iso1_transp_0_0.png, part_002-iso1_transp_0_0.png
     - BOM: part_001 & part_002 metadata
     - LLM: Analyze interaction
  → For step 2:
     - Render: step_02_iso1_transp_0_3.png
     - Monoparts: part_001, part_003
     - BOM: metadata
     - LLM: Analyze interaction
  → Saves: interaction_analysis.json
  ✓ State: interaction_analysis_data

Step 3: validate_assembly_sequence (unchanged)
  → Optional, may use interaction context

Step 4: assess_ffa
  → If include_interaction_analysis=True:
     Append step interaction to FFA prompt for additional context
  ✓ State: ffa_assessment_data

Step 5: create_checkpoint_from_run
  → Copies: assembly_sequence.json, sequence_renderings/, IA interaction_analysis.json
```

### FFA-Only Run (from Checkpoint)
```
Load checkpoint:
  → assembly_sequence.json
  → interaction_analysis.json (if exists)
  
Run assess_ffa_node:
  → If include_interaction_analysis=True:
     Load interaction_analysis.json from checkpoint
     Append to FFA prompt
```

---

## 🎨 Rendering Fixes

### YZ-Plane Section View Inversion (24. Februar 2026)

**Issue**: YZ-plane section views displayed with incorrect viewing direction

**Root Cause**: Plane normal and camera position not properly inverted for YZ-plane orientation

**Fixes Applied** in `stepparser/rendering/renderer.py`:

**1. Part Section View - YZ-Plane** (Lines 195-200):
- Plane normal changed from `gp_Dir(1, 0, 0)` to `gp_Dir(-1, 0, 0)`
- Camera position calculation: `center[0] - distance` instead of `center[0] + distance`
- Effect: Corrects viewing direction for left-side cross-section views

**2. Assembly Section View - YZ-Plane** (Lines 631-637):
- Cutting box start position inverted to positive X side (`center_x`)
- Camera position: `center_x + diagonal * 1.5` instead of `center_x - diagonal * 1.5`
- Effect: Proper section plane placement and viewing angle for assembly context

**3. Combined Impact**:
- YZ-plane renderings now display parts and assemblies from correct perspective
- Cross-section cuts accurately show internal geometry
- Part orientation matches expected right-hand side views

**Verification**:
- Check rendered PNG images for YZ-plane views
- Verify internal surfaces are visible and properly positioned
- Confirm part relationships in sections match CAD model

---

## 📝 Testing Checklist

- [ ] Can load assembly_sequence.json with multiple steps
- [ ] Images load correctly (sequence + monopart)
- [ ] Duplicate part handling works (copy1/copy2 → use first/base)
- [ ] BOM metadata extracted correctly
- [ ] Assembly step information (joining_process, belongs_to) included in prompt context
- [ ] Structured output validates against InteractionAnalysisDetailed schema
- [ ] All 9 analysis categories populated in LLM response
- [ ] interaction_analysis.json has correct schema
- [ ] Checkpoint correctly copies interaction_analysis.json
- [ ] FFA-Node receives all 9 interaction analysis categories
- [ ] FFA prompt includes GEOMETRIC INTERACTION ANALYSIS section
- [ ] run_ffa_only_experiments handles missing interaction_analysis.json gracefully
- [ ] YZ-plane section views render with correct viewing direction
- [ ] Part and assembly cross-sections show internal geometry properly
- [ ] User's custom IA prompts work with assembly context injection

---

## 📚 References

Similar Implementations:
- **FFA-Node** (`agent/FFA_assessment.py`): Per-step LLM analysis with image/JSON loading
- **Template**: Follow same pattern for image loading, JSON extraction, LLM calling, result saving
- **Checkpoint System** (`create_checkpoint_from_run.py`): Already copies sequence_renderings/

