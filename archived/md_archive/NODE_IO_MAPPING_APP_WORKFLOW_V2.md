# Node Input/Output Mapping - app_workflow_v2

Complete documentation of what data each node produces and where agents access it.

---

## PHASE 1: Preprocessing + Stepparser

### Node: `_node_resolve_paths`

| Property | Value |
|----------|-------|
| **Phase** | 1 (Preprocessing) |
| **Input** | `preprocessing/stepparser/{assembly_name}/` (from stepparser) |
| **Output** | `resolved_paths.json` |
| **Location** | `session_root/` |
| **Description** | Maps all file paths from stepparser output to structured JSON |

**Output Structure**:
```json
{
  "assembly_parent_dir": "...",
  "assembly_dir": "preprocessing/stepparser/{assembly_name}/assembly_{assembly_name}/",
  "bom_json_path": "...",
  "assembly_metadata_path": "...",
  "part_dirs": ["Part_1", "Part_2", ...],
  "unique_part_dirs": [...]
}
```

**Used By**: Phase 2a nodes (all assembly analysis nodes read this)

---

### Node: `_node_run_assembly` (Phase 1 - Minimal)

| Property | Value |
|----------|-------|
| **Phase** | 1 (Preprocessing - minimal config) |
| **Input** | `resolved_paths.json` + assembly images from stepparser |
| **Output** | `{assembly_name}-Metadata_assembly_enriched.json` (v1) |
| **Location** | `session_root/` |
| **LLM Call** | YES (via `tools.analyse_assembly_img`) |
| **Description** | Initial assembly analysis (quick overview for Agent 1) |

**Output Structure**:
```json
{
  "assembly_name": "{assembly_name}",
  "total_parts": 15,
  "part_interactions": [...],
  "assembly_type": "...",
  "constraints": [...]
}
```

**Used By**: Agent 1 (for context loading), Phase 2a (refined in next iteration)

---

## AGENT 1: Assembly Analyst (After Phase 2a)

| Property | Value |
|----------|-------|
| **Invoked** | State machine phase = "AGENT_1" |
| **Input Data** | `{assembly_name}-Metadata_assembly_enriched.json` (v1) + BOM + images |
| **Output** | `Agent_txt_files/Agent1_conversation.txt` |
| **Conversation Type** | Multi-turn (Turn 0: initial analysis, Turn 1+: user questions) |
| **Expected Output** | Assembly context, key challenges, recommendations |

**Agent 1 Loads**:
```
session_root/
├── {assembly_name}-Metadata_assembly_enriched.json (v1)
├── {assembly_name}_BOM.json (from stepparser)
├── preprocessing/stepparser/{assembly_name}/images/
│   └── iso_*.png, exploded_*.png (for context)
└── resolved_paths.json (to locate files)
```

**Agent 1 Creates**:
```
session_root/Agent_txt_files/
└── Agent1_conversation.txt ← Full conversation history (Turn 0 + user Q&A)
```

**Workflow Continues To**: Phase 2a (assembly enrichment with Agent 1 context injected)

---

## PHASE 2a: Assembly Enrichment (With Agent 1 Context)

### Node: `_node_run_assembly` (Phase 2a - Full LLM)

| Property | Value |
|----------|-------|
| **Phase** | 2a (Enrichment with Agent 1 feedback) |
| **Input** | `resolved_paths.json` + `Agent1_conversation.txt` (injected into system prompt) + all assembly images |
| **Output** | `{assembly_name}-Metadata_assembly_enriched.json` (v2, refined) |
| **Location** | `session_root/` (OVERWRITES v1) |
| **LLM Call** | YES (detailed assembly analysis) |
| **Description** | Deep assembly analysis with Agent 1's insights incorporated |

**Output Structure** (Enhanced from v1):
```json
{
  "assembly_name": "{assembly_name}",
  "total_parts": 15,
  "part_interactions": [
    {
      "part_a": "Part_1",
      "part_b": "Part_2",
      "interaction_type": "press_fit",
      "notes": "Agent 1 noted this is critical for assembly stability"
    }
  ],
  "assembly_type": "...",
  "constraints": [...],
  "assembly_insights_from_agent1": "..." ← NEW
}
```

**Used By**: Phase 2b nodes (all monopart + BOM analysis use this refined context)

---

### Node: `_node_list_parts`

| Property | Value |
|----------|-------|
| **Phase** | 2a |
| **Input** | `{assembly_name}-Metadata_assembly_enriched.json` (v2) |
| **Output** | Dictionary of part names/IDs |
| **Description** | Pass-through: extract part list for iteration |

**Used By**: `_node_run_monoparts` (for loop over each part)

---

### Node: `_node_run_monoparts`

| Property | Value |
|----------|-------|
| **Phase** | 2a |
| **Input** | Part images + metadata from stepparser + `{assembly_name}-Metadata_assembly_enriched.json` (v2 context) |
| **Output** | `enriched_parts/Part_N-Metadata_enriched.json` (for each part) |
| **Location** | `session_root/enriched_parts/` |
| **LLM Call** | YES (detailed part analysis, parallel) |
| **Description** | Analyze each part in context of assembly (geometry, function, interactions) |

**Output Structure** (per part):
```json
{
  "part_id": "Part_1",
  "part_name": "Housing",
  "geometry": {...},
  "material": "Aluminum",
  "critical_features": [...],
  "assembly_context": "..." ← Influenced by Agent 1 insights
}
```

**Used By**: `_node_merge_copy_part_data` (enriches with additional data)

---

### Node: `_node_merge_copy_part_data`

| Property | Value |
|----------|-------|
| **Phase** | 2a |
| **Input** | `enriched_parts/Part_N-Metadata_enriched.json` + part data from stepparser |
| **Output** | `enriched_parts/Part_N_Data_enriched_merged.json` (for each part) |
| **Location** | `session_root/enriched_parts/` |
| **Description** | Merge LLM analysis with raw CAD data (dimensions, tolerances, etc.) |

**Used By**: `_node_merge_bom` (collects all part data for BOM)

---

### Node: `_node_merge_bom`

| Property | Value |
|----------|-------|
| **Phase** | 2a → 2b boundary |
| **Input** | `enriched_parts/Part_*_Data_enriched_merged.json` (all parts) |
| **Output** | `{assembly_name}_BOM_enriched.json` |
| **Location** | `session_root/` |
| **Description** | Single BOM combining all part data (no LLM, pure concatenation) |

**Output Structure**:
```json
{
  "assembly_name": "{assembly_name}",
  "total_parts": 15,
  "parts": [
    {
      "part_id": "Part_1",
      "part_name": "Housing",
      "quantity": 1,
      "geometry": {...},
      "material": "Aluminum",
      "critical_features": [...]
    },
    ...
  ]
}
```

**Used By**: `_node_generate_assembly_sequence` (v1 generation, iteration 1)

---

## PHASE 2b: Sequence Generation (Iteration 1)

### Node: `_node_generate_assembly_sequence` (Run 1)

| Property | Value |
|----------|-------|
| **Phase** | 2b (Iteration 1 - Initial sequence) |
| **Input** | `{assembly_name}_BOM_enriched.json` + assembly images + `Agent1_conversation.txt` (as context) |
| **Output** | `assembly_sequence_run1/assembly_sequence.json` |
| **Location** | `session_root/assembly_sequence_run1/` |
| **LLM Call** | YES (sequence generation via vision + text analysis) |
| **Description** | Generate optimal assembly sequence considering part properties and interactions |

**Output Structure**:
```json
{
  "assembly_name": "{assembly_name}",
  "total_steps": 15,
  "base_part": {"part_id": "Part_1", "reason": "Largest, most stable"},
  "steps": [
    {
      "step_number": 1,
      "description": "Place Part_1 on table",
      "base_part_id": "Part_1",
      "joining_part_id": [],
      "joining_process": "place_on_table"
    },
    {
      "step_number": 2,
      "description": "Insert Part_2 into Part_1",
      "base_part_id": "Part_1",
      "joining_part_id": ["Part_2"],
      "joining_process": "insert",
      "constraints": ["Tolerance: ±0.1mm"]
    },
    ...
  ]
}
```

**Created At**: `assembly_sequence_run1/`

```
session_root/assembly_sequence_run1/
├── assembly_sequence.json          ← Main output
├── sequence_renderings/
│   ├── step_1.png
│   ├── step_2.png
│   └── ... (preview images per step)
└── remarks.txt                      ← EMPTY initially (will be filled by Agent 2)
```

**Used By**: Agent 2 (for validation)

---

## AGENT 2: Sequence Validator Loop

### Loop Control

```
AGENT_2_LOOP Iteration 1:
  ├─ Load: assembly_sequence_run1/assembly_sequence.json
  ├─ Agent 2 presents sequence to user
  ├─ User feedback collected
  ├─ Decision:
  │   ├─ IF user approves → go to PHASE_4
  │   └─ IF user feedback → save remarks, regenerate
  └─ Output: assembly_sequence_run{1}/remarks.txt

AGENT_2_LOOP Iteration 2+ (if feedback):
  ├─ Phase 2b REGENERATES with remarks context
  │   └─ _node_generate_assembly_sequence reads remarks
  │   └─ Generates assembly_sequence_run{N}/assembly_sequence.json
  ├─ Agent 2 presents NEW sequence
  ├─ User feedback again
  └─ Repeat until approval OR max_iterations reached
```

### Agent 2 Invocation (Iteration N)

| Property | Value |
|----------|-------|
| **Invoked** | State machine phase = "AGENT_2_LOOP" |
| **Input Data** | `assembly_sequence_run{N}/assembly_sequence.json` + rendered step images |
| **Output** | `Agent_txt_files/Agent2_validation_iteration_{N}.txt` + approval flag |
| **Conversation Type** | Multi-turn (Turn 0: present sequence, Turn 1+: clarification/approval) |

**Agent 2 Loads**:
```
session_root/
├── assembly_sequence_run{N}/assembly_sequence.json (current sequence)
├── assembly_sequence_run{N}/sequence_renderings/ (step images)
├── {assembly_name}-Metadata_assembly_enriched.json (context)
├── {assembly_name}_BOM_enriched.json (part info)
└── Agent_txt_files/Agent1_conversation.txt (assembly insights)
```

**Agent 2 Creates** (on each iteration):
```
session_root/
├── Agent_txt_files/Agent2_validation_iteration_{N}.txt ← Conversation + decision
├── assembly_sequence_run{N}/remarks.txt                ← User feedback (if iteration N < final)
└── [If approved] → Workflow proceeds to PHASE_4
```

**Feedback Format** (remarks.txt):
```
User Feedback (Iteration {N}):
- Step 2: Part_2 should be inserted BEFORE Part_3 (currently after)
- Step 5: Add constraint about surface damage prevention
- Overall: Sequence is more logical now, but these adjustments needed
```

**Workflow Decision**:
- **Approval keyword found** → Set state `approval=True` → Proceed to PHASE_4
- **Max iterations reached** → Force approval of `assembly_sequence_run{N}` → Proceed to PHASE_4
- **User feedback** → Increment run counter → Regenerate Phase 2b with remarks → Repeat Agent 2

---

## PHASE 2b (Regeneration): Sequence Generation with Remarks

### Node: `_node_generate_assembly_sequence` (Run 2+)

| Property | Value |
|----------|-------|
| **Phase** | 2b (Iteration N > 1 - with user feedback) |
| **Input** | `{assembly_name}_BOM_enriched.json` + `assembly_sequence_run{N-1}/remarks.txt` (user feedback) + images |
| **Output** | `assembly_sequence_run{N}/assembly_sequence.json` (improved) |
| **Location** | `session_root/assembly_sequence_run{N}/` |
| **LLM Call** | YES (regeneration with feedback context) |
| **Description** | Re-generate sequence incorporating user feedback from iteration N-1 |

**Input from Previous Iteration**:
```
session_root/assembly_sequence_run{N-1}/
├── assembly_sequence.json (old sequence)
└── remarks.txt            ← USER FEEDBACK (fed to LLM system prompt)
```

**System Prompt Injection**:
```
You are an assembly sequence expert.

Previous Feedback from User (Iteration {N-1}):
{remarks_content}

Generate improved sequence addressing this feedback...
```

**Output** (new sequence incorporating feedback):
```
session_root/assembly_sequence_run{N}/
├── assembly_sequence.json ← NEW, with feedback incorporated
├── sequence_renderings/ ← NEW renderings for new sequence
└── remarks.txt ← EMPTY (will be filled if user gives more feedback)
```

**Workflow Continues**: Agent 2 validates again with `assembly_sequence_run{N}/assembly_sequence.json`

**Loop Exits When**: Approval detected OR max_iterations (default: 5) reached

---

## PHASE 4: Rendering + Quality Assessment (After Agent 2 Approval)

### Node: `_node_render_assembly_steps`

| Property | Value |
|----------|-------|
| **Phase** | 4 (Quality Assessment) |
| **Input** | `assembly_sequence_run{final}/assembly_sequence.json` (highest numbered run = approved) |
| **Output** | `assembly_sequence_run{final}/` (populated with all step renderings) |
| **Description** | Generate high-quality 3D renderings for each assembly step (all 5 views) |

**Input Location**:
```
Detects highest numbered assembly_sequence_run{X}/ and uses that
Final approved sequence from Agent 2 loop
```

**Output Structure**:
```
session_root/assembly_sequence_run{final}/
├── assembly_sequence.json (already present)
├── sequence_renderings/
│   ├── step_01_isometric.png
│   ├── step_01_front.png
│   ├── step_01_top.png
│   ├── step_01_side.png
│   ├── step_01_explosion.png
│   ├── step_02_isometric.png
│   ├── step_02_front.png
│   └── ... (all 5 views × total_steps)
└── step_{N}/
    ├── step_image.png (composite/main view)
    └── step_metadata.json (rendering parameters)
```

**Used By**: `_node_interaction_analysis` (for interaction detection), `_node_assess_ffa` (for automation analysis)

---

### Node: `_node_interaction_analysis`

| Property | Value |
|----------|-------|
| **Phase** | 4 |
| **Input** | Rendered step images (from `_node_render_assembly_steps`) + `assembly_sequence_run{final}/assembly_sequence.json` |
| **Output** | `interaction_analysis.json` |
| **Location** | `session_root/` |
| **LLM Call** | YES (per-step interaction detection, parallel) |
| **Description** | Analyze part interactions at each assembly step |

**Output Structure**:
```json
{
  "assembly_name": "{assembly_name}",
  "total_steps": 15,
  "step_interactions": [
    {
      "step_number": 1,
      "assembling_parts": ["Part_1"],
      "interactions": [
        {
          "interaction_type": "contact",
          "parts_involved": ["Part_1", "fixture"],
          "contact_area": "bottom surface",
          "notes": "Stable placement, no issues"
        }
      ]
    },
    {
      "step_number": 2,
      "assembling_parts": ["Part_1", "Part_2"],
      "interactions": [
        {
          "interaction_type": "press_fit",
          "parts_involved": ["Part_1", "Part_2"],
          "contact_area": "bore in Part_1, shaft of Part_2",
          "tight_tolerance": true,
          "potential_issues": ["Surface damage risk", "High insertion force"]
        }
      ]
    }
  ]
}
```

**Used By**: `_node_assess_ffa` (FFA assessment uses interaction data)

---

### Node: `_node_assess_ffa`

| Property | Value |
|----------|-------|
| **Phase** | 4 (Final assessment) |
| **Input** | `interaction_analysis.json` + rendered step images + `assembly_sequence_run{final}/assembly_sequence.json` |
| **Output** | `ffa_assessment/ffa_assessment.json` |
| **Location** | `session_root/ffa_assessment/` |
| **LLM Call** | YES (detailed FFA assessment per step, 4 criteria) |
| **Description** | Assess Fitness for Automation using 4 criteria: Separation, Handling, Positioning, Joining |

**Output Structure**:
```json
{
  "assembly_name": "{assembly_name}",
  "total_steps": 15,
  "assessed_steps": 15,
  "step_assessments": [
    {
      "step_id": 1,
      "step_description": "Place Part_1 on table",
      "base_part_id": "Part_1",
      "joining_part_id": [],
      "joining_process": "place_on_table",
      "assessment": {
        "separation": {
          "nature_of_provision": "Part in feeder",
          "automatable": true,
          "automatable_reasoning": "Standard robot gripper can separate from feeder"
        },
        "handling": {
          "part_rigidity": "Rigid",
          "gripping_areas": true,
          "orientation_features": true,
          "surface_sensibility": false,
          "automatable": true,
          "automatable_reasoning": "Flat surfaces allow safe gripping"
        },
        "positioning": {
          "accuracy_of_target_position": "±5mm",
          "positioning_aids": true,
          "additional_orientation_by_rotation": false,
          "automatable": true,
          "automatable_reasoning": "Low accuracy, fixture-guided"
        },
        "joining": {
          "joining_method": "Place on table",
          "joining_force": "Gravity",
          "joining_tolerance": "N/A",
          "automatable": true,
          "automatable_reasoning": "Simple placement via robot"
        }
      }
    },
    {
      "step_id": 2,
      "step_description": "Insert Part_2 into Part_1",
      "base_part_id": "Part_1",
      "joining_part_id": ["Part_2"],
      "joining_process": "insert",
      "assessment": {
        "separation": {...},
        "handling": {...},
        "positioning": {
          "accuracy_of_target_position": "±0.1mm",
          "positioning_aids": false,
          "additional_orientation_by_rotation": true,
          "automatable": "BORDERLINE",
          "automatable_reasoning": "High precision needed, no positioning aids = challenging for robot"
        },
        "joining": {...}
      }
    }
  ]
}
```

**Used By**: Agent 3 (for FFA explanation and discussion)

---

## AGENT 3: FFA Explainer (Final Endpoint)

### Agent 3 Invocation

| Property | Value |
|----------|-------|
| **Invoked** | State machine phase = "AGENT_3" (after Phase 4 completes) |
| **Input Data** | `ffa_assessment/ffa_assessment.json` + interaction context |
| **Output** | `Agent_txt_files/Agent3_ffa_explanation.txt` |
| **Conversation Type** | Multi-turn (Turn 0: auto-presentation, Turn 1+: user questions) |
| **Final Endpoint** | YES - Workflow ends when user exits Agent 3 |

**Agent 3 Loads**:
```
session_root/
├── ffa_assessment/ffa_assessment.json       ← MAIN INPUT
├── assembly_sequence_run{final}/
│   ├── assembly_sequence.json
│   └── interaction_analysis.json (optional context)
├── {assembly_name}-Metadata_assembly_enriched.json (assembly info)
└── Agent_txt_files/Agent1_conversation.txt (assembly background)
```

**Agent 3 Creates**:
```
session_root/Agent_txt_files/
└── Agent3_ffa_explanation.txt ← Full conversation (Turn 0 auto-intro + Turn 1+ user Q&A)
```

**Conversation Flow**:
```
TURN 0 (Automatic - No user input needed):
  ├─ Load FFA assessment from ffa_assessment.json
  ├─ Build system prompt with full 4×step FFA matrix
  ├─ Invoke LLM: "Present FFA results for this assembly"
  ├─ LLM auto-generates:
  │   ├─ High-level automation fitness overview
  │   ├─ 2-3 key automation challenges identified
  │   └─ 2-3 key improvement opportunities
  └─ Display to user

TURN 1+ (User-Driven Questions):
  ├─ User asks: "Which steps are hardest to automate?"
  ├─ Agent 3 responds with FFA-based insights
  ├─ User can ask follow-up questions
  ├─ Agent discusses design improvements, cost-benefit, etc.
  └─ User types "exit" or "done" to finish

WORKFLOW COMPLETE:
  └─ Conversation saved to ffa_summary.txt
  └─ Session ends (no further phases)
```

---

## Complete Data Flow Visualization

```
PHASE 1: Preprocessing
  ├─ Stepparser Runs
  │   └─ preprocessing/stepparser/{assembly}/
  │       ├─ assembly_*/BOM.json
  │       ├─ assembly_*/Overview_Stepparser.json
  │       ├─ Part_*/metadata.json
  │       └─ images/
  ├─ _node_resolve_paths
  │   └─ resolved_paths.json
  └─ _node_run_assembly (v1 - minimal)
      └─ {assembly}-Metadata_assembly_enriched.json (v1)

         ↓ Agent 1 (Multi-turn conversation)
         └─ Agent_txt_files/Agent1_conversation.txt

PHASE 2a: Enrichment with Agent 1 Context
  ├─ _node_run_assembly (v2 - full, Agent 1 context injected)
  │   └─ {assembly}-Metadata_assembly_enriched.json (v2)
  ├─ _node_run_monoparts
  │   └─ enriched_parts/Part_*-Metadata_enriched.json
  ├─ _node_merge_copy_part_data
  │   └─ enriched_parts/Part_*_Data_enriched_merged.json
  └─ _node_merge_bom
      └─ {assembly}_BOM_enriched.json

PHASE 2b: Sequence Generation (Iteration 1)
  └─ _node_generate_assembly_sequence
      └─ assembly_sequence_run1/
          ├─ assembly_sequence.json
          ├─ sequence_renderings/step_*.png
          └─ remarks.txt (empty)

         ↓ Agent 2 Validation Loop
         ├─ Agent_txt_files/Agent2_validation_iteration_1.txt
         ├─ User provides feedback
         └─ IF feedback → Generate remarks.txt → Regenerate Phase 2b

         [Loop: Phase 2b → Agent 2 → feedback → Phase 2b → ... UNTIL approval]

         ↓ When approved OR max_iterations

PHASE 4: Rendering + Quality Assessment
  ├─ _node_render_assembly_steps
  │   └─ assembly_sequence_run{final}/sequence_renderings/
  ├─ _node_interaction_analysis
  │   └─ interaction_analysis.json
  └─ _node_assess_ffa
      └─ ffa_assessment/ffa_assessment.json

         ↓ Agent 3 FFA Explainer
         ├─ Turn 0: Auto-presents FFA summary
         ├─ Turn 1+: User Q&A about automation fitness
         └─ Agent_txt_files/Agent3_ffa_explanation.txt

WORKFLOW COMPLETE ✓
```

---

## Quick Reference: Where to Find Data

| Data Type | Location | Phase | Purpose |
|-----------|----------|-------|---------|
| **Resolved Paths** | `resolved_paths.json` | 1 | Maps all file locations |
| **Assembly Metadata** | `{assembly}-Metadata_assembly_enriched.json` | 1,2a | Assembly overview (v1→v2) |
| **Agent 1 Context** | `Agent_txt_files/Agent1_conversation.txt` | 1→2a | Assembly insights from LLM |
| **Enriched Parts** | `enriched_parts/Part_*-Metadata_enriched.json` | 2a | Per-part analysis |
| **BOM** | `{assembly}_BOM_enriched.json` | 2a→2b | All part data combined |
| **Sequence (Iteration N)** | `assembly_sequence_run{N}/assembly_sequence.json` | 2b | Assembly steps |
| **User Feedback** | `assembly_sequence_run{N}/remarks.txt` | 2b+Agent2 | User's iteration feedback |
| **Agent 2 Log** | `Agent_txt_files/Agent2_validation_iteration_{N}.txt` | Agent2 | Validation conversation |
| **Step Renderings** | `assembly_sequence_run{final}/sequence_renderings/` | 4 | Visual guides per step |
| **Interactions** | `interaction_analysis.json` | 4 | Part contact analysis |
| **FFA Assessment** | `ffa_assessment/ffa_assessment.json` | 4 | Automation fitness scores |
| **Agent 3 Log** | `Agent_txt_files/Agent3_ffa_explanation.txt` | Agent3 | FFA discussion Q&A |

