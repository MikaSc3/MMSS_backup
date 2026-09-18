# Interactive Annotation Workflow (app_workflow)

**Purpose:** Interactive user-guided assembly annotation with PM (Process Manager) agent for structured question-answering and workflow orchestration.

**Status:** Phase 1 - Text-based artifacts, planned JSON migration in Phase 2

**Architecture:** Three-layer design: User ↔ PM Agent ↔ Workflow Wrapper ↔ Existing Nodes

---

## 📋 Overview

The workflow combines LLM analysis with interactive user feedback, mediated by a stateful PM agent:

1. **PM Agent (Conversation Layer)** - Stateful agent with memory, talks to user, decides workflow state
2. **Workflow Wrapper (Automation Layer)** - Runs workflow nodes from checkpoint to checkpoint automatically
3. **Workflow Nodes (Execution Layer)** - Existing nodes (run_assembly, generate_assembly_sequence, etc.)

**Process Flow:**
- PM Agent gathers assembly context → calls wrapper with `"phase_1"` → wrapper runs nodes until Phase 1 stop point
- PM Agent reviews findings → prompts user → calls wrapper with `"phase_2"` → wrapper auto-runs intermediate nodes
- Continues until completion

---

## 🗂️ Data Structure

```
data/session/
└── {assembly_name}/
    ├── input/
    │   └── {assembly_name}.STEP              ← Input STEP file
    │
    ├── output/
    │   ├── textbased_info/                   ← All text artifacts
    │   │   ├── additional_info_{name}.txt    ← Assembly questions/answers
    │   │   ├── remarks_{name}.txt            ← User sequence corrections
    │   │   └── session_state.json            ← Internal session tracking
    │   │
    │   ├── renderings/                       ← All assembly visualizations
    │   │   ├── assembly_iso_*.png            ← Phase 1 (iso only)
    │   │   ├── part_*.png                    ← Individual part views
    │   │   └── sequence_renderings/          ← Phase 4 (step-by-step)
    │   │       ├── step_001_*.png
    │   │       └── ...
    │   │
    │   ├── ffa_assessment/                   ← FFA evaluation results
    │   │   └── ffa_assessment.json
    │   │
    │   ├── assembly_sequence.json            ← Final assembly sequence
    │   └── assembly_sequence_v1.json         ← After first generation
    └── merged_bom.json                       ← Merged BOM data
```

---

## 🔄 Workflow Sequence

```
PM Agent → Wrapper.run_until("phase_1_stop") → Return to Agent
             ├─→ [0] STEPPARSER PREPROCESSING
             ├─→ [1] LOAD & RESOLVE PATHS
             ├─→ [2] INITIAL ASSEMBLY ANALYSIS (run_assembly)
             └─→ [3] MONOPART ANALYSIS (run_monoparts)

PM Agent → Wrapper.run_until("phase_2_stop") → Return to Agent
             ├─→ [4] MERGE DATA (merge_copy_part_data)
             ├─→ [5] MERGE BOM (merge_bom)
             └─→ [6] INITIAL SEQUENCE GENERATION (generate_assembly_sequence v1)
                     Rendering: ISO-only (fast)

PM Agent → Wrapper.run_until("phase_3_stop") → Return to Agent
             ├─→ [7] FULL RENDERING (render_assembly_steps)
             │       Multiple views (iso, front, top, side, sections)
             └─→ [8] SEQUENCE REGENERATION (generate_assembly_sequence v2)
                     Context: User remarks from agent

PM Agent → Wrapper.run_until("end") → End Session
             ├─→ [9] INTERACTION ANALYSIS
             ├─→ [10] FFA ASSESSMENT
             └─→ [11] SAVE SESSION STATE
```

**Key Points:**
- ✅ Workflow has **NO PM nodes** — just defined stop points
- ✅ Wrapper runs all intermediate nodes automatically
- ✅ PM Agent stays outside workflow (talks to user, maintains conversation state/memory)
- ✅ Agent decides when to proceed by calling `wrapper.run_until("phase_X")`
- ✅ State passed between wrapper calls via checkpointing

**Text Files Created:**
- `textbased_info/additional_info_{assembly_name}.txt` — PM agent saves during phase 1
- `textbased_info/remarks_{assembly_name}.txt` — PM agent saves during phase 2

---

## ⚙️ Configuration (configs/interactive_annotation/default_config.yaml)

Follows the **same pattern as run_experiments_sequence_gt.py**: uses `load_experiment_settings()` and YAML structure.

**Model Selection Strategy:**
- Global `llm_model: "4o"` for analysis nodes (run_assembly, run_monoparts, etc.)
- Node-specific overrides: `ffa_llm_model: "5.4"`, `pm_llm_model: "4o"`
- Before calling each node, check for node-specific override and set accordingly

```yaml
# === GLOBAL SETTINGS ===
base_system_prompt_id: "cad_analysis_expert_v1"
llm_model: "4o"  # Default for analysis: run_assembly, run_monoparts, etc.
temperature: 0.0

# === MODEL OVERRIDES PER NODE ===
# null/missing means use default llm_model
ffa_llm_model: "5.4"  # FFA uses premium model
pm_llm_model: "4o"    # PM uses standard model

# === IMAGE & RENDERING SETTINGS ===
image_downscale_factor: 0.7
img_to_analyse_assy: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]
img_to_analyse_monopart: ["iso1_transp_0_0"]
use_assembly_context: true

# ===  SESSION SETTINGS ===
session_input_root: "data/session"

# === NODE-SPECIFIC PROMPTS ===
# Assembly Analysis
AAI_system_prompt_id: "assembly_analyst_v1"
AAI_human_prompt_id: "assembly_analysis_task_v1"
AAI_json_file_keyword: "Overview_Stepparser"
AAI_json_keys: ["total_parts", "unique_parts", "bounding_box"]

# Monopart Analysis
AMI_system_prompt_id: "monopart_analyst_v1"
AMI_human_prompt_id: "monopart_analysis_task_v1"

# Assembly Sequence Generation
ASG_system_prompt_id: "assembly_planner_expert_v1"
ASG_human_prompt_id: "generate_assembly_sequence_v3"
ASG_image_keywords: ["iso1_transp_0_0", "iso1_exp_transp_0_0"]
ASG_json_file_keyword: "BOM_enriched"
ASG_json_keys: ["part_id", "part_name_guess", "part_is_touching"]
ASG_use_additional_info: true
ASG_use_manual_order: false  # GT mode: don't use manual order
ASG_include_remarks: true    # Second call: use user remarks
ASG_max_completion_tokens: 12000

# Interaction Analysis
IA_system_prompt_id: "Interaction_Analyst_V1"
IA_human_prompt_id: "Analyse_Interaction_V1"
IA_sequence_step_img_keywords: ["iso1_transp_0_0", "section_xy", "section_xz"]
IA_mode: "enabled"

# FFA Assessment
FFA_system_prompt_id: "automation_expert_v2_neutral"
FFA_human_prompt_id: "ffa_assessment_task_v1"
FFA_mode: "enabled"
FFA_include_interaction_analysis: false  # Can enable later
FFA_step_img_keywords: ["iso1_transp_0_0"]
FFA_max_completion_tokens: 8000

# === PM NODES (NEW) ===
# Assembly Analyst (Phase 1 interactive break)
PM_assembly_analyst_system_prompt_id: "PM_AssemblyAnalyst_system_v1"
PM_assembly_analyst_human_prompt_id: "PM_AskAssemblyQuestions_v1"

# Sequence Analyst (Phase 3 interactive break)
PM_sequence_analyst_system_prompt_id: "PM_SequenceAnalyst_system_v1"
PM_sequence_analyst_human_prompt_id: "PM_ValidateSequence_v1"

# === STEPPARSER SETTINGS ===
stepparser:
  skip_if_processed: true
  color_mode: "geometry"
  transparency_values: [0.0]
  headless_mode: true

# ============================================================================
# INTERACTIVE BREAK CONFIGURATION
# ============================================================================

# Phase 1: Assembly Analysis Questions
interactive_break_1:
  enabled: true
  name: "assembly_analyst"
  lead_questions:
    - "What is the primary function of this assembly?"
    - "What are the main sub-assemblies?"
    - "Are there any critical handling considerations?"
  ask_for_verification: true
  save_to: "textbased_info/additional_info_{assembly_name}.txt"

# Phase 2: Sequence Validation
interactive_break_2:
  enabled: true
  name: "sequence_analyst"
  allow_corrections: true
  correction_format: "free_text"
  accept_remarks: true
  save_to: "textbased_info/remarks_{assembly_name}.txt"

# ============================================================================
# RENDERING CONFIGURATION
# ============================================================================

# Phase 1 & 3: Full rendering (no selective rendering for now)
# Full views: iso, front, top, side, section views
rendering_full:
  enabled: true
  views: ["isometric", "front", "top", "side", "section_xy", "section_xz", "section_yz"]
  transparency_values: [0.0, 0.3]
  edge_width: 1.0
  save_to: "renderings/"

# ============================================================================
# TEXT FILES TO CREATE
# ============================================================================

text_artifacts:
  additional_info:
    enabled: true
    filename: "additional_info_{assembly_name}.txt"
    format: "text"  # Future: json
    folder: "textbased_info"
    
  remarks:
    enabled: true
    filename: "remarks_{assembly_name}.txt"
    format: "text"  # Future: json
    folder: "textbased_info"
    source: "user_input_phase_2"

# ============================================================================
# SEQUENCE GENERATION (Feed-back Loop)
# ============================================================================

# First generation: initial sequence
generate_assembly_sequence_v1:
  include_remarks: false
  rendering_timeout_seconds: 30
  
# Second generation: after user feedback
generate_assembly_sequence_v2:
  include_remarks: true  # Load from remarks_{assembly_name}.txt
  use_remarks_as_context: true
  rendering_timeout_seconds: 30

# ============================================================================
# PHASE 4: FINAL ANALYSIS
# ============================================================================

enable_interaction_analysis: true
enable_ffa_assessment: true

ffa_assessment:
  model: "gpt-5.4"
  save_to: "ffa_assessment/ffa_assessment.json"

# ============================================================================
# PROMPT CONFIGURATION
# ============================================================================

prompts:
  # Assembly Analysis Phase
  pm_assembly_analyst_system: "PMAssemblyAnalyst_v1"
  pm_assembly_analyst_user: "AskAssemblyQuestions_v1"
  
  # Sequence Analysis Phase
  pm_sequence_analyst_system: "PMSequenceAnalyst_v1"
  pm_sequence_analyst_user: "ValidateSequence_v1"
  
  # Standard nodes use existing prompts from run_experiments
  run_assembly: "assembly_describer_v1"
  run_monoparts: "monopart_describer_v1"
  generate_assembly_sequence: "generate_assembly_sequence_v3"
  interaction_analysis: "Analyse_Interaction_v1"
  assess_ffa: "ffa_assessment_full_v1"
```

---

## 🏗️ **Implementation Architecture**

### **Layer 1: Workflow (Existing + Stop Points)**

**File:** `agent/workflow.py` — Minimal changes
- Use existing workflow setup
- Add **checkpoint logic** to pause at defined stop points
- Stop points: after phase 1, phase 2, phase 3

**Pattern:**
```python
def build_interactive_workflow():
    graph = StateGraph(WorkflowState)
    # Add all existing nodes
    graph.add_node("resolve_paths", _node_resolve_paths)
    graph.add_node("run_assembly", _node_run_assembly)
    graph.add_node("run_monoparts", _node_run_monoparts)
    # ... etc ...
    graph.add_edge(...) # All existing edges
    
    # Compile with checkpointing
    return graph.compile(checkpointer=SQLiteSaver(...))
```

---

### **Layer 2: Workflow Wrapper (New)**

**File:** `agent/workflow_wrapper.py` — New file
- Simple wrapper that resumes from checkpoints
- Takes target phase as input
- Returns workflow results when phase reached

```python
def run_workflow_until(
    workflow_app,
    datasource_root: str,
    target_phase: Literal["phase_1_stop", "phase_2_stop", "phase_3_stop", "end"],
    thread_id: str,
    remarks: Optional[str] = None,  # Passed for phase 3
) -> Dict[str, Any]:
    """
    Resume workflow from last checkpoint until target phase.
    Returns: state dict with results
    """
    # Load checkpoint
    config = {"configurable": {"thread_id": thread_id}}
    
    # If phase 3, inject remarks into state
    if remarks:
        workflow_app.update_state(
            config,
            {"user_remarks": remarks}
        )
    
    # Stream execution until target reached
    result = None
    for event in workflow_app.stream({...}, config):
        if event.get("phase") == target_phase:
            result = event
            break
    
    return result
```

---

### **Layer 3: PM Agent (New)**

**File:** `agent/pm_agent.py` — New file
- LangGraph Agent with message history + memory store
- Calls workflow_wrapper when ready
- Talks to user via console/CLI

```python
def build_pm_agent():
    agent_graph = StateGraph(PMAgentState)
    
    agent_graph.add_node("analyze", node_analyze_state)
    agent_graph.add_node("recall_memory", node_recall_memories)
    agent_graph.add_node("ask_user", node_ask_clarifications)
    agent_graph.add_node("call_workflow", node_call_workflow_wrapper)
    agent_graph.add_node("reflect", node_reflect_and_learn)
    
    # Routing based on phase
    agent_graph.add_conditional_edges("analyze", route_by_phase)
    
    return agent_graph.compile(checkpointer=SQLiteSaver(...))
```

---

### **Layer 4: Entry Point (New)**

**File:** `app_workflow.py` — New file
- Main orchestrator
- Initializes PM agent
- Runs: Phase 1 → Phase 2 → Phase 3 → End

```python
def main(assembly_name: str, config_file: Optional[str] = None):
    # Load config
    settings = load_experiment_settings(config_file)
    
    # Initialize workflow + wrapper
    workflow_app = build_interactive_workflow()
    
    # Initialize PM agent
    pm_agent = build_pm_agent()
    
    # Run agent (handles all conversation + workflow calls)
    result = pm_agent.invoke({
        "assembly_name": assembly_name,
        "datasource_root": settings["session_input_root"],
    })
    
    # Save session state
    save_session_state(result)
```

---

### **Control Flow Diagram**

```
main()
  │
  ├─→ Load config + initialization
  │
  ├─→ PM Agent.invoke(assembly_name)
  │    │
  │    ├─→ Agent: "Analyzing assembly..."
  │    ├─→ Call: workflow_wrapper.run_until("phase_1_stop")
  │    ├─→ Receive: assembly_info
  │    │
  │    ├─→ Agent: "What is the function?" (ask_user + interrupt)
  │    ├─→ Receive: user_response
  │    ├─→ Save: additional_info_{assembly_name}.txt
  │    │
  │    ├─→ Agent: "Generating sequence..."
  │    ├─→ Call: workflow_wrapper.run_until("phase_2_stop")
  │    ├─→ Receive: sequence_v1
  │    │
  │    ├─→ Agent: "Review this sequence" + show images
  │    ├─→ Receive: user_remarks
  │    ├─→ Save: remarks_{assembly_name}.txt
  │    │
  │    ├─→ Agent: "Regenerating with your feedback..."
  │    ├─→ Call: workflow_wrapper.run_until("phase_3_stop", remarks)
  │    ├─→ Receive: sequence_v2 + full_rendering
  │    │
  │    ├─→ Agent: "Final analysis..."
  │    ├─→ Call: workflow_wrapper.run_until("end")
  │    ├─→ Receive: interaction_analysis + ffa_assessment
  │    │
  │    └─→ Return: PMAgentState
  │
  └─→ Save session_state.json
```

---

## 🔧 PM Agent Design

**Role:** Stateful conversation agent that orchestrates workflow execution and collects user feedback.

**Architecture:**
- **Memory:** Conversation history + semantic search over past assemblies (for learning patterns)
- **Tools:** PDF/CAD metadata reading (future), workflow wrapper calls
- **State:** Assembly context, user responses, decisions log
- **Integration:** LangGraph Agent (ReAct loop) → Calls workflow wrapper → Talks to user → Records learnings

---

### **Phase 1: Assembly Analysis**

**Agent Task:**
1. Receive initial assembly analysis from workflow
2. Ask clarifying questions (lead questions from config)
3. Verify user responses
4. Save findings to `additional_info_{assembly_name}.txt`
5. Signal workflow wrapper: `proceed_to_phase_2()`

**User Interaction:**
```
Agent: "I analyzed the assembly. A few clarifications:
        1. What is the PRIMARY FUNCTION?"
User: "It's a bearing assembly for rotational support"
Agent: "Got it. Any SUB-ASSEMBLIES?"
User: "Yes, outer ring, inner ring, bearing balls"
Agent: "Perfect! I'll proceed with the sequence generation."
→ Agent calls: wrapper.run_until("phase_2_stop")
```

**Saved to File:**
```
ASSEMBLY ANALYSIS NOTES
PRIMARY FUNCTION: Bearing assembly for rotational support
SUB-ASSEMBLIES: Outer ring, inner ring, bearing balls
HANDLING CONSTRAINTS: [from user or LLM]
SPECIAL NOTES: [user notes]
```

---

### **Phase 2: Sequence Review & User Feedback**

**Agent Task:**
1. Review generated assembly sequence from workflow
2. Present sequence with visualizations
3. Invite user corrections in free text
4. Save remarks to `remarks_{assembly_name}.txt`
5. Signal workflow wrapper: `proceed_to_phase_3(user_remarks)`

**User Interaction:**
```
Agent: "Here's the first assembly sequence (steps 1-5).
        [Shows sequence with ISO images]
        Any corrections or remarks?"
User: "Move step 3 before step 2, the joining is easier that way.
       Also split step 5 into two sub-steps."
Agent: "Got those remarks. Regenerating sequence with your feedback..."
→ Agent calls: wrapper.run_until("phase_3_stop", remarks="{user_input}")
```

**Saved to File:**
```
SEQUENCE CORRECTION REMARKS
USER FEEDBACK:
Move step 3 before step 2, the joining is easier that way.
Also split step 5 into two sub-steps.
```

---

### **PM Agent State Schema** (LangGraph)

```python
class PMAgentState(TypedDict):
    # Conversation
    messages: list[AnyMessage]           # Full Q&A history
    
    # Current assembly context
    assembly_name: str
    assembly_info: dict                  # From workflow phase 1
    
    # User responses
    assembly_function: str
    sub_assemblies: list[str]
    handling_constraints: list[str]
    sequence_remarks: str
    
    # Workflow state
    workflow_phase: Literal["1", "2", "3", "end"]
    workflow_checkpoint_id: str
    
    # Memory references (for learning)
    similar_past_assemblies: list[dict]  # Semantic search results
    learned_patterns: list[dict]         # Patterns from memory store
    
    # Audit
    decisions_log: list[dict]            # Why agent made each decision
```

---

### **Agent Reasoning Loop** (LangGraph ReAct)

```
1. ANALYZE: Read assembly_info from workflow, identify gaps
2. RECALL: Search memory for similar assembly cases
3. CLARIFY: Ask user questions (interrupt)
4. REASON: Generate response based on context
5. EXECUTE: Call workflow wrapper.run_until(phase)
6. OBSERVE: Receive workflow results
7. REFLECT: Save learnings to memory store
```

---

### **Future Tools for PM Agent**

- **PDF Reader:** Access assembly drawings/design docs
- **CAD Metadata Lookup:** Query part specifications (mass, materials, surface finish)
- **Design Database:** Search for similar parts in company database
- **Cost/Time Estimator:** Calculate assembly time and cost based on FFA results

## 📝 Text Files Created

### **additional_info_{assembly_name}.txt**
```
ASSEMBLY ANALYSIS NOTES
Generated: 2026-03-24 10:23:45

PRIMARY FUNCTION:
[User answer or extracted from analysis]

SUB-ASSEMBLIES:
[List]

HANDLING CONSTRAINTS:
[List]

SPECIAL NOTES:
[User notes]

---
Created by: PM Assembly Analyst (app_workflow)
Approval Status: user_verified / pending
```

### **remarks_{assembly_name}.txt**
```
SEQUENCE CORRECTION REMARKS
Generated: 2026-03-24 10:45:12

USER FEEDBACK:
Move step 3 before step 2 because the joining is easier if we position this part first.
Step 5 should be split into two sub-steps.

---
Processed: user_input_phase_2
Status: saved_for_regeneration
```

---

## 🎯 Entry Point: app_workflow.py

```python
# Usage
python app_workflow.py {assembly_name}
# OR
python app_workflow.py {assembly_name} --config configs/interactive_annotation/custom_config.yaml
```

**Returns:**
- Console output with interactive prompts
- Saved session state
- Final results in `data/session/{assembly_name}/output/`

---

## 📊 Session State (session_state.json)

```json
{
  "session_id": "uuid",
  "assembly_name": "IPA_Cranfield",
  "timestamp_started": "2026-03-24T10:00:00",
  "current_phase": 3,
  
  "phases_completed": {
    "phase_1_assembly_analysis": true,
    "phase_2_sequence_generation_v1": true,
    "phase_3_user_feedback": true,
    "phase_4_sequence_regeneration": false
  },
  
  "user_responses": {
    "assembly_function": "Bearing assembly mechanism",
    "sub_assemblies": ["outer ring", "inner ring", "bearing balls"],
    "sequence_corrections": "Move step 3 before step 2..."
  },
  
  "outputs": {
    "additional_info_path": "textbased_info/additional_info_IPA_Cranfield.txt",
    "remarks_path": "textbased_info/remarks_IPA_Cranfield.txt",
    "assembly_sequence_v1": "assembly_sequence_v1.json",
    "assembly_sequence_v2": "assembly_sequence.json",
    "ffa_assessment": "ffa_assessment/ffa_assessment.json"
  }
}
```

---

## 🚀 Future Enhancements

- **Phase 2**: Migrate .txt to JSON with backward compatibility
- **PM Agent Tools**: PDF reading, CAD metadata access, design database queries
- **FFA Expert Node**: Present FFA results to user, collect feedback
- **Workflow Export**: Convert final annotations to standard `run_experiments.py` format
- **Multi-Assembly**: Pipeline multiple assemblies with shared session

---

## 📌 Relationship to Existing Workflows

### `run_experiments.py` (LLM-Generated Sequence)
- **Independence**: app_workflow doesn't interfere with run_experiments
- **Compatibility**: Outputs can be fed into run_experiments later

### `run_experiments_sequence_gt.py` (GT-Structured Sequence)
- **Independence**: Separate workflows
- **Later**: app_workflow results could become GT input

### `agent/workflow.py` (Node Definitions)
- **Reuse**: app_workflow calls existing nodes
- **No Modification**: Existing workflow.py remains unchanged
- **Model Override**: Config allows per-node model selection

---

## ✅ **Implementation Decisions (Confirmed)**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Model Selection** | Option D: Global + node-specific overrides | Follow run_experiments_sequence_gt pattern |
| **Orchestration** | LangGraph StateGraph | Consistent with existing workflows |
| **Rendering** | Full both times | Simplest now, optimize later |
| **File Creation** | Option A: PM nodes save own files | Encapsulated, clear |
| **Session State** | Save at END | Cleaner, simpler |
| **Config Format** | YAML (load_experiment_settings) | Proven pattern |
| **Remarks Handling** | Pass to second sequence call | Direct context integration |

---

## ✅ Implementation Checklist

### **Phase 0: Setup**
- [ ] Create `configs/interactive_annotation/default_config.yaml`
- [ ] Add prompts to `configs/prompts.yaml`:
  - [ ] `PM_AssemblyAnalyst_system_v1`
  - [ ] `PM_AskAssemblyQuestions_v1`
  - [ ] `PM_SequenceAnalyst_system_v1`
  - [ ] `PM_ValidateSequence_v1`

### **Phase 1: Workflow Wrapper**
- [ ] Create `agent/workflow_wrapper.py`:
  - [ ] `run_workflow_until(app, datasource_root, target_phase, thread_id, remarks?)`
  - [ ] Checkpoint management logic
  - [ ] Phase detection + stopping logic

### **Phase 2: PM Agent**
- [ ] Create `agent/pm_agent.py`:
  - [ ] `PMAgentState` TypedDict
  - [ ] `build_pm_agent()` function
  - [ ] Nodes: analyze, recall_memory, ask_user, call_workflow, reflect
  - [ ] Tool: workflow_wrapper call integration

### **Phase 3: Entry Point**
- [ ] Create `app_workflow.py`:
  - [ ] `main(assembly_name, config_file?)`
  - [ ] Initialization logic
  - [ ] Console interaction
  - [ ] Session state save

### **Phase 4: Testing**
- [ ] Test workflow wrapper with existing workflow
- [ ] Test PM agent initialization
- [ ] Test Phase 1: Assembly questions
- [ ] Test Phase 2: Sequence generation
- [ ] Test Phase 3: User feedback + regeneration
- [ ] Test Phase 4: Final analysis
- [ ] Verify text file creation
- [ ] Verify session state saved correctly

---

## ✅ **Implementation Decisions (Updated)**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Agent Architecture** | PM Agent outside workflow + wrapper | Clean separation of concerns, agent has memory/reasoning |
| **Workflow Structure** | Existing workflow + stop points | No changes to node logic, minimal impact |
| **Orchestration** | Wrapper function + agent decides phases | Agent autonomously decides workflow progression |
| **Rendering Phase 2** | ISO-only (fast) | Speed, user can provide feedback before full render |
| **Rendering Phase 3** | Full rendering (all views) | Context for sequence regeneration |
| **File Creation** | Agent saves text files via wrapper | Explicit, traceable, part of conversation |
| **Session State** | Save at END | Simpler, matches existing pattern |
| **Config Format** | YAML (load_experiment_settings) | Proven pattern, consistency |
| **Remarks Handling** | Agent passes to wrapper → state update | Direct context integration |
| **Memory System** | Semantic store (PostgreSQL prod) | Learn patterns across assemblies |
| **Future Tools** | PDF reader, CAD metadata, design DB | Extensibility maintained |
