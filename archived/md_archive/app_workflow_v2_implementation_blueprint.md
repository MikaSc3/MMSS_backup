# app_workflow_v2.py Implementation Blueprint

**Based on code analysis**: workflow.py, prompt_store.py, Assembly_sequence_generation.py, tools.py

---

## 1. ARCHITECTURE PATTERNS

### 1.1 Node Function Signature (Langgraph-style)
```python
def node_name(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process state, update with outputs, return modified state.
    """
    # Read from state
    assembly_name = state.get("assembly_name")
    
    # Do work
    result = do_something(assembly_name)
    
    # Update and return state
    return {
        **state,  # Carry forward all keys
        "output_key": result,  # Add/overwrite specific keys
    }
```

### 1.2 State Management
- **Single shared dict** flows through entire workflow
- Each node reads what it needs, adds/updates keys
- **Key state variables** (from existing nodes):
  - `assembly_name`: str
  - `sequence_run_counter`: int (current iteration)
  - `previous_remarks_context`: Optional[str] (for regeneration)
  - `assembly_sequence_path`: str (path to assembled sequence JSON)
  - `assembly_sequence_data`: dict (parsed JSON)
  - `sequence_max_iterations`: int (from config)

### 1.3 Config Loading Pattern
```python
from agent.prompt_store import load_experiment_settings

# Called once at startup
settings = load_experiment_settings()
# Loads from (in priority order):
#   1. configs/default_settings.yaml
#   2. experiment.yaml
#   3. env var APA_EXPERIMENT_YAML

# Access settings anywhere:
max_iterations = settings.get("max_iterations", 5)
asg_system_id = settings.get("ASG_system_prompt_id")
```

### 1.4 Prompt Loading & Rendering Pattern
```python
from agent.prompt_store import get_system_and_human_prompts, render_prompt

settings = load_experiment_settings()

# For paired system/human prompts:
system_prompt, human_template = get_system_and_human_prompts("ASG", settings)
# Looks for: ASG_system_prompt_id, ASG_human_prompt_id in settings
# Falls back to: base_system_prompt_id for system prompt

# For single prompt:
prompt_text = render_prompt("my_prompt_id", assembly_name="Pump", steps=8)
# Format keys get substituted via str.format(**kwargs)
```

### 1.5 LLM Call Pattern (from Assembly_sequence_generation.py)
```python
from agent.tools import _get_img_describer_llm

# Get configured LLM client
llm = _get_img_describer_llm(max_completion_tokens=4000)

# With structured output
llm_structured = llm.with_structured_output(OutputSchema, include_raw=True)

# Build message (text + images)
user_content = [
    {"type": "text", "text": user_text},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
]

# Call
response = llm_structured.invoke([
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_content},
])
```

### 1.6 Remarks/Feedback Pattern (from generate_assembly_sequence)
```python
# On regeneration, previous remarks are loaded:
prev_run_dir = exp_output_dir_root / f"assembly_sequence_run{N-1}"
remarks_path = prev_run_dir / "remarks.json"
if remarks_path.exists():
    remarks_context = remarks_path.read_text()

# Then remarks_context is appended to user prompt:
user_text_parts.append(f"\n## Previous Validation Feedback:")
user_text_parts.append(remarks_context)
user_text = "\n".join(user_text_parts)
```

---

## 2. CONDITIONAL EDGES (Agent Approval)

### 2.1 Agent Return Format
```python
# Agent functions return a dict with:
{
    **state,  # Carry forward all state
    "approval": True/False,  # Did user approve?
    "user_feedback": Optional[str],  # Remarks if not approved
    "agent_action": "continue"|"next_phase"|"done",
}
```

### 2.2 Conditional Route Based on Agent Output
```python
# In main workflow loop:
agent_result = agent_2_validate_sequence(state)

if agent_result["approval"]:
    # Approved → move to Phase 4
    state = agent_result
    phase = "PHASE_4"
else:
    # Not approved → regenerate
    remarks = agent_result.get("user_feedback")
    state = {
        **agent_result,
        "previous_remarks_context": remarks,
        "sequence_run_counter": state["sequence_run_counter"] + 1,
    }
    # Loop: re-run Phase 2 with new remarks
    phase = "PHASE_2_REGENERATE"
```

---

## 3. WORKFLOW STRUCTURE FOR app_workflow_v2.py

### 3.1 Main Orchestrator Function
```python
def run_app_workflow_v2():
    """Single unified script managing all phases + agents."""
    
    config = load_and_validate_config()
    assembly_name = discover_assembly()
    session_root = setup_session(assembly_name)
    
    # Initialize shared state
    state = {
        "assembly_name": assembly_name,
        "session_root": str(session_root),
        "sequence_run_counter": 0,
        "config": config,
    }
    
    # Main state machine loop
    phase = "PHASE_1"
    max_phase_iterations = 100
    iteration = 0
    
    while phase != "DONE" and iteration < max_phase_iterations:
        iteration += 1
        print(f"\n[{iteration}] Current Phase: {phase}")
        
        if phase == "PHASE_1":
            state = run_phase_1(state)
            phase = "AGENT_1"
        
        elif phase == "AGENT_1":
            state = run_agent_1(state)
            phase = "PHASE_2"
        
        elif phase == "PHASE_2":
            state = run_phase_2(state)
            phase = "AGENT_2_LOOP"
        
        elif phase == "AGENT_2_LOOP":
            # Inner loop: keep asking Agent 2 until approval
            while True:
                state = run_agent_2_validate(state)
                if state.get("approval"):
                    phase = "PHASE_4"
                    break
                else:
                    # Regenerate with remarks
                    remarks = state.get("user_feedback")
                    state["previous_remarks_context"] = remarks
                    state["sequence_run_counter"] += 1
                    if state["sequence_run_counter"] >= state.get("sequence_max_iterations", 5):
                        # Force approval
                        print("Max iterations reached, forcing approval")
                        state["approval"] = True
                        phase = "PHASE_4"
                        break
                    # Re-run Phase 2 with updated remarks
                    state = run_phase_2(state)
        
        elif phase == "PHASE_4":
            state = run_phase_4(state)
            phase = "AGENT_3"
        
        elif phase == "AGENT_3":
            state = run_agent_3(state)
            # Agent 3 may request revision (Phase 5)
            if state.get("wants_revision"):
                phase = "PHASE_2"  # Regenerate with FFA context
            else:
                phase = "DONE"
    
    return state
```

---

## 4. INDIVIDUAL PHASE IMPLEMENTATIONS

### 4.1 Phase 1: Preprocessing
```python
def run_phase_1(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stepparser preprocessing."""
    assembly_name = state["assembly_name"]
    session_root = Path(state["session_root"])
    
    # Step 1a: Run stepparser
    preprocessing_dir = session_root / "preprocessing" / "stepparser" / assembly_name
    if not preprocessing_dir.exists():
        # Call stepparser
        processor = StepProcessor(...)
        processor.process_all_step_files()
    
    # Step 1b: Resolve paths (from existing node)
    resolved_paths = _node_resolve_paths({
        "datasource_root": str(preprocessing_dir),
    })
    
    # Step 1c: Run initial assembly analysis (AAI node)
    assembly_analysis = _node_run_assembly({
        **resolved_paths,
        "config": state["config"],
    })
    
    # Save v1 assembly metadata
    metadata_file = session_root / f"{assembly_name}-Metadata_assembly_enriched.json"
    metadata_file.write_text(json.dumps(assembly_analysis.get("assembly_metadata"), indent=2))
    
    return {
        **state,
        **resolved_paths,
        **assembly_analysis,
    }
```

### 4.2 Phase 2: Enrichment & Sequence Generation
```python
def run_phase_2(state: Dict[str, Any]) -> Dict[str, Any]:
    """Full enrichment + sequence generation."""
    
    # Reuse existing nodes from workflow.py
    from agent.workflow import (
        _node_run_assembly,
        _node_list_parts,
        _node_run_monoparts,
        _node_merge_copy_part_data,
        _node_merge_bom,
        _node_generate_assembly_sequence,
    )
    
    # 2a: Full assembly analysis (inject Agent 1 context)
    additional_info = (Path(state["session_root"]) / "Agent_txt_files" / "additional_info.txt").read_text()
    state["assembly_analyst_context"] = additional_info
    
    state = _node_run_assembly(state)  # Uses config + context
    
    # 2b-2e: Monoparts + BOM
    state = _node_list_parts(state)
    state = _node_run_monoparts(state)
    state = _node_merge_copy_part_data(state)
    state = _node_merge_bom(state)
    
    # 2f: Generate sequence (or regenerate with remarks)
    state = _node_generate_assembly_sequence(state)
    
    return state
```

### 4.3 Phase 4: Rendering + Quality
```python
def run_phase_4(state: Dict[str, Any]) -> Dict[str, Any]:
    """Rendering + interaction analysis + FFA."""
    
    from agent.workflow import (
        _node_render_assembly_steps,
        _node_interaction_analysis,
        _node_assess_ffa,
    )
    
    state = _node_render_assembly_steps(state)
    state = _node_interaction_analysis(state)
    state = _node_assess_ffa(state)
    
    return state
```

---

## 5. AGENT IMPLEMENTATIONS

### 5.1 Agent 1: Assembly Analyst (Non-interactive)
```python
def run_agent_1(state: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 1 analyzes assembly, provides notes."""
    
    settings = state.get("config", {})
    system_prompt, human_template = get_system_and_human_prompts("AGENT1", settings)
    
    # Prepare prompt
    assembly_metadata = json.loads(
        (Path(state["session_root"]) / f"{state['assembly_name']}-Metadata_assembly_enriched.json").read_text()
    )
    
    user_text = human_template.format(
        assembly_name=state["assembly_name"],
        assembly_metadata=json.dumps(assembly_metadata, indent=2),
    )
    
    # Call LLM
    llm = _get_img_describer_llm(max_completion_tokens=2000)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ])
    
    # Save response
    agent_txt_dir = Path(state["session_root"]) / "Agent_txt_files"
    agent_txt_dir.mkdir(parents=True, exist_ok=True)
    (agent_txt_dir / "additional_info.txt").write_text(response.content)
    
    return state
```

### 5.2 Agent 2: Sequence Validator (Interactive Loop)
```python
def run_agent_2_validate(state: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 2 validates sequence, gets user approval."""
    
    settings = state.get("config", {})
    system_prompt, human_template = get_system_and_human_prompts("AGENT2", settings)
    
    # Load current sequence
    run_num = state["sequence_run_counter"]
    seq_path = Path(state["session_root"]) / f"assembly_sequence_run{run_num}" / "assembly_sequence.json"
    sequence_data = json.loads(seq_path.read_text())
    
    user_text = human_template.format(
        assembly_name=state["assembly_name"],
        sequence=json.dumps(sequence_data, indent=2),
        previous_remarks=state.get("previous_remarks_context", ""),
    )
    
    # Call LLM
    llm = _get_img_describer_llm(max_completion_tokens=3000)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ])
    
    # Parse response for approval
    approval_keywords = settings.get("approval_keywords", ["approve", "done", "this is fine"])
    is_approved = any(kw in response.content.lower() for kw in approval_keywords)
    
    # Save remarks
    agent_txt_dir = Path(state["session_root"]) / "Agent_txt_files"
    remarks_file = agent_txt_dir / f"remarks_iteration_{state['sequence_run_counter']}.txt"
    remarks_file.write_text(response.content)
    
    if is_approved:
        (agent_txt_dir / "remarks_iteration_final.txt").write_text(response.content)
    
    return {
        **state,
        "approval": is_approved,
        "user_feedback": response.content,  # Extract structured feedback if needed
    }
```

### 5.3 Agent 3: FFA Explainer (Non-interactive)
```python
def run_agent_3(state: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 3 explains FFA results, asks for revisions."""
    
    settings = state.get("config", {})
    system_prompt, human_template = get_system_and_human_prompts("AGENT3", settings)
    
    # Load FFA assessment
    ffa_path = Path(state["session_root"]) / "ffa_assessment" / "ffa_assessment.json"
    ffa_data = json.loads(ffa_path.read_text())
    
    user_text = human_template.format(
        assembly_name=state["assembly_name"],
        ffa_assessment=json.dumps(ffa_data, indent=2),
    )
    
    # Call LLM
    llm = _get_img_describer_llm(max_completion_tokens=2000)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ])
    
    # Save summary
    agent_txt_dir = Path(state["session_root"]) / "Agent_txt_files"
    (agent_txt_dir / "ffa_summary.txt").write_text(response.content)
    
    # Check for revision keywords
    revision_keywords = settings.get("revision_keywords", ["regenerate", "redo", "try again"])
    wants_revision = any(kw in response.content.lower() for kw in revision_keywords)
    
    return {
        **state,
        "wants_revision": wants_revision,
        "ffa_summary": response.content,
    }
```

---

## 6. PROMPT TEMPLATES (prompts_app.yaml)

```yaml
# New separate file: configs/prompts_app.yaml

prompts:
  agent1_system: |
    You are an assembly engineering expert analyzing CAD assemblies.
    ...
  
  agent1_user: |
    Analyze this assembly: {assembly_name}
    Metadata: {assembly_metadata}
    ...
  
  agent2_system: |
    You help users validate and refine assembly sequences.
    ...
  
  agent2_user: |
    Here's the assembly sequence for {assembly_name}:
    {sequence}
    
    Previous feedback: {previous_remarks}
    
    Does this look correct? Any changes needed?
  
  agent3_system: |
    You explain automation fitness assessment results clearly.
    ...
  
  agent3_user: |
    Assessment for {assembly_name}:
    {ffa_assessment}
    ...
```

---

## 7. KEY UTILITIES ALREADY AVAILABLE

| Function | Module | Purpose |
|----------|--------|---------|
| `_node_run_assembly` | workflow.py | Analyze assembly via LLM |
| `_node_run_monoparts` | workflow.py | Analyze individual parts |
| `_node_merge_bom` | workflow.py | Merge BOM data |
| `_node_generate_assembly_sequence` | workflow.py | Generate sequence (handles remarks) |
| `_node_render_assembly_steps` | workflow.py | Render step images |
| `_node_interaction_analysis` | workflow.py | Analyze part interactions |
| `_node_assess_ffa` | workflow.py | FFA assessment |
| `load_experiment_settings` | prompt_store.py | Load config from YAML |
| `get_system_and_human_prompts` | prompt_store.py | Load prompt pairs |
| `render_prompt` | prompt_store.py | Format prompt with kwargs |
| `_get_img_describer_llm` | tools.py | Get configured LLM client |

---

## 8. ENVIRONMENT SETUP REQUIRED

```bash
# Python environment
source venv/Scripts/activate

# Environment variables
export APA_EXPERIMENT_OUTPUT_DIR=/path/to/session_root
export APA_EXPERIMENT_YAML=configs/appconfig/appconfig.yaml
export AZURE_ENDPOINT_4O=https://...
export API_KEY_GPT_4=sk-...
```

---

## 9. STATE FLOW DIAGRAM

```
[Start]
  ↓
[PHASE_1: Preprocessing]
  ↓
[AGENT_1: Assembly Analysis]
  ↓
[PHASE_2: Enrichment]
  ↓
[AGENT_2 Loop]
  ├─→ User approves? ──→ YES ──→ [PHASE_4: Quality Assessment]
  └─→ User gives feedback? ──→ YES ──→ [Update remarks] ──→ [PHASE_2 regenerate] ──→ [AGENT_2 again]
                                (repeat until max_iterations or approval)
  ↓
[AGENT_3: FFA Explanation]
  ├─→ User wants revision? ──→ YES ──→ [Update FFA context] ──→ [PHASE_2 regenerate] ──→ [Agent 2 loop again]
  └─→ User satisfied? ──→ YES ──→ [DONE]
```

---

## 10. SUMMARY: WHAT'S CLEAR

✅ Node reuse pattern (state dict, return modified state)
✅ Config loading (load_experiment_settings)
✅ Prompt loading (get_system_and_human_prompts, render_prompt)
✅ LLM calling (_get_img_describer_llm)
✅ Remarks/feedback handling (append to user prompt)
✅ Run counter management (sequence_run_counter increments)
✅ Agent interaction (return approval boolean + feedback)
✅ State machine (conditional edges based on agent decisions)

---

## 11. IMPLEMENTATION READINESS

| Component | Status | Notes |
|-----------|--------|-------|
| Phase 1 code | 🟢 Clear | Reuse stepparser + existing nodes |
| Phase 2 code | 🟢 Clear | Reuse all enrichment nodes |
| Phase 4 code | 🟢 Clear | Reuse rendering + FFA nodes |
| Agent 1 code | 🟡 Template ready | Need to finalize prompts |
| Agent 2 code | 🟡 Template ready | Need approval keyword list |
| Agent 3 code | 🟡 Template ready | Need revision keyword list |
| prompts_app.yaml | 🔴 To create | Define AGENT1/2/3 prompts |
| appconfig.yaml | 🟢 Spec ready | Use template from app_workflow_v2.md |
| Main orchestrator | 🟡 Architecture clear | Need to implement loop logic |

---

**Ready to implement?** All patterns are clear from code analysis.
