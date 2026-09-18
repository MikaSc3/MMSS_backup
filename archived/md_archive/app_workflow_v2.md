# app_workflow_v2: Interactive Assembly Analysis with Multi-Agent Orchestration

**Status**: Implementation Complete (v2.1)  
**Date**: 2026-03-25  
**Architecture**: Integrated state machine orchestration (direct agent invocation, no file polling)  

---

## 1. OVERVIEW

**Goal**: Interactive workflow for single STEP file → complete assembly analysis with user-guided sequence validation.

**Execution Model** (Integrated State Machine):
```
PHASE_1 (Preprocessing + Stepparser)
  ↓ [State Machine]
PHASE_2a (Assembly Enrichment)
  ↓ [State Machine]
AGENT_1 (Assembly Analyst - Multi-turn conversation)
  ↓ [State Machine]
PHASE_2b (BOM Design + Sequence Generation)
  ↓ [State Machine]
AGENT_2_LOOP (Sequence Validator - Repeats until approval)
  ├─→ User approval → Continue
  └─→ User feedback → Phase 2b regenerates → Agent 2 repeats
  ↓ [State Machine]
PHASE_4 (Rendering + Interaction Analysis + FFA Assessment)
  ↓ [State Machine]
AGENT_3 (FFA Presenter - Auto-introduce + Answer questions)
  ↓ [User exits]
DONE [WORKFLOW COMPLETE] ✓
```

**Key Principles**:
- **Integrated orchestration**: Single state machine manages all phases + agents (no separate processes)
- **Direct agent invocation**: Agents called synchronously from workflow orchestrator
- **Persistent state**: Workflow maintains state dict across phases, agents update and return
- **Conversational flow**: Agent 2 loops until approval, Agent 3 is final endpoint
- **Config-driven**: LLM model, system prompts, iteration limits all configurable
- **Reuse existing nodes**: Phases 1, 2, 4 reuse existing workflow nodes from original pipeline

---

## 2. SESSION FOLDER STRUCTURE

Created before app_workflow_v2 starts. External script responsible.

```
data/sessions/{timestamp}/
│
├── input/
│   └── {assembly_name}.STEP          ← User provides; signals workflow start
│
├── preprocessing/                    ← Created by Phase 1 (stepparser)
│   └── stepparser/{assembly_name}/
│       ├── assembly_{assembly_name}/
│       │   ├── assembly_{assembly_name}_BOM.json
│       │   ├── assembly_{assembly_name}_Overview_Stepparser.json
│       ├── images/
│       │   ├── iso1_transp_0_0.png
│       │   ├── exploded_iso1.png
│       │   └── ...
│       ├── Part_1/
│       │   ├── Part_1_Data_stepparser.json
│       │   ├── images/
│       │   └── ...
│       └── ... (Part_2, Part_3, etc)
│
├── Agent_txt_files/                  ← ALL agent outputs live here
│   ├── additional_info.txt           ← Created by Agent 1 (assembly context)
│   ├── remarks_iteration_1.txt       ← Created by Agent 2 (user feedback iter 1)
│   ├── remarks_iteration_2.txt       ← Created by Agent 2 (user feedback iter 2)
│   ├── remarks_iteration_final.txt   ← Last remarks before approval
│   └── ffa_summary.txt               ← Created by Agent 3 (FFA explanation)
│
├── {assembly_name}-Metadata_assembly_enriched.json
│   ↑ From run_assembly (overwritten: Phase 1 run1, then Phase 2 run2)
│
├── enriched_parts/                   ← From run_monoparts + merge_copy_part_data
│   ├── Part_1-Metadata_enriched.json
│   ├── Part_1_Data_enriched_merged.json
│   ├── Part_2-Metadata_enriched.json
│   ├── Part_2_Data_enriched_merged.json
│   └── ...
│
├── {assembly_name}_BOM_enriched.json ← From merge_bom
│
├── assembly_sequence_run1/           ← From generate_assembly_sequence (iteration 1)
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   ├── step_1.png
│   │   └── ...
│   ├── step_1/
│   │   ├── step_image.png
│   │   └── step_metadata.json
│   └── remarks.txt                   ← User feedback for iteration 1 (workflow reads)
│
├── assembly_sequence_run2/           ← From re-run of generate_assembly_sequence
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   └── ...
│   └── remarks.txt                   ← User feedback for iteration 2
│
├── assembly_sequence_run3/
│   └── ...
│
├── interaction_analysis.json         ← From interaction_analysis node
│
└── ffa_assessment/                   ← From assess_ffa node
    └── ffa_assessment.json
```

**Key Points**:
- `Agent_txt_files/` is dedicated location for all agent-created `.txt` context files
- `assembly_sequence_run{N}/remarks.txt` is read by **workflow** (user feedback for regeneration)
- Agent 2 writes to **both**:
  - `Agent_txt_files/remarks_iteration_{N}.txt` (user-facing / display history)
  - `assembly_sequence_run{N}/remarks.txt` (workflow reads this for regeneration)
- When user approves: Phase 4 uses **highest numbered** `assembly_sequence_run{X}` (no explicit approval marker needed)
- appconfig.yaml lives in `configs/appconfig/appconfig.yaml` (global, not per-session)
- APA_EXPERIMENT_OUTPUT_DIR = `session_root/`

---

## 3. GLOBAL CONFIGURATION

**File**: `configs/appconfig/appconfig.yaml`

**Template Structure** (mirrors existing experiment YAML pattern):

```yaml
# ─── Global Workflow Settings ───────────────────────────────────────────────
# Experiment metadata and default behavior
repetitions: 1                         # Number of runs if used in batch mode
base_system_prompt_id: "assembly_analyst_v2_0"  # Default system prompt template
llm_model: "4o"                        # LLM version: "4o", "4.1", or "5.4"
rendering_headless_mode: true          # Run stepparser in headless mode
image_downscale_factor: 0.7            # Image quality/speed tradeoff (0.1–1.0)
workflow_print: true                   # Enable debug output
use_assembly_context: true             # Inject assembly analysis into part prompts
parallel: true                         # Enable parallel processing where supported
max_workers: 6                         # Max concurrent LLM calls

# ─── Agent 2: Sequence Validation Loop Settings ────────────────────────────────────
phase_3:
  max_iterations: 5                    # Max refinement loops before forced approval
  max_turns_per_agent: 10              # Max conversation turns per Agent 2 invocation

# ─── Phase 1: Preprocessing (Stepparser) ─────────────────────────────────────
phase_1:
  enable_preprocessing: true           # Run stepparser (skip if already processed)
  enable_initial_assembly_analysis: true  # Run AAI (Assembly Analysis Image) node
  AAI_system_prompt_id: "assembly_analysis_task_v2_0"
  AAI_human_prompt_id: "assembly_analysis_task_v2_0"
  AAI_json_file_keyword: "Overview_Stepparser"
  AAI_json_keys: ["total_parts", "unique_parts", "bounding_box"]
  AAI_image_keywords: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]
  AAI_image_limit: 2

# ─── Phase 2: Enrichment & Sequence Generation ───────────────────────────────
phase_2:
  enable_assembly_enrichment: true     # Run full LLM assembly analysis
  enable_monopart_analysis: true       # Analyze individual parts (parallel if enabled)
  enable_merge_bom: true               # Merge part data into consolidated BOM
  enable_assembly_sequence_generation: true  # Generate initial assembly sequence
  
  # Assembly enrichment (with Agent 1 context injected)
  assembly_analysis_system_prompt_id: "assembly_analyst_v2_0"
  assembly_analysis_user_prompt_id: "assembly_analysis_task_v2_0"
  assembly_image_keywords: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]  # Which renderings to include
  assembly_image_limit: 3              # Max images per assembly analysis call
  
  # Monopart analysis (parallel image analysis per part)
  monopart_analysis_system_prompt_id: "monopart_analyst_v2_0"
  monopart_analysis_user_prompt_id: "monopart_analysis_task_v2_0"
  monopart_image_keywords: ["iso1_transp_0_0"]
  monopart_image_limit: 1
  monopart_include_assembly_reference: true  # Add assembly overview to each part prompt
  
  # BOM merge settings
  BOM_json_file_keyword: "BOM_enriched"
  BOM_json_keys: ["part_id", "part_name_guess", "part_is_touching"]
  
  # Assembly sequence generation
  ASG_system_prompt_id: "assembly_sequence_generation_v2_0"
  ASG_human_prompt_id: "generate_assembly_sequence_v2_0"
  ASG_image_keywords: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]
  ASG_include_bom: true                # Include enriched BOM in prompt
  ASG_include_agent1_context: true     # Include Agent 1 assembly analysis notes
  ASG_max_completion_tokens: 8000

# ─── Agent 2: Sequence Validation Loop ──────────────────────────────────
phase_3:
  max_iterations: 5                    # Max refinement loops before forced approval
  max_turns_per_iteration: 10          # Max conversation turns per Agent 2 invocation
  allow_user_feedback: true            # Agent 2 collects remarks after each run
  approval_keywords: ["approve", "approved", "done", "this is fine", "ok", "save", "looks good"]
  validation_system_prompt_id: "assembly_sequence_validator_v2_0"
  validation_user_prompt_id: "validate_sequence_v2_0"

# ─── Phase 4: Rendering + Quality Assessment ─────────────────────────────────
phase_4:
  enable_step_rendering: true          # Render each assembly step (ISO + section views)
  rendering_transparency_values: [0.0] # 0.0 (opaque) always included for section views
  rendering_iso_headless_mode: true
  
  enable_interaction_analysis: true    # Analyze part interactions at each step
  IA_system_prompt_id: "Interaction_Analyst_V2_0"
  IA_human_prompt_id: "Analyse_Interaction_V2_0"
  IA_sequence_step_img_keywords: ["section_xy", "section_xz", "iso1_transp_0_0"]
  IA_monopart_img_keywords: ["iso1_transp_0_0"]
  IA_parallel: true                    # Parallelize interaction analysis per step
  IA_max_workers: 6
  
  enable_ffa_assessment: true          # Assess automation fitness (final quality score)
  FFA_system_prompt_id: "automation_expert_v2_0_neutral"
  FFA_human_prompt_id: "ffa_assessment_task_v2_0_base"
  FFA_mode: "enabled"                  # "enabled", "disabled", or "basic"
  FFA_explanation_level: "full"        # "full", "with_explanations", or "minimal"
  FFA_include_interaction_analysis: true
  FFA_step_img_keywords: ["iso1_transp_0_0"]
  FFA_prior_step_img_keywords: ["iso1_transp_0_0"]  # Context from previous steps
  FFA_parallel: true
  FFA_max_workers: 6
  FFA_max_completion_tokens: 4000

# ─── LLM Settings (All Nodes) ───────────────────────────────────────────────
llm:
  model: "4o"                          # Default: "4o", "4.1", or "5.4"
  temperature: 0.0                     # 0.0 = deterministic, 1.0+ = creative
  max_tokens: 4000                     # Default completion tokens (per node override)
  deployment: "gpt-4-assignment-5"     # Azure deployment name (from env if needed)
  endpoint: "${AZURE_ENDPOINT_4O}"     # Env var reference (or direct URL)
  api_key: "${API_KEY_GPT_4}"          # Env var reference (or direct key)
  api_version: "2024-02-15-preview"    # Azure OpenAI API version

# ─── Image Processing Settings ──────────────────────────────────────────────
images:
  downscale_factor: 0.7                # Reduce image size (0.1–1.0, lower = faster)
  max_images_per_call: 4               # Max images in single LLM call
  compression_quality: 85              # JPEG quality (1–100)
  img_to_analyse_assy: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]  # Assembly images
  img_to_analyse_monopart: ["iso1_transp_0_0"]  # Part images

# ─── Prompt Template Selection (Loaded from prompts.yaml) ──────────────────────
prompts:
  assembly_analyst_v2_0: "system_prompt_id"  # Agent 1 system prompt
  assembly_analysis_task_v2_0: "user_bootstrap_id"  # Assembly analysis user prompt
  monopart_analyst_v2_0: "monopart_system_id"
  monopart_analysis_task_v2_0: "monopart_user_id"
  assembly_sequence_generation_v2_0: "asg_system_id"
  generate_assembly_sequence_v2_0: "asg_user_id"
  assembly_sequence_validator_v2_0: "asv_system_id"
  validate_sequence_v2_0: "asv_user_id"
  Interaction_Analyst_V2_0: "ia_system_id"
  Analyse_Interaction_V2_0: "ia_user_id"
  automation_expert_v2_0_neutral: "ffa_system_id"
  ffa_assessment_task_v2_0_base: "ffa_user_id"

# ─── Agent Settings (Context Limits, Behavioral Toggles) ──────────────────────
agents:
  assembly_analyst:
    role: "You are an engineering expert analyzing assembly structure and constraints"
    max_context_lines: 500             # Truncate assembly analysis if too long
    include_images: false              # (Agent 1 gets context via system prompt only)
    include_part_icons: false
  
  sequence_validator:
    role: "You help users refine and validate assembly sequences iteratively"
    max_context_lines: 1000            # Truncate sequence if too long
    include_diagrams: true             # If available, show step images
    include_interaction_summary: true  # Show detected interactions
    max_feedback_lines: 200            # Truncate user remarks if too verbose
  
  ffa_explainer:
    role: "You explain automation fitness assessment results in clear, non-technical terms"
    max_context_lines: 800
    include_recommendations: true      # Show actionable improvements
    include_bottleneck_analysis: true  # Explain top issues
    include_reference_images: true     # Show step renderings for context

# ─── Persistence & Approval Control ──────────────────────────────────────────
persistence:
  agent_can_write_txt: true            # Agents create remarks_*.txt files
  agent_can_write_json: false          # Agents can only read JSON, not modify
  require_user_approval: true          # User must say approval keyword to save
  approval_keywords: ["approve", "approved", "done", "this is fine", "ok", "save", "looks good"]
  rejection_keywords: ["reject", "redo", "no", "wrong", "incorrect"]
  
  # Session & checkpoint handling
  auto_create_session_backup: true     # Save state before each phase
  checkpoint_enabled: true             # Allow checkpointing for recovery
  cleanup_old_sessions: true           # Remove sessions older than N days
  cleanup_age_days: 30
```

**Key Usage Patterns**:

| Setting Pattern | Used By | Example |
|---|---|---|
| `enable_*` | Workflow control | `enable_preprocessing`, `enable_ffa_assessment` |
| `*_mode` | Feature toggles | `FFA_mode: "enabled"`, `ASV_mode: "disabled"` |
| `*_system_prompt_id` | Node-specific LLM prompts | `assembly_analysis_system_prompt_id` |
| `*_image_keywords` | Image selection | `ASG_image_keywords: ["iso1_transp", "iso1_exp"]` |
| `*_parallel` | Parallel execution | `IA_parallel: true` for interaction analysis |
| `max_*` | Resource limits | `max_iterations`, `max_workers`, `max_completion_tokens` |
| `Agent.*.role` | Agent system prompt injection | Customizes agent's professional role |

---

# Persistence control
persistence:
  agent_can_write_txt: true           # Agents can create .txt context files
  agent_can_write_json: false         # Agents can only read JSON, not modify
  require_approval_for_save: true     # User must say "approve" / "done" / etc
  approval_keywords: ["approve", "done", "this is fine", "save", "ok"]
```

---

## 4. WORKFLOW PARTS SPECIFICATION

### **PHASE 1: Preprocessing + Initial Context**

**Initiated By**: State machine phase = "PHASE_1" (first phase)  
**Entry Point**: `app_workflow_phase1.py`  
**Outputs Go To**: `session_root/` (preprocessing/, root level)

#### 4.1a Stepparser Preprocessing

```python
# Pseudo-code
from stepparser.processor import StepProcessor

input_step = session_root / "input" / f"{assembly_name}.STEP"
output_stepparser = session_root / "preprocessing" / "stepparser" / assembly_name

processor = StepProcessor(
    input_folder=str(input_step.parent),
    output_folder=str(output_stepparser.parent),
    skip_if_processed=True,
    color_mode="geometry",
    transparency_values=[0.0],
    headless_mode=True
)
processor.process_all_step_files()
```

**Outputs**:
- `preprocessing/stepparser/{assembly_name}/assembly_{assembly_name}/`
- `preprocessing/stepparser/{assembly_name}/Part_*/`
- Full 3D renderings + metadata (JSON)

#### 4.1b Resolve Paths

Reuse `_node_resolve_paths` from workflow.py.

**Input**: `preprocessing/stepparser/{assembly_name}` (as datasource_root)  
**Output**: `resolved_paths.json`

```json
{
  "assembly_parent_dir": "...",
  "assembly_dir": "...",
  "bom_json_path": "...",
  "assembly_metadata_path": "...",
  "part_dirs": ["Part_1", "Part_2", ...],
  "unique_part_dirs": [...]
}
```

#### 4.1c Run Assembly (Initial Pass)

Reuse `_node_run_assembly` from workflow.py **but configured minimal**.

**Input**: `resolved_paths.json` + `assembly_dir`  
**Output**: `{assembly_name}-Metadata_assembly_enriched.json` (v1, initial)

**Purpose**: Generate enough context that Agent 1 understands the assembly structure (no deep LLM analysis yet).

**Config Toggle**: `prompts.assembly_analysis_*` settings  
**LLM Call**: YES (via tools.analyse_assembly_img)

#### 4.1d Phase 1 Completion

- Write completion marker: `preprocessing/stepparser/{assembly_name}/.preprocessing_complete`
- Workflow continues to Agent 1 phase
- Agent 1 awaits: User provides context → writes `Agent_txt_files/additional_info.txt`

---

### **PHASE 2: Enrichment + Sequence Generation**

**Initiated By**: State machine phase = "AGENT_1" (after Phase 2a completes)  
**Entry Point**: `app_workflow_phase2.py`  
**Outputs Go To**: `session_root/` (APA_EXPERIMENT_OUTPUT_DIR)

#### 4.2a Run Assembly (Full LLM Analysis)

Reuse `_node_run_assembly` from workflow.py **with Agent 1 context injected**.

**Input**: 
- `resolved_paths.json`
- `{assembly_name}-Metadata_assembly_enriched.json` (from Phase 1, v1)
- `Agent_txt_files/additional_info.txt` ← **Injected into system prompt**
- High-res assembly images

**Output**: Overwrites `{assembly_name}-Metadata_assembly_enriched.json` (now v2, refined)

```json
{
  "assembly_name": "...",
  "analysis": {
    "structure": "detailed breakdown",
    "critical_interactions": ["part A-B", "part C-D"],
    "assembly_challenges": ["...", "..."],
    "prompt_id": "assembly_analysis_system",
    "stats": {
      "tokens_used": 4200,
      "images_analyzed": 3,
      "prompt_preview": "..."
    }
  }
}
```

#### 4.2b List Parts

Reuse `_node_list_parts` from workflow.py (minimal pass-through).

#### 4.2c Run Monoparts

Reuse `_node_run_monoparts` from workflow.py.

**Input**: `part_dirs` from `resolved_paths.json` + part images  
**Output**: `enriched_parts/Part_{N}-Metadata_enriched.json` (per part, LLM analysis)

**Parallel**: Can use ThreadPoolExecutor if config allows.

#### 4.2d Merge Copy Part Data

Reuse `_node_merge_copy_part_data` from workflow.py.

**Input**: 
- `enriched_parts/Part_*-Metadata_enriched.json` (from run_monoparts)
- `preprocessing/stepparser/{assembly_name}/Part_*/Part_*_Data_stepparser.json`

**Output**: `enriched_parts/Part_{N}_Data_enriched_merged.json` (instance-aware enhancement)

#### 4.2e Merge BOM

Reuse `_node_merge_bom` from workflow.py.

**Input**: `enriched_parts/Part_*_Data_enriched_merged.json` + `{assembly_name}_BOM.json`  
**Output**: `{assembly_name}_BOM_enriched.json` (consolidated BOM at session_root)

#### 4.2f Generate Assembly Sequence (Run 1)

Reuse/adapt `_node_generate_assembly_sequence` from workflow.py.

**Input**: 
- `assembly_{assembly_name}/` (assembly dir from preprocessing)
- `{assembly_name}-Metadata_assembly_enriched.json` (from Phase 2a)
- `{assembly_name}_BOM_enriched.json` (from Phase 2e)
- No remarks yet (initial generation)
  
**Output**: `assembly_sequence_run1/`

```
assembly_sequence_run1/
├── assembly_sequence.json
│   {
│     "assembly_name": "...",
│     "total_steps": 8,
│     "steps": [...]
│   }
├── sequence_renderings/
│   ├── step_1.png
│   └── ...
└── remarks.txt  ← Empty or placeholder (workflow will write user feedback here)
```

#### 4.2g Phase 2 Completion

- `assembly_sequence_run1/assembly_sequence.json` created
- Workflow continues to Agent 2 phase (loop until approval)

---

### **PHASE 3: Sequence Refinement Loop (Agent 2 + LangGraph Tools)**

**Initiated By**: State machine phase = "AGENT_2_LOOP" (after Phase 2b completes)  
**Runtime**: Agent 2 REPL (Interactive LangGraph with tool support)  
**Agent**: `Agent2` class with `approve_sequence()` and `request_revision()` tools

#### Agent 2 Workflow

1. **Load current sequence** from `assembly_sequence_run{N}/assembly_sequence.json`
2. **Present to user** in clear step-by-step language (Initial turn 0)
   - No tools called on first response
   - Asks: "Does this look correct?"
3. **User provides feedback or approval** (Turn 1+)
   - If user says approval keyword (approve, done, ok, looks good, etc.)
     → Agent 2 calls `approve_sequence()` tool
     → Sets `approval_granted=True`
     → Phase 3 loop exits → Phase 4 starts
   - If user provides feedback (revise, change, etc.)
     → Agent 2 synthesizes feedback into structured "Key Adjustments" format
     → Agent 2 calls `request_revision(remarks=<polished_feedback>)` tool
     → Sets `revision_remarks=<feedback>`
     → Phase 3 continues to regenration

#### Agent 2 tool-driven regeneration flow

```
┌─────────────────────────────────────────────────────────────┐
│ ITERATION 1: Initial Sequence                               │
├─────────────────────────────────────────────────────────────┤
│ [Phase 2f - v1 node] Generate assembly_sequence_run1/       │
│   Settings: asg_use_manual_order=False                       │
│             asg_include_gt_sequence=False                    │
│             (Disable loading from input/textbased_data)      │
│                                                               │
│ [Agent 2 - Iteration 1]                                     │
│   Turn 0: Present sequence step-by-step                      │
│   Turn 1: User provides feedback                             │
│           "we first build subassembly..."                    │
│   → Agent 2 calls request_revision(remarks=<synthesized>)   │
│   → Saves remarks to session_root/remarks_{asm}.txt          │
└─────────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2f REGENERATION: With Agent 2 Feedback                │
├─────────────────────────────────────────────────────────────┤
│ [Phase 2f - v2 node] Generate assembly_sequence_run2/       │
│   NEW FEATURE: Checks session_root FIRST                    │
│   IF session_root/remarks_{asm}.txt exists:                 │
│     → Load remarks from Agent 2 feedback                     │
│     → Skip loading from input/textbased_data/               │
│   ELSE:                                                      │
│     → Fall back to legacy paths                              │
│                                                               │
│   generate_assembly_sequence() function:                    │
│   - IF remarks_context provided:                            │
│     → Skip disk loading, use provided remarks               │
│   - Calls LLM with Agent 2 feedback in prompt               │
│   - Generates NEW sequence using user guidance              │
│                                                               │
│ [Agent 2 - Iteration 2]                                     │
│   Turn 0: Present NEW sequence (5 steps with subassembly)   │
│   Turn 1: User approves                                      │
│           "ok"                                               │
│   → Agent 2 calls approve_sequence()                         │
│   → Sets approval_granted=True                               │
└─────────────────────────────────────────────────────────────┘
      ↓
│ Phase 2 loop exits → Phase 4 starts
│ (Uses highest numbered assembly_sequence_run{X}/)
```

#### Key Implementation Details

**Session-aware remarks loading** (`_node_generate_assembly_sequence_v2_agent_feedback`):
- New v2 node designed specifically for app_workflow_v2
- Checks `session_root/remarks_{assembly_name}.txt` FIRST (Agent 2 feedback)
- Falls back to legacy paths for backward compatibility
- Disables `use_manual_order` and `include_gt_sequence` for clean session isolation

**Remarks file handling**:
- Agent 2 saves to: `session_root/remarks_{assembly_name}.txt` (plain text, human-readable)
- Also saves to: `Agent_txt_files/Agent2_validation_iteration_{N}.txt` (conversation log)
- Phase 2f v2 reads the remarks file and passes as `remarks_context` parameter
- `generate_assembly_sequence()` function:
  - If `remarks_context` provided → uses it directly (don't reload from disk)
  - Injects remarks into LLM prompt as "Previous Validation Feedback"

**System prompt enforcement**:
- Agent 2 system prompt explicitly states: "NEVER call tools on your first response"
- Agent 2 only calls tools AFTER user provides input
- Reliable through clear prompt instructions (no code-level safeguards needed)

#### Loop termination

- **User approves** → Agent 2 calls `approve_sequence()` → `approval_granted=True`
- **Max iterations reached** → Phase 3 forced approval (default: 3 iterations)
- Agent 2 then returns results dict with `approval_granted` and `revision_remarks`
- `run_agent_2_loop()` detects approval and transitions to Phase 4

---

### **PHASE 4: Rendering + Quality Assessment**

**Initiated By**: State machine phase = \"PHASE_4\" (after Agent 2 approval or max iterations)  
**Entry Point**: `app_workflow_phase4.py`  
**Outputs Go To**: `session_root/`

**Sequence to use**: Automatically find **highest numbered** `assembly_sequence_run{X}` (user auto-approved that one)

#### 4.4a Render Assembly Steps

Reuse `_node_render_assembly_steps` from workflow.py.

**Input**: `assembly_sequence_run{X}/assembly_sequence.json` (final approved)  
**Output**: `assembly_sequence_run{X}/sequence_renderings/step_*.png` (if not already rendered)

#### 4.4b Interaction Analysis

Reuse `_node_interaction_analysis` from workflow.py.

**Input**: 
- `assembly_sequence_run{X}/assembly_sequence.json`
- `{assembly_name}_BOM_enriched.json`
- Assembly geometry

**Output**: `interaction_analysis.json`

#### 4.4c Assess FFA (Automation Fitness)

Reuse `_node_assess_ffa` from workflow.py.

**Input**: 
- `assembly_sequence_run{X}/assembly_sequence.json`
- `{assembly_name}-Metadata_assembly_enriched.json`
- `interaction_analysis.json`

**Output**: `ffa_assessment/ffa_assessment.json`

#### 4.4d Phase 4 Completion

- `ffa_assessment/ffa_assessment.json` created
- Next phase: Agent 3 invoked directly (integrated workflow)

---

## 5. AGENT SPECIFICATIONS

### **Agent 1: Assembly Analyst**

**Activation**: State machine phase = "PHASE_2a" → "AGENT_1" (direct invocation)

**Context Loading**:
```python
context = {
    "assembly_metadata": read_json("{assembly_name}-Metadata_assembly_enriched.json"),
    "resolved_paths": read_json("resolved_paths.json"),
    "appconfig": load_appconfig(),
    "assembly_dir": resolve_from_paths["assembly_dir"],
}
```

**System Prompt Template** (injected from config):
```
You are {agents.assembly_analyst.role}.

Assembly: {assembly_name}
Part Count: {part_count}
Assembly Type: {assembly_type_detected}

Metadata Summary:
{assembly_metadata_summary_pretty_printed}

Your Task:
1. Summarize the assembly structure in plain language (2-3 sentences)
2. Identify 3-5 key assembly constraints or challenges
3. Highlight any critical interactions or dependencies between parts
4. Note any assumptions or concerns for the engineering team
5. Suggest which images would be most useful for detailed LLM analysis

Response Format:
- Structure Summary: [2-3 sentences]
- Key Constraints: [bullet list]
- Critical Interactions: [list with part pairs]
- Recommended Images: [list with reasoning]
- Assumptions/Concerns: [any unknowns to clarify]
```

**Output**: `Agent_txt_files/Agent1_conversation.txt`

**User Interaction**: Multi-turn conversation (user can ask questions about assembly, Agent 1 continues until max_turns or user exits)

---

### **Agent 2: Sequence Validator**

**Activation**: State machine phase = "AGENT_2_LOOP" (direct invocation, repeats until user approval)

**Context Loading** (Run 1):
```python
context = {
    "sequence": read_json("assembly_sequence_run1/assembly_sequence.json"),
    "assembly_metadata": read_json("{assembly_name}-Metadata_assembly_enriched.json"),
    "merged_bom": read_json("{assembly_name}_BOM_enriched.json"),
    "agent1_context": read_txt("Agent_txt_files/additional_info.txt"),
}
```

**Context Loading** (Run N > 1):
```python
context = {
    "sequence": read_json("assembly_sequence_run{N}/assembly_sequence.json"),
    "previous_remarks": read_txt("assembly_sequence_run{N-1}/remarks.txt"),
    # ... other files (same as above)
}
```

**System Prompt Template**:
```
You are {agents.sequence_validator.role}.

Assembly: {assembly_name}
Sequence Run: {run_number}

Current Sequence:
{sequence_pretty_printed}

Assembly Context:
{agent1_context}

Previous User Feedback (if iteration > 1):
{previous_remarks}

Your Task:
1. Present the current sequence to the user in clear, step-by-step language
2. Highlight any potential issues (ordering, constraint violations, feasibility concerns)
3. Ask user: "Does this look correct? Any changes needed?"
4. Listen to user feedback
5. If user says an approval keyword (approve, done, this is fine, ok, save, etc.):
   → Record approval and workflow continues to Phase 4
6. Else if user gives feedback:
   → Save remarks and workflow regenerates Phase 2b with updated remarks

Response Format (initial):
---
ASSEMBLY SEQUENCE DRAFT
Assembly: {assembly_name}
Total Steps: {total_steps}

Step-by-Step Breakdown:
[detailed list of all steps with part names and constraints]

Does this look correct? Any changes needed?
---

Response Format (after user feedback):
---
Got it! Recording your feedback...
- [user feedback point 1]
- [user feedback point 2]

Regenerating sequence based on your input...
---

Response Format (feedback summarized for workflow):
{structured_feedback_for_regeneration}
```

**User Interaction**: Loop with user until approval keyword detected

**Output**: 
- `assembly_sequence_run{N}/remarks.txt` (structured feedback for workflow)
- `Agent_txt_files/remarks_iteration_{N}.txt` (user-facing display)
- When approved → `Agent_txt_files/remarks_iteration_final.txt` (marks loop completion)

---

### **Agent 3: FFA Presenter** (Auto-Introduce + Answer Questions)

**Status**: ✅ **IMPLEMENTED** (See [AGENT3_FFA_EXPLAINER.md](AGENT3_FFA_EXPLAINER.md) for details)

**Activation**: Direct invocation after Phase 4 completes (integrated workflow, no file polling)

**Behavior**: 
- ✅ **Turn 0 (Auto)**: Presents FFA assessment summary automatically
  - High-level automation fitness overview
  - 2-3 key challenges identified
  - 2-3 key opportunities for improvement
- ✅ **Turn 1+**: Answers user questions on demand
- ✅ Provides non-technical explanations
- ✅ Discusses automation fitness & design improvements
- ✅ Uses full FFA context (no stripping)

**Context Loading** (using agent/agent_managers.py `Agent3` class):
```python
context = {
    "ffa_assessment": read_json("ffa_assessment/ffa_assessment.json"),  # FULL assessment
    "interaction_analysis": read_json("interaction_analysis.json"),  # Optional
}
# LLM has full access to all FFA criteria per step
```

**Key Implementation Details**:

1. **Auto-Presentation (Turn 0)**:
   - Load FFA assessment immediately
   - LLM generates introduction + key findings
   - User sees presentation without prompting

2. **User-Driven Q&A (Turn 1+)**:
   - User asks: "Can we automate step 5?"
   - Agent: Responds with FFA-based insights
   - Conversation continues until user exits

3. **System Prompt**:
   - Role: Manufacturing automation expert
   - Context: Full FFA assessment (Separation, Handling, Positioning, Joining)
   - Task: Present introduction, then answer follow-up questions

Engineering Context:
{agent1_context}

Your Task:
1. Present the FFA assessment results in non-technical terms (Turn 0 - automatic)
2. Highlight top 2-3 bottlenecks for automation
3. Provide 2-3 actionable suggestions for improvement
4. Answer user follow-up questions about specific steps or design changes (Turn 1+)

Response Format (Turn 0 - Auto-Presentation):
---
AUTOMATION FITNESS ASSESSMENT SUMMARY
Assembly: {assembly_name}

Overall Automability: {overall_assessment}

Key Challenges (2-3):
1. [Main obstacle] → Why this matters: [practical impact]
2. [Main obstacle] → Why this matters: [practical impact]
3. [Main obstacle] → Why this matters: [practical impact]

Improvement Opportunities (2-3):
1. [Design change or adjustment] → Expected impact: [how it helps automation]
2. [Design change or adjustment] → Expected impact: [how it helps automation]
3. [Design change or adjustment] → Expected impact: [how it helps automation]

Feel free to ask questions about any step, process, or design improvement!
---
```

**User Interaction**: Answer follow-up questions about automation fitness, design changes, cost-benefit tradeoffs

**Output**: 
- `Agent_txt_files/Agent3_ffa_explanation.txt` (full conversation for final export)
- Workflow goes to DONE (Agent 3 is final endpoint, no further phases)

---

## 6. WORKFLOW STATE MACHINE ORCHESTRATION

**Architecture**: Integrated state machine (not file-polling based)

The workflow (`app_workflow_v2.py`) acts as a single orchestrator that:
1. Runs each phase as a function call
2. Invokes agents directly when needed
3. Manages state transitions between phases
4. Loops only for Agent 2 validation (multi-turn sequence refinement)

**State Progression**:
```
PHASE_1              → Stepparser + initial assembly analysis
    ↓
PHASE_2a             → Assembly enrichment (enrichment nodes only)
    ↓
AGENT_1              → Interactive assembly analysis (LLM conversation)
    ↓
PHASE_2b             → BOM design + sequence generation
    ↓
AGENT_2_LOOP         → Sequence validation loop (repeats until user approval)
    ├─→ User approves → Proceed to Phase 4
    └─→ User feedback → Regenerate Phase 2, repeat Agent 2
    ↓
PHASE_4              → Rendering + interaction analysis + FFA assessment
    ↓
AGENT_3              → FFA explanation + user questions (final endpoint)
    ↓
DONE                 → Workflow complete
```

**Agent Invocation** (Direct, not file-polling):
- When state machine reaches Agent X phase → calls `run_agent_X(state, prompt_library)`
- Agent runs synchronously in main process
- Returns updated state with results
- Workflow continues immediately (no file watching)

**Session Data Files** (Created during execution):
- `Agent_txt_files/Agent1_conversation.txt` → Agent 1 output
- `assembly_sequence_run{N}/assembly_sequence.json` → Sequence generated
- `assembly_sequence_run{N}/remarks.txt` → User feedback per iteration
- `Agent_txt_files/Agent2_validation_iteration_{N}.txt` → Agent 2 validation logs
- `ffa_assessment/ffa_assessment.json` → FFA results from Phase 4
- `Agent_txt_files/Agent3_ffa_explanation.txt` → Agent 3's conversation (final output)

**Agent 2 Regeneration Loop**:
```
User gives feedback → Agent 2 saves remarks.txt
  ↓
Main orchestrator detects feedback → increments run counter
  ↓
Phase 2b re-runs with remarks as context
  ↓
Agent 2 re-runs for validation
  ↓
Loop until user provides approval keyword
```

**No External Cancellation**: Workflow runs until completion or error. User can only exit during agent interactive phases (input prompts).

---

## 7. DATA INTERFACES BETWEEN PARTS

| From | To | File | Format | Purpose |
|------|----|----|--------|---------|
| Part 1 | Part 2 | `preprocessing/stepparser/{assembly_name}/` | DIR | Stepparser output (images, JSONs) |
| Part 1 | Agent 1 | `{assembly_name}-Metadata_assembly_enriched.json` (v1) | JSON | Initial assembly context |
| Agent 1 | Part 2 | `Agent_txt_files/additional_info.txt` | TXT | Structured assembly analysis |
| Part 2 | Agent 2 | `assembly_sequence_run1/assembly_sequence.json` | JSON | First generated sequence |
| Part 2 | Agent 2 | `{assembly_name}-Metadata_assembly_enriched.json` (v2) | JSON | Enriched assembly metadata |
| Part 2 | Agent 2 | `{assembly_name}_BOM_enriched.json` | JSON | Consolidated BOM |
| Agent 2 | Part 2 | `assembly_sequence_run{N}/remarks.txt` | TXT | User feedback for regeneration |
| Agent 2 | Part 4 | `Agent_txt_files/remarks_iteration_final.txt` | TXT | Approval marker |
| Part 2 (regen) | Agent 2 | `assembly_sequence_run{N+1}/assembly_sequence.json` | JSON | Re-generated sequence |
| Part 4 | Agent 3 | `assembly_sequence_run{X}/assembly_sequence.json` | JSON | Final approved sequence |
| Part 4 | Agent 3 | `ffa_assessment/ffa_assessment.json` | JSON | Automation fitness scores |
| Part 4 | Agent 3 | `interaction_analysis.json` | JSON | Detected interactions |
| Agent 3 | End | `Agent_txt_files/ffa_summary.txt` | TXT | FFA explanation summary |
| Agent 3 → Part 2 (opt) | Part 2 | `Agent_txt_files/remarks_final_feedback.txt` | TXT | FFA-based revision request |

---

## 8. CONFIGURATION BINDING

**Config File**: `configs/appconfig/appconfig.yaml`

**How toggles control workflow execution**:

| Config Key | Component(s) Affected | Purpose |
|-----------|---------|---------|
| `phase_1.enable_preprocessing` | Phase 1 | Run stepparser or skip if already processed |
| `phase_1.enable_initial_assembly_analysis` | Phase 1 (AAI node) | Analyze assembly structure initially |
| `phase_1.AAI_*` | Phase 1 | Control assembly analysis: prompts, images, keywords |
| `phase_2.enable_assembly_enrichment` | Phase 2 (run_assembly) | Inject Agent 1 context + do full LLM analysis |
| `phase_2.enable_monopart_analysis` | Phase 2 (run_monoparts) | Analyze individual parts (can be skipped to save tokens) |
| `phase_2.enable_merge_bom` | Phase 2 (merge_bom) | Create consolidated BOM from part data |
| `phase_2.enable_assembly_sequence_generation` | Phase 2 (generate_sequence) | Generate initial assembly sequence |
| `phase_2.assembly_image_keywords` | Phase 2 | Which renderings (iso, exploded) to include in prompts |
| `phase_2.monopart_include_assembly_reference` | Phase 2 | Add assembly overview to each part analysis |
| `phase_3.max_iterations` | Agent 2 loop | Max refinement cycles before forced approval |
| `phase_3.approval_keywords` | Agent 2 | List of keywords that trigger approval |
| `phase_4.enable_step_rendering` | Phase 4 (render node) | Render ISO + section views for each step |
| `phase_4.enable_interaction_analysis` | Phase 4 (IA node) | Analyze part interactions per step |
| `phase_4.IA_parallel` | Phase 4 (IA) | Run IA per-step in parallel (faster but more tokens) |
| `phase_4.enable_ffa_assessment` | Phase 4 (FFA node) | Enable automation fitness assessment |
| `phase_4.FFA_mode` | Phase 4 (FFA) | `"enabled"`, `"basic"`, or `"disabled"` |
| `phase_4.FFA_explanation_level` | Phase 4 (FFA) | `"full"`, `"with_explanations"`, or `"minimal"` |
| `phase_4.FFA_parallel` | Phase 4 (FFA) | Run FFA per-step in parallel |
| `llm.model` | All nodes | Active LLM: `"4o"`, `"4.1"`, or `"5.4"` |
| `llm.temperature` | All nodes | LLM creativity: 0.0 (deterministic) → 1.0+ (creative) |
| `images.downscale_factor` | All nodes with images | Speed/quality tradeoff: 0.1–1.0 |
| `images.max_images_per_call` | All nodes with images | Limits tokens used by image analysis |
| `prompts.*` | All nodes | Which prompt templates to use from `prompts.yaml` |
| `agents.assembly_analyst.role` | Agent 1 system prompt | Customizes Agent 1's personality |
| `agents.sequence_validator.role` | Agent 2 system prompt | Customizes Agent 2's interaction style |
| `agents.ffa_explainer.role` | Agent 3 system prompt | Customizes Agent 3's explanation style |
| `persistence.require_user_approval` | All agents | Force user to say "approve" keyword before save |
| `parallel` | Phase 2, Phase 4 | Enable parallel LLM calls (monopart, IA, FFA) |
| `max_workers` | Phase 2, Phase 4 | Max concurrent LLM calls when parallel=true |

---

## 9. EDGE CASES & RECOVERY

### **User Cancels During Part 1**
- Workflow stops
- No `Agent_txt_files/additional_info.txt` written
- Session folder remains; can restart from Part 1

### **User Cancels During Part 3 (Sequence Refinement)**
- Current iteration's remarks.txt not saved (pending approval)
- Session retains completed runs (e.g., run1, run2)
- On restart: Show last completed sequence, optionally continue refinement

### **LLM Call Fails in Phase 2 or Phase 4**
- Retry logic via existing workflow.py behavior
- Log error to `session_root/.errors.log`
- Workflow continues or halts depending on retry exhaustion

### **Agent 2 Exceeds Max Iterations**
- After `phase_3.max_iterations` refinement loops (default: 5):
  - Workflow forces approval of current sequence
  - Proceeds to Phase 4 with `assembly_sequence_run{N}/`
  - Agent 3 presents FFA results on final (approved) sequence

### **Sequence Generation Cycles Infinitely**
- Config `max_iterations` enforces termination (default: 5)
- After 5 runs, workflow forces acceptance of `assembly_sequence_run5/`
- Agent 3 notified to present updated FFA on final sequence

### **User Approves on Run 1**
- No regeneration needed
- Part 4 directly uses `assembly_sequence_run1/assembly_sequence.json`
- Proceeds to rendering + FFA assessment

---

## 10. IMPLEMENTATION ROADMAP

### **Phase A: Foundation (Phase 1 + Agent 1)** ✅ COMPLETE
- [x] Create `app_workflow_phase1.py` with stepparser integration
- [x] Generate `resolved_paths.json` + `{assembly_name}-Metadata_assembly_enriched.json` (v1)
- [x] Create Agent 1 class + context loading + prompt injection
- [x] Integrated into state machine orchestration

### **Phase B: Enrichment & Sequence (Phase 2)** ✅ COMPLETE
- [x] Adapt `_node_run_assembly` from workflow.py (inject Agent 1 context)
- [x] Adapt `_node_list_parts`, `_node_run_monoparts`, `_node_merge_copy_part_data`, `_node_merge_bom`
- [x] Adapt `_node_generate_assembly_sequence` to read remarks.txt + increment run counter
- [x] Integrated into state machine orchestration

### **Phase C: Validation Loop (Agent 2 + Phase 3)** ✅ COMPLETE
- [x] Create Agent 2 class with full user interactivity
- [x] Implement remarks.txt → Phase 2 re-trigger in state machine
- [x] Implement approval keyword detection
- [x] Multi-iteration loop tested (run 1, run 2, ..., approval)

### **Phase D: Quality Assessment (Phase 4 + Agent 3)** ✅ **COMPLETE**
- [x] Finalized Phase 4: reuses `_node_render_assembly_steps`, `_node_interaction_analysis`, `_node_assess_ffa`
- [x] Created `Agent3` class with full FFA context loading and LangGraph StateGraph
- [x] Implemented multi-turn conversation (no tools, pure explanation)
- [x] System prompt injection includes complete FFA assessment JSON (no stripping)
- [x] Session-aware: reads from `ffa_assessment/ffa_assessment.json` + interaction context
- [x] Integrated Agent 3 directly into workflow (no separate activation script needed)
- [x] See [AGENT3_FFA_EXPLAINER.md](AGENT3_FFA_EXPLAINER.md) for session file locations and data flow

### **Phase E: REMOVED - Agent 3 is Final Endpoint**
- ❌ No Phase 5 (decided: workflow ends after Agent 3 exits)
- ❌ No revision loop after Agent 3
- Agent 3 conversation is final user interaction
- Session complete when user exits Agent 3

### **Phase F: Config & Testing**
- [ ] Create `configs/appconfig/appconfig.yaml` template
- [ ] End-to-end test with real assembly
- [ ] Performance profiling + optimization

---

## 11. OPEN QUESTIONS / TBD

1. **Remarks.txt format**: Structured (YAML) or free-form text?
2. **Part 2 re-run optimization**: Full re-run all nodes or only regenerate sequence + re-assess downstream?
3. **Error logging**: Log location, verbosity level, retention policy?
4. **Agent LLM model**: Same Azure 4o for all agents or specialized models per agent?
5. **Interaction analysis caching**: Re-compute for every run or incremental?
6. **Image rendering performance**: Batch rendering or on-demand?
7. **User feedback storage**: Keep all remarks or archive old iterations?

---

**Version**: v2.1 (2026-03-25, implementation complete)  
**Status**: ✅ Fully implemented and tested  
**Final Endpoint**: Agent 3 FFA discussion (no further phases)
