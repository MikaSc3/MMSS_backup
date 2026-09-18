# app_workflow_v2: Interactive Assembly Analysis Workflow

**Status**: Ready for Testing  
**Date**: 2026-03-24  
**Architecture**: Single-script orchestrator with multi-agent interaction

---

## Quick Start

```bash
# Activate environment
source venv/Scripts/activate

# Prepare a STEP file
cp my_assembly.STEP data/input/

# Run the workflow
python app_workflow_v2.py

# Or with custom config
python app_workflow_v2.py --config configs/appconfig/appconfig.yaml
```

---

## What Gets Created

```
data/sessions/{timestamp}_{assembly_name}/
├── input/
│   └── {assembly_name}.STEP
│
├── preprocessing/
│   └── stepparser/{assembly_name}/
│       ├── assembly_{assembly_name}/
│       │   ├── assembly_{assembly_name}_BOM.json
│       │   ├── images/
│       │   │   ├── iso1_transp_0_0.png
│       │   │   ├── iso1_exp_transp_0_0.png
│       │   │   └── ...
│       └── Part_1/, Part_2/, ...
│
├── Agent_txt_files/
│   ├── additional_info.txt           (Agent 1 output)
│   ├── remarks_iteration_1.txt       (Agent 2 feedback, iteration 1)
│   ├── remarks_iteration_2.txt       (Agent 2 feedback, iteration 2)
│   ├── remarks_iteration_final.txt   (Agent 2 approval)
│   └── ffa_summary.txt               (Agent 3 output)
│
├── {assembly_name}-Metadata_assembly_enriched.json
│
├── enriched_parts/
│   ├── Part_1-Metadata_enriched.json
│   ├── Part_1_Data_enriched_merged.json
│   ├── Part_2-Metadata_enriched.json
│   └── ...
│
├── {assembly_name}_BOM_enriched.json
│
├── assembly_sequence_run1/
│   ├── assembly_sequence.json
│   ├── sequence_renderings/
│   │   ├── step_1.png
│   │   ├── step_2.png
│   │   └── ...
│   └── remarks.json                 (User feedback for regeneration)
│
├── assembly_sequence_run2/          (If regenerated)
│   └── ...
│
├── interaction_analysis.json
│
└── ffa_assessment/
    └── ffa_assessment.json
```

---

## Workflow Phases

### Phase 1: Preprocessing
- **Runs**: Stepparser (creates 3D renderings + metadata)
- **Reuses**: `_node_resolve_paths`, `_node_run_assembly`
- **Output**: Assembly metadata (v1)

### Agent 1: Assembly Analyst
- **Role**: Non-interactive LLM analyzes assembly structure
- **Prompt**: From `prompts_app.yaml` → `agent1_user`
- **Output**: `Agent_txt_files/additional_info.txt`

### Phase 2: Enrichment & Sequence Generation
- **Reuses**: All 6 enrichment nodes from `workflow.py`:
  - `_node_run_assembly` (inject Agent 1 context)
  - `_node_list_parts`
  - `_node_run_monoparts`
  - `_node_merge_copy_part_data`
  - `_node_merge_bom`
  - `_node_generate_assembly_sequence` (handles remarks internally)
- **Output**: Enriched metadata, BOM, sequence JSON + renderings

### Agent 2: Sequence Validator (Interactive Loop)
- **Role**: User-interactive sequence validation
- **Input**: Current sequence, previous feedback
- **Interaction**:
  1. Present sequence to user
  2. Wait for user input
  3. If approval keyword (approve, done, ok, etc.) → move to Phase 4
  4. Else → save feedback, regenerate Phase 2, loop again
- **Max iterations**: 5 (configurable)
- **Output**: `Agent_txt_files/remarks_iteration_*.txt`, `remarks.json`

### Phase 4: Rendering + Quality Assessment
- **Reuses**: `_node_render_assembly_steps`, `_node_interaction_analysis`, `_node_assess_ffa`
- **Output**: Step renderings, interaction analysis, FFA scores

### Agent 3: FFA Explainer
- **Role**: Explain automation fitness results
- **Interaction**: Explain scores, show bottlenecks, ask if user wants revisions
- **Optional Phase 5**: If user wants revision, regenerate Phase 2 again
- **Output**: `Agent_txt_files/ffa_summary.txt`

---

## Configuration

### Main Config: `configs/appconfig/appconfig.yaml`

**Key settings**:
- `llm_model`: LLM to use (4o, 4.1, 5.4)
- `phase_3.max_iterations`: Max sequence refinement loops
- `phase_3.approval_keywords`: List of approval trigger words
- `image_downscale_factor`: Speed/quality tradeoff

**All toggles**:
- `phase_1.enable_*`, `phase_2.enable_*`, `phase_4.enable_*`
- `agents.*`: Role descriptions, context limits
- `persistence.*`: Approval behavior, write permissions

### Prompts: `configs/prompts_app.yaml`

Three agent prompt pairs:
- `agent1_system` / `agent1_user` → Assembly analysis
- `agent2_system` / `agent2_user` → Sequence validation
- `agent3_system` / `agent3_user` → FFA explanation

---

## Environment Variables

```bash
# Optional (defaults to configs/appconfig/appconfig.yaml)
export APA_APP_CONFIG=path/to/config.yaml

# Set by workflow (nodes use this)
export APA_EXPERIMENT_OUTPUT_DIR=path/to/session/root

# Required (from .env file)
export AZURE_ENDPOINT_4O=https://...
export API_KEY_GPT_4=sk-...
```

---

## Code Structure

```
app_workflow_v2.py
├── setup_paths()                      # Workspace setup
├── load_config()                      # Load YAML config
├── discover_assembly()                # Find .STEP file
├── setup_session()                    # Create session folder
│
├── load_prompt_library()              # Load prompts_app.yaml
├── render_prompt()                    # Format template with kwargs
├── get_llm_client()                   # Get Azure OpenAI client
│
├── run_phase_1()                      # Preprocessing
├── run_agent_1()                      # Assembly analysis
├── run_phase_2()                      # Enrichment (reuses nodes)
├── run_agent_2_loop()                 # Sequence validation loop
├── run_phase_4()                      # Quality assessment
├── run_agent_3()                      # FFA explanation
│
└── run_app_workflow_v2()              # Main orchestrator (state machine)
```

---

## Reused Nodes (NOT Modified)

All existing nodes are **imported as-is** from `agent/workflow.py`:

```python
from agent.workflow import (
    _node_resolve_paths,
    _node_run_assembly,
    _node_list_parts,
    _node_run_monoparts,
    _node_merge_copy_part_data,
    _node_merge_bom,
    _node_generate_assembly_sequence,      # Handles remarks internally ✓
    _node_render_assembly_steps,
    _node_interaction_analysis,
    _node_assess_ffa,
)
```

Each node is called with state dict, updates with outputs, returned.

---

## State Dictionary

Shared across all phases/agents:

```python
state = {
    "assembly_name": str,                    # "MyAssembly"
    "session_root": str,                     # "/path/to/session"
    "sequence_run_counter": int,             # Current iteration (1, 2, 3, ...)
    "config": Dict,                          # Loaded from appconfig.yaml
    
    # Phase 1 outputs
    "datasource_root": str,
    "assembly_dir": str,
    "part_dirs": List[str],
    
    # Phase 2 outputs
    "assembly_sequence_path": str,
    "assembly_sequence_data": Dict,
    
    # Agent outputs
    "agent1_context": str,
    "approval": bool,
    "user_feedback": str,
    "wants_revision": bool,
    
    # Remarks for regeneration
    "previous_remarks_context": str,
    
    # ... plus all keys added by reused nodes
}
```

---

## Safety Safeguards

✅ **No modifications to existing nodes** - All imported as-is
✅ **State dict pattern** - Same as existing workflow.py
✅ **Environment variable usage** - `APA_EXPERIMENT_OUTPUT_DIR` set properly
✅ **Error handling** - Try/except blocks in each phase
✅ **Max iterations** - Config `phase_3.max_iterations` prevents infinite loops
✅ **Safe fallbacks** - Missing prompts don't crash, just warn

---

## Testing Checklist

- [ ] Phase 1: Stepparser runs successfully
- [ ] Phase 1: Assembly metadata created
- [ ] Agent 1: LLM call works, `additional_info.txt` written
- [ ] Phase 2: All nodes execute without error
- [ ] Phase 2: `assembly_sequence_run1/` created
- [ ] Agent 2: User can input feedback
- [ ] Agent 2: Loop regenerates Phase 2 on feedback
- [ ] Agent 2: Approval keyword triggers Phase 4
- [ ] Phase 4: Rendering, interaction, FFA complete
- [ ] Agent 3: FFA summary generated
- [ ] Agent 3: Revision keyword triggers Phase 5 regeneration

---

## Troubleshooting

**"Metadata file not found"**
- Ensure Phase 1 completed successfully
- Check `session_root/{assembly_name}-Metadata_assembly_enriched.json` exists

**"Sequence file not found"**
- Ensure Phase 2 completed successfully
- Check `session_root/assembly_sequence_run{N}/assembly_sequence.json` exists

**"Prompt template not found"**
- Verify `configs/prompts_app.yaml` exists
- Check prompt ID in error message matches YAML keys

**"LLM API error"**
- Check Azure endpoint and API key in .env
- Verify `APA_EXPERIMENT_OUTPUT_DIR` is set before nodes run

---

## Next Steps

1. **Test with a small assembly** (2-3 parts)
2. **Iterate on prompt templates** in `prompts_app.yaml`
3. **Adjust config** in `configs/appconfig/appconfig.yaml` as needed
4. **Scale to larger assemblies** once working

---

**Version**: 1.0  
**Ready**: Yes ✓
