# -*- coding: utf-8 -*-
"""
app_workflow_v2.py

Interactive Assembly Analysis Workflow with Multi-Agent Orchestration

Architecture:
  - Single unified script handling all phases + agents
  - State machine orchestration (not file-based polling)
  - Agent 2 loop: interactive sequence refinement until user approval
  - Conditional edges: agent approval decisions route workflow
  - Reuses 11 existing workflow nodes, no modifications

Phases:
  Phase 1: Preprocessing (Stepparser + initial analysis)
  Phase 2: Enrichment + sequence generation
  Agent 2: Interactive sequence validation loop
  Phase 4: Rendering + quality assessment (FFA)
  Agent 3: FFA explanation + optional revision trigger

Usage:
    python scripts/app_workflow_v2.py
    python scripts/app_workflow_v2.py --config configs/appconfig/appconfig.yaml
    python scripts/app_workflow_v2.py --assembly my_assembly --session path/to/session
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

# ============================================================================
# FORCE UTF-8 ENCODING (Fix for Windows terminal Unicode issues)
# ============================================================================

if sys.platform == "win32":
    # Force UTF-8 output on Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# ============================================================================
# ENVIRONMENT & CONFIG SETUP
# ============================================================================

def setup_paths():
    """Ensure workspace root is in path."""
    workspace_root = Path(__file__).resolve().parent.parent
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    return workspace_root


WORKSPACE_ROOT = setup_paths()


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load application configuration from YAML.
    
    Priority:
      1. Provided config_path
      2. Environment variable APA_APP_CONFIG
      3. Default: configs/appconfig/appconfig.yaml
    """
    if config_path is None:
        config_path = os.environ.get("APA_APP_CONFIG")
        if config_path:
            config_path = Path(config_path)
        else:
            config_path = WORKSPACE_ROOT / "configs" / "appconfig" / "appconfig.yaml"
    
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = WORKSPACE_ROOT / config_path
    
    print(f"[CONFIG] Loading: {config_path}")
    
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        print(f"[CONFIG] [OK] Loaded successfully")
        return config
    except Exception as e:
        print(f"[CONFIG] [ERROR] {e}")
        raise


# ============================================================================
# ASSEMBLY DISCOVERY & SESSION SETUP
# ============================================================================

def discover_assembly(input_dir: Optional[Path] = None) -> str:
    """Discover assembly name from input/ folder.
    
    Looks for .STEP files in data/input/ directory.
    Returns the first assembly name found.
    """
    if input_dir is None:
        input_dir = WORKSPACE_ROOT / "data" / "input"
    
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    
    step_files = list(input_dir.glob("*.STEP"))
    if not step_files:
        raise FileNotFoundError(f"No .STEP files found in {input_dir}")
    
    assembly_name = step_files[0].stem
    print(f"[ASSEMBLY] Discovered: {assembly_name}")
    return assembly_name


def setup_session(assembly_name: str, session_dir: Optional[Path] = None) -> Path:
    """Create session directory structure.
    
    Structure:
      session_root/
        ├── input/
        ├── preprocessing/
        ├── Agent_txt_files/
        ├── assembly_sequence_run{N}/
        ├── enriched_parts/
        ├── ffa_assessment/
      
    Sets environment variable: APA_EXPERIMENT_OUTPUT_DIR
    """
    if session_dir is None:
        session_dir = WORKSPACE_ROOT / "data" / "sessions"
    
    session_dir = Path(session_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    session_root = session_dir / f"{timestamp}_{assembly_name}"
    
    # Create subdirectories
    for subdir in ["input", "preprocessing", "Agent_txt_files", "enriched_parts", "ffa_assessment"]:
        (session_root / subdir).mkdir(parents=True, exist_ok=True)
    
    # Copy input STEP file to session/input/ if not already there
    input_source = WORKSPACE_ROOT / "data" / "input" / f"{assembly_name}.STEP"
    input_target = session_root / "input" / f"{assembly_name}.STEP"
    if input_source.exists() and not input_target.exists():
        print(f"[SESSION] Copying STEP file: {input_source.name}")
        import shutil
        shutil.copy2(input_source, input_target)
    
    # Set environment variable for existing nodes to use
    os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(session_root)
    
    print(f"[SESSION] Root: {session_root}")
    return session_root


# ============================================================================
# PROMPT LOADING
# ============================================================================

def load_prompt_library(library_name: str = "prompts.yaml") -> Dict[str, str]:
    """Load prompt templates from YAML file.
    
    Prompts are consolidated in configs/prompts.yaml.
    """
    prompts = {}
    
    # First: Try to load the requested library
    prompt_file = WORKSPACE_ROOT / "configs" / library_name
    if prompt_file.exists():
        try:
            import yaml
            with open(prompt_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            if "prompts" in data:
                for prompt_id, content in data["prompts"].items():
                    if isinstance(content, str):
                        prompts[prompt_id] = content
                    elif isinstance(content, dict) and "text" in content:
                        prompts[prompt_id] = content["text"]
            
            print(f"[PROMPTS] [OK] Loaded {len(prompts)} templates from {library_name}")
        except Exception as e:
            print(f"[PROMPTS] [ERROR] loading {library_name}: {e}")
    else:
        print(f"[PROMPTS] [WARN] File not found: {prompt_file}")
    
    return prompts


def render_prompt(prompt_id: str, prompt_library: Dict[str, str], **kwargs) -> Optional[str]:
    """Render a prompt template with format kwargs."""
    if prompt_id not in prompt_library:
        print(f"[PROMPT] [ERROR] Template not found: {prompt_id}")
        return None
    
    template = prompt_library[prompt_id]
    try:
        return template.format(**kwargs)
    except KeyError as e:
        print(f"[PROMPT] ✗ Missing format key: {e}")
        return None


# ============================================================================
# LLM SETUP
# ============================================================================

def get_llm_client(config: Dict[str, Any]):
    """Get Azure OpenAI LLM client.
    
    Uses existing tools.py infrastructure.
    """
    try:
        from agent.tools import _get_img_describer_llm
        
        llm = _get_img_describer_llm(max_completion_tokens=4000)
        print(f"[LLM] ✓ Initialized (model={config.get('llm_model', '4o')})")
        return llm
    except Exception as e:
        print(f"[LLM] ✗ ERROR: {e}")
        raise


# ============================================================================
# PHASE 1: PREPROCESSING
# ============================================================================

def run_phase_1(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 1: Preprocessing + Initial Assembly Analysis.
    
    Steps:
      1. Run stepparser (if needed)
      2. Resolve paths
      3. Run initial assembly analysis (AAI)
    """
    print(f"\n{'='*80}")
    print(f"PHASE 1: PREPROCESSING + INITIAL ASSEMBLY ANALYSIS")
    print(f"{'='*80}")
    
    assembly_name = state["assembly_name"]
    session_root = Path(state["session_root"])
    config = state.get("config", {})

    def emit_phase(phase_name: str):
        callback = state.get("_ui_callback")
        if callback:
            try:
                callback("phase_changed", phase=phase_name)
            except Exception as e:
                print(f"[PHASE 1 UI] Error: {e}")
    
    # Step 1a: Stepparser preprocessing
    print(f"\n[Phase 1a] Stepparser preprocessing...")
    emit_phase("PHASE_1_STEPPARSER")
    configured_stepparser_root = os.environ.get("APA_STEPPARSER_OUTPUT_FOLDER")
    if configured_stepparser_root:
        stepparser_output_root = Path(configured_stepparser_root)
        if not stepparser_output_root.is_absolute():
            stepparser_output_root = WORKSPACE_ROOT / stepparser_output_root
    else:
        stepparser_output_root = session_root / "preprocessing" / "stepparser"
    preprocessing_dir = stepparser_output_root / assembly_name
    
    if not preprocessing_dir.exists():
        print(f"[Phase 1a] Running stepparser for {assembly_name}...")
        try:
            from stepparser.processor import StepProcessor
            
            input_step = session_root / "input" / f"{assembly_name}.STEP"
            processor = StepProcessor(
                input_folder=str((session_root / "input")),
                output_folder=str(stepparser_output_root),
                skip_if_processed=True,
                color_mode="geometry",
                transparency_values=[0.0],
                headless_mode=config.get("rendering_headless_mode", True),
            )
            processor.process_all_step_files()
            print(f"[Phase 1a] ✓ Stepparser complete")
        except Exception as e:
            print(f"[Phase 1a] ✗ ERROR: {e}")
            raise
    else:
        print(f"[Phase 1a] ✓ Already processed, skipping stepparser")
    
    # Step 1a-copy: Copy preprocessed data to standard location for nodes to find
    print(f"\n[Phase 1a-copy] Ensuring data in standard location...")
    try:
        import shutil
        standard_location = WORKSPACE_ROOT / "data" / "processed" / "stepparser" / assembly_name
        
        # If not already there, create symlink or copy
        if preprocessing_dir.resolve() == standard_location.resolve():
            print(f"[Phase 1a-copy] ✓ Standard location is active output")
        elif configured_stepparser_root or not standard_location.exists():
            standard_location.parent.mkdir(parents=True, exist_ok=True)
            # Copy the entire preprocessed directory to standard location
            shutil.copytree(preprocessing_dir, standard_location, dirs_exist_ok=True)
            print(f"[Phase 1a-copy] ✓ Copied to {standard_location}")
            
            # Verify: check what's inside
            if standard_location.exists():
                contents = list(standard_location.glob("*"))
                print(f"[Phase 1a-copy]   Contents: {[p.name for p in contents]}")
                assembly_subdir = standard_location / f"assembly_{assembly_name}"
                if assembly_subdir.exists():
                    print(f"[Phase 1a-copy]   ✓ Found assembly subdir: {assembly_subdir.name}")
                else:
                    print(f"[Phase 1a-copy]   WARNING: Expected assembly subdir not found")
        else:
            print(f"[Phase 1a-copy] ✓ Already available at standard location")
    except Exception as e:
        print(f"[Phase 1a-copy] ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 1b: Resolve paths
    print(f"\n[Phase 1b] Resolving paths...")
    emit_phase("PHASE_1_PATHS")
    try:
        from agent.workflow import _node_resolve_paths
        
        # Prepare minimal state for path resolution
        path_state = {
            "datasource_root": str(preprocessing_dir),
        }
        result = _node_resolve_paths(path_state)
        state.update(result)
        print(f"[Phase 1b] ✓ Paths resolved")
        print(f"[Phase 1b]   assembly_dir={state.get('assembly_dir')}")
        print(f"[Phase 1b]   part_dirs={len(state.get('part_dirs', []))}")
    except Exception as e:
        print(f"[Phase 1b] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    # Step 1c: Run initial assembly analysis
    print(f"\n[Phase 1c] Initial assembly analysis...")
    emit_phase("PHASE_1_ANALYSIS")
    try:
        from agent.workflow import _node_run_assembly
        
        result = _node_run_assembly(state)
        state.update(result)
        print(f"[Phase 1c] ✓ Assembly analysis complete")
    except Exception as e:
        print(f"[Phase 1c] ✗ ERROR: {e}")
        raise
    
    print(f"\n[Phase 1] [OK] COMPLETE\n")
    return state


# ============================================================================
# AGENT 1: ASSEMBLY ANALYST
# ============================================================================

def run_agent_1(state: Dict[str, Any], prompt_library: Dict[str, str], input_queue=None, ui_callback=None) -> Dict[str, Any]:
    """Agent 1: Assembly Analyst - Multi-turn LLM conversation with optional UI input queue.
    
    Uses Phase 2a enriched data:
    1. Load Overview_Enriched.json and BOM
    2. Initial LLM analysis (3 sentences + function)
    3. Multi-turn conversation loop:
       - If input_queue provided: reads user input from queue (UI mode)
       - If input_queue is None: auto-proceeds (non-interactive mode)
    4. Save full conversation
    
    Args:
        state: Workflow state
        prompt_library: Prompt library
        input_queue: Optional queue.Queue for user input from UI
        ui_callback: Optional callback for UI updates
    
    Next Phase: Phase 2b (sequence generation) triggers automatically
    """
    from agent.agent_managers import Agent1
    
    print(f"\n{'='*80}")
    print(f"AGENT 1: ASSEMBLY ANALYST")
    print(f"{'='*80}")
    
    if ui_callback:
        ui_callback("message", role="system", content="🤖 Agent 1: Assembly Analyst starting...")
    
    try:
        assembly_name = state["assembly_name"]
        session_root = Path(state["session_root"])
        llm_model = state.get("llm_model", "4o")
        
        agent_txt_dir = session_root / "Agent_txt_files"
        agent_txt_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize agent
        agent = Agent1(llm_model=llm_model)
        
        # Load assembly data
        print(f"\n[Agent 1] Loading enriched overview and BOM...")
        agent.load_assembly_data(
            assembly_name=assembly_name,
            session_root=session_root,
            workspace_root=WORKSPACE_ROOT
        )
        
        # Get system prompt
        system_prompt = prompt_library.get("agent1_system", 
            "You are an expert mechanical engineer analyzing assemblies. Be precise and concise.")
        
        # Run multi-turn conversation with optional input queue
        result = agent.run(
            system_prompt=system_prompt,
            max_turns=20,
            input_queue=input_queue,
            ui_callback=ui_callback
        )
        
        # Save conversation
        agent.save_conversation(
            filepath=agent_txt_dir / "Agent1_conversation.txt"
        )
        
        print(f"\n[Agent 1] [OK] Analysis and conversation complete\n")
        
        if ui_callback:
            ui_callback("status", content="✓ Agent 1 complete, proceeding to Phase 2a enrichment")
        
        return state
    
    except Exception as e:
        print(f"[Agent 1] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        if ui_callback:
            ui_callback("error", content=f"Agent 1 failed: {str(e)}")
        return state


# ============================================================================
# PHASE 2: ENRICHMENT & SEQUENCE GENERATION
# ============================================================================

def run_phase_2a_only(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 2a: Only run assembly enrichment (for Agent 1 to use).
    
    Reuses:
      - run_assembly (full LLM analysis)
    """
    print(f"\n{'='*80}")
    print(f"PHASE 2a: ASSEMBLY ENRICHMENT")
    print(f"{'='*80}")
    
    try:
        from agent.workflow import _node_run_assembly
        
        print(f"\n[Phase 2a] Full assembly analysis...")
        state = _node_run_assembly(state)
        print(f"[Phase 2a] [OK] Complete")
        print(f"[Phase 2a]   assembly_result keys: {list(state.get('assembly_result', {}).keys())[:5]}...")
        
    except Exception as e:
        print(f"[Phase 2a] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    return state


def run_phase_2b_onwards(state: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 2b onwards: Continue with monoparts, BOM, sequence.
    
    Reuses existing nodes:
      - list_parts
      - run_monoparts
      - merge_copy_part_data
      - merge_bom
      - generate_assembly_sequence (includes remarks handling)
    """
    print(f"\n{'='*80}")
    print(f"PHASE 2b-2f: MONOPARTS, BOM & SEQUENCE GENERATION")
    print(f"{'='*80}")

    def emit_phase(phase_name: str):
        callback = state.get("_ui_callback")
        if callback:
            try:
                callback("phase_changed", phase=phase_name)
            except Exception as e:
                print(f"[PHASE 2 UI] Error: {e}")

    def emit_progress(step: int, status_text: str = None):
        callback = state.get("_ui_callback")
        if callback:
            try:
                callback("progress", step=step)
                if status_text:
                    callback("status", content=status_text)
            except Exception as e:
                print(f"[PHASE 2 UI] Error: {e}")
    
    try:
        from agent.workflow import (
            _node_list_parts,
            _node_run_monoparts,
            _node_merge_copy_part_data,
            _node_merge_bom,
            _node_generate_assembly_sequence,
        )
        
        # 2b: List parts
        print(f"\n[Phase 2b] Listing parts...")
        emit_phase("PHASE_2B_MONOPARTS")
        emit_progress(4, "Phase 2b: listing parts for monopart analysis...")
        state = _node_list_parts(state)
        print(f"[Phase 2b] [OK] Complete")
        
        # 2c: Run monoparts analysis
        print(f"\n[Phase 2c] Monopart analysis...")
        emit_phase("PHASE_2B_MONOPARTS")
        emit_progress(4, "Phase 2c: analysing monoparts...")
        state = _node_run_monoparts(state)
        print(f"[Phase 2c] [OK] Complete")
        
        # 2d: Merge copy part data
        print(f"\n[Phase 2d] Merge copy part data...")
        state = _node_merge_copy_part_data(state)
        print(f"[Phase 2d] [OK] Complete")
        
        # 2e: Merge BOM
        print(f"\n[Phase 2e] Merge BOM...")
        state = _node_merge_bom(state)
        print(f"[Phase 2e] [OK] Complete")
        
        # 2f: Generate assembly sequence (handles remarks if present)
        print(f"\n[Phase 2f] Generate assembly sequence (run {state.get('sequence_run_counter', 1)})...")
        emit_phase("PHASE_2B_SEQUENCE")
        emit_progress(5, "Phase 2f: generating assembly sequence...")
        print(f"[Phase 2f]   assembly_name: {state.get('assembly_name')}")
        print(f"[Phase 2f]   APA_EXPERIMENT_OUTPUT_DIR: {os.environ.get('APA_EXPERIMENT_OUTPUT_DIR')}")
        
        # IMPORTANT: Ensure sequence generation is enabled (may have been disabled in Phase 1)
        state["enable_assembly_sequence"] = True
        
        # For session-based workflow: disable loading from input/textbased_data on first run
        # These files won't exist in session context, only Agent 2 feedback will be provided
        state["asg_use_manual_order"] = False
        state["asg_include_gt_sequence"] = False
        
        # Debug: check if assembly data exists where node will look
        assembly_name = state.get('assembly_name')
        expected_assembly_dir1 = WORKSPACE_ROOT / "data" / "processed" / "stepparser" / assembly_name / f"assembly_{assembly_name}"
        print(f"[Phase 2f]   Assembly dir exists: {expected_assembly_dir1.exists()}")
        
        state = _node_generate_assembly_sequence(state)
        
        seq_path = state.get("assembly_sequence_path")
        if seq_path:
            print(f"[Phase 2f] SUCCESS: {Path(seq_path).name}")
        else:
            print(f"[Phase 2f] FAILED: assembly_sequence_path is None")
            session_root = Path(state["session_root"])
            run_num = state.get("sequence_run_counter", 1)
            seq_dir = session_root / f"assembly_sequence_run{run_num}"
            if seq_dir.exists():
                print(f"[Phase 2f]   But directory was created: {seq_dir}")
                contents = list(seq_dir.glob("*"))
                print(f"[Phase 2f]   Contents: {[p.name for p in contents]}")
        
        print(f"\n[Phase 2b-2f] [OK] COMPLETE\n")
        
    except Exception as e:
        print(f"[Phase 2b-2f] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    return state


# ============================================================================
# AGENT 2: SEQUENCE VALIDATOR (INTERACTIVE LOOP)
# ============================================================================

def run_agent_2_loop(
    state: Dict[str, Any],
    prompt_library: Dict[str, str],
    input_queue=None,
    ui_callback=None
) -> Dict[str, Any]:
    """Agent 2: Sequence Validator with LangGraph.
    
    Flow:
    1. Load current sequence from Phase 2
    2. Agent 2 presents sequence and asks for validation
    3. Multi-turn conversation with user
    4. Agent calls approve_sequence() or request_revision() tool
    5. If approved → proceed to Phase 4
    6. If revision requested → regenerate Phase 2 and loop
    7. Max iterations enforces approval
    
    Args:
        state: Workflow state
        prompt_library: Prompt library
        input_queue: Optional queue.Queue for user input from UI
        ui_callback: Optional callback for UI updates
    """
    from agent.agent2_sequence_validator import Agent2
    
    print(f"\n{'='*80}")
    print(f"AGENT 2: SEQUENCE VALIDATOR (LangGraph)")
    print(f"{'='*80}")
    
    assembly_name = state["assembly_name"]
    session_root = Path(state["session_root"])
    config = state.get("config", {})
    max_iterations = config.get("phase_3", {}).get("max_iterations", 3)
    
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        run_num = state.get("sequence_run_counter", 1)
        
        print(f"\n[Agent 2] Iteration {iteration} (Sequence run {run_num})")
        
        # Load current sequence
        seq_dir = session_root / f"assembly_sequence_run{run_num}"
        seq_file = seq_dir / "assembly_sequence.json"
        
        if not seq_file.exists():
            print(f"[Agent 2] ✗ Sequence file not found: {seq_file}")
            return state
        
        try:
            with open(seq_file, "r", encoding="utf-8") as f:
                sequence_data = json.load(f)
        except Exception as e:
            print(f"[Agent 2] ✗ Error reading sequence: {e}")
            return state
        
        # Initialize Agent 2
        agent = Agent2(llm_model=state.get("llm_model", "4o"))
        
        # Get system prompt
        system_prompt = prompt_library.get("agent2_system",
            "You are a manufacturing engineer validating assembly sequences.")
        
        # Run validation
        result = agent.run(
            system_prompt=system_prompt,
            sequence_json=sequence_data,
            assembly_name=assembly_name,
            max_turns=10,
            input_queue=input_queue,
            ui_callback=ui_callback
        )
        
        # Save conversation
        agent_txt_dir = session_root / "Agent_txt_files"
        agent_txt_dir.mkdir(parents=True, exist_ok=True)
        agent.save_conversation(
            filepath=agent_txt_dir / f"Agent2_validation_iteration_{iteration}.txt"
        )
        
        # Check result
        if result.get("approval_granted", False):
            print(f"\n[Agent 2] ✓ Sequence APPROVED - proceeding to Phase 4\n")
            return {
                **state,
                "approval": True,
                "user_feedback": "",
            }
        
        elif result.get("revision_remarks"):
            # Regenerate with feedback
            remarks = result["revision_remarks"]
            print(f"\n[Agent 2] Revisions requested: {remarks[:80]}...")
            print(f"[Phase 2f] Regenerating sequence with feedback...\n")
            
            # Save remarks in session root (where Phase 2f v2 expects them)
            remarks_file = session_root / f"remarks_{assembly_name}.txt"
            remarks_file.write_text(remarks, encoding="utf-8")
            print(f"[Agent 2] [OK] Remarks saved to: {remarks_file}")
            print(f"[Agent 2] [OK] Remarks file exists: {remarks_file.exists()}")
            print(f"[Agent 2] [OK] Remarks content ({len(remarks)} chars):\n{remarks}\n")
            
            # Update state for next regeneration
            state["previous_remarks_context"] = remarks
            state["sequence_run_counter"] = run_num + 1
            state["enable_assembly_sequence"] = True
            state["session_root"] = str(session_root)  # Ensure session_root is in state for v2 node
            
            # Regenerate sequence with remarks using v2 node (checks session_root first)
            try:
                from agent.workflow import _node_generate_assembly_sequence_v2_agent_feedback
                
                print(f"[Phase 2f] Calling v2 node with session_root: {state['session_root']}")
                state = _node_generate_assembly_sequence_v2_agent_feedback(state)
                
                print(f"[Phase 2f] ✓ New sequence generated")
                # Loop continues...
                
            except Exception as e:
                print(f"[Phase 2f] ✗ ERROR: {e}")
                import traceback
                traceback.print_exc()
                # Force approval to prevent infinite loop
                return {
                    **state,
                    "approval": True,
                    "forced_approval": True,
                }
        
        else:
            # No decision made (timeout)
            print(f"\n[Agent 2] No decision in max turns, proceeding\n")
            return {
                **state,
                "approval": True,
            }
    
    # Max iterations reached
    print(f"\n[Agent 2] ✗ Max iterations ({max_iterations}) reached, forcing approval")
    return {
        **state,
        "approval": True,
        "forced_approval": True,
    }


# ============================================================================
# PHASE 4: RENDERING + QUALITY ASSESSMENT
# ============================================================================

def run_phase_4(state: Dict[str, Any], ui_callback=None) -> Dict[str, Any]:
    """Phase 4: Rendering + Quality Assessment.
    
    Steps:
      1. Render assembly steps (ISO + section views)
      2. Interaction analysis (can fail gracefully)
      3. FFA assessment
    """
    print(f"\n{'='*80}")
    print(f"PHASE 4: RENDERING + QUALITY ASSESSMENT")
    print(f"{'='*80}")

    def emit_progress(step: int, status_text: str = None):
        if ui_callback:
            try:
                ui_callback("progress", step=step)
                if status_text:
                    ui_callback("status", content=status_text)
            except Exception as e:
                print(f"[PHASE 4 UI] Error: {e}")

    def emit_phase(phase_name: str):
        if ui_callback:
            try:
                ui_callback("phase_changed", phase=phase_name)
            except Exception as e:
                print(f"[PHASE 4 UI] Error: {e}")
    
    try:
        from agent.workflow import (
            _node_render_assembly_steps,
            _node_interaction_analysis,
            _node_assess_ffa,
            _node_ffa_reporter,
            _node_ffa_post_processing,
        )
        
        # 4a: Render assembly steps
        print(f"\n[Phase 4a] Rendering assembly steps...")
        emit_phase("PHASE_4_RENDERING")
        emit_progress(7, "→ Phase 4a: Rendering assembly steps...")
        try:
            state = _node_render_assembly_steps(state)
            print(f"[Phase 4a] [OK] Complete")
        except Exception as e:
            print(f"[Phase 4a] ⚠ Warning: {e}")
            print(f"[Phase 4a] Continuing without rendering...")
        
        # 4b: Interaction analysis (skip if it fails)
        print(f"\n[Phase 4b] Interaction analysis...")
        emit_phase("PHASE_4_INTERACTIONS")
        emit_progress(8, "→ Phase 4b: Interaction analysis...")
        try:
            state = _node_interaction_analysis(state)
            print(f"[Phase 4b] [OK] Complete")
        except KeyboardInterrupt:
            print(f"[Phase 4b] ⚠ Cancelled by user, skipping interaction analysis")
            state["interaction_analysis"] = None
        except Exception as e:
            print(f"[Phase 4b] ⚠ Warning: Interaction analysis failed: {str(e)[:100]}")
            print(f"[Phase 4b] Skipping interaction analysis, continuing to FFA...")
            state["interaction_analysis"] = None
        
        # 4c: FFA assessment
        print(f"\n[Phase 4c] FFA assessment...")
        emit_phase("PHASE_4_FFA")
        emit_progress(9, "→ Phase 4c: FFA assessment...")
        try:
            state = _node_assess_ffa(state)
            print(f"[Phase 4c] [OK] Complete")
        except Exception as e:
            print(f"[Phase 4c] ⚠ Warning: {e}")
            print(f"[Phase 4c] Continuing without FFA assessment...")
        
        # 4d: FFA report synthesis
        print(f"\n[Phase 4d] FFA report synthesis...")
        emit_phase("PHASE_4_REPORT")
        emit_progress(10, "Generating FFA report...")
        try:
            state = _node_ffa_reporter(state)
            print(f"[Phase 4d] [OK] Complete")
        except Exception as e:
            print(f"[Phase 4d] Warning: {e}")
            print(f"[Phase 4d] Continuing without synthesized FFA report...")

        # 4e: FFA post-processing / PDF package
        print(f"\n[Phase 4e] FFA post-processing / PDF...")
        emit_progress(10, "Building PDF report package...")
        try:
            state = _node_ffa_post_processing(state)
            print(f"[Phase 4e] [OK] Complete")
        except Exception as e:
            print(f"[Phase 4e] Warning: {e}")
            print(f"[Phase 4e] Continuing without PDF package...")

        if ui_callback:
            post_result = state.get("ffa_post_processing_result") or {}
            ui_callback(
                "artifacts",
                ffa_assessment_path=state.get("ffa_assessment_path"),
                ffa_report_path=state.get("ffa_report_path"),
                ffa_pdf_path=post_result.get("pdf_report"),
                ffa_plot_path=post_result.get("step_plot"),
                ffa_metrics_json=post_result.get("assembly_metrics_json"),
            )

        print(f"\n[Phase 4] [OK] COMPLETE\n")
        
    except Exception as e:
        print(f"[Phase 4] ✗ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    return state


# ============================================================================
# AGENT 3: FFA EXPLAINER
# ============================================================================

def run_agent_3(state: Dict[str, Any], prompt_library: Dict[str, str], input_queue=None, ui_callback=None) -> Dict[str, Any]:
    """Agent 3: FFA Explainer - Final step presenting FFA results.
    
    Flow:
    1. Load FFA assessment from Phase 4
    2. Agent 3 auto-presents FFA results (Turn 0)
    3. Multi-turn conversation with user questions (Turn 1+)
    4. Save conversation summary
    5. Return to DONE (final endpoint, no further phases)
    
    Args:
        state: Workflow state
        prompt_library: Prompt library
        input_queue: Optional queue.Queue for user input from UI
        ui_callback: Optional callback for UI updates
    """
    from agent.agent_managers import Agent3
    
    print(f"\n{'='*80}")
    print(f"AGENT 3: FFA EXPLAINER")
    print(f"{'='*80}")
    
    try:
        assembly_name = state["assembly_name"]
        session_root = Path(state["session_root"])
        
        # Check FFA file exists
        ffa_file = session_root / "ffa_assessment" / "ffa_assessment.json"
        if not ffa_file.exists():
            print(f"[Agent 3] ✗ FFA assessment not found: {ffa_file}")
            return state
        
        # Initialize Agent 3
        agent = Agent3(llm_model=state.get("llm_model", "4o"))
        
        # Load FFA assessment + synthesized report
        agent.load_ffa_assessment(session_root, assembly_name)
        agent.load_ffa_report(
            session_root,
            assembly_name,
            report_dir=Path(state.get("ffa_report_path")) if state.get("ffa_report_path") else None,
        )
        
        if not agent.ffa_assessment:
            print(f"[Agent 3] ✗ Could not load FFA assessment")
            return state
        
        # Get system prompt
        system_prompt = prompt_library.get("agent3_system",
            "You are an automation fitness expert analyzing assembly sequences. "
            "Present findings clearly, highlighting automation challenges and opportunities.")
        
        # Optional: Load interaction analysis for context
        interaction_summary = ""
        interaction_file = session_root / f"assembly_sequence_run{state.get('sequence_run_counter', 1)}" / "interaction_analysis.json"
        if interaction_file.exists():
            try:
                with open(interaction_file, "r", encoding="utf-8") as f:
                    interaction_data = json.load(f)
                    interaction_summary = json.dumps(interaction_data, indent=2)[:1000]
            except Exception as e:
                print(f"[Agent 3] ⚠ Could not load interaction summary: {e}")
        
        # Run Agent 3 (auto-presents + questions)
        result = agent.run(
            system_prompt=system_prompt,
            interaction_summary=interaction_summary,
            pdf_report_path=((state.get("ffa_post_processing_result") or {}).get("pdf_report", "")),
            max_turns=15,
            input_queue=input_queue,
            ui_callback=ui_callback
        )
        
        # Save conversation
        agent_txt_dir = session_root / "Agent_txt_files"
        agent_txt_dir.mkdir(parents=True, exist_ok=True)
        agent.save_conversation(
            filepath=agent_txt_dir / "Agent3_ffa_explanation.txt"
        )
        
        print(f"\n[Agent 3] ✓ FFA explanation complete\n")
        
        return {
            **state,
            "ffa_summary": json.dumps(result),
            "agent3_complete": True,
        }
    
    except Exception as e:
        print(f"[Agent 3] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return state


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def run_app_workflow_v2(
    config_path: Optional[Path] = None,
    assembly_name: Optional[str] = None,
    session_root: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
    prompt_library: Optional[Dict[str, str]] = None,
    ui_callback = None,  # Optional callback(event: dict) for UI updates
    input_queue = None,  # Optional queue.Queue for user input from UI
) -> Dict[str, Any]:
    """Main application workflow orchestrator.
    
    State machine:
      PHASE_1 → PHASE_2a → AGENT_1 → PHASE_2b → AGENT_2_LOOP → PHASE_4 → AGENT_3 → DONE
      
    Agent 2 loop can regenerate Phase 2 until user approval.
    Agent 3 can trigger Phase 2 revision.
    
    Args:
        config_path: Path to config file (optional if config provided)
        assembly_name: Assembly name (optional if discovered)
        session_root: Session root path (optional if setup_session called)
        config: Config dict (optional, loaded if not provided)
        prompt_library: Prompt library dict (optional, loaded if not provided)
        ui_callback: Optional callback(event: dict) for UI updates
                    Event types: "message", "status", "phase_changed", "error", "complete"
        input_queue: Optional queue.Queue for user input from UI (agents read from this)
    """
    
    def ui_emit(event_type: str, **kwargs):
        """Emit event to UI callback."""
        if ui_callback:
            event = {"type": event_type, **kwargs}
            try:
                ui_callback(event)
            except Exception as e:
                print(f"[UI_CALLBACK] Error: {e}")
    
    print(f"\n{'='*80}")
    print(f"APP WORKFLOW V2: INTERACTIVE ASSEMBLY ANALYSIS")
    print(f"{'='*80}\n")
    
    ui_emit("status", content="🔄 Setting up workflow...")
    
    # Setup
    if config is None:
        config = load_config(config_path)
    
    if prompt_library is None:
        prompt_library = load_prompt_library("prompts.yaml")
    
    if assembly_name is None:
        assembly_name = discover_assembly()
    
    if session_root is None:
        session_root = setup_session(assembly_name)
    else:
        session_root = Path(session_root)
        os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(session_root)
    
    ui_emit("status", content=f"✓ Setup complete")
    
    # Emit initial progress (upload complete)
    ui_emit("progress", step=0)
    
    # Initialize state
    state = {
        "assembly_name": assembly_name,
        "session_root": str(session_root),
        "sequence_run_counter": 1,
        "config": config,
        "_ui_callback": ui_emit,
    }
    
    # Progress tracking mapping: phase -> progress_step
    phase_to_progress = {
        "PHASE_1": 1,      # Preprocess Stepfile
        "PHASE_2a": 2,     # Analyse Assembly (start)
        "AGENT_1": 3,      # Analyse Assembly (agent)
        "PHASE_2b": 4,     # Analyse Monoparts (sequence generation updates to 5)
        "AGENT_2_LOOP": 6, # Discuss about Assembly Sequence
        "PHASE_4": 7,      # Render Assemblysteps
        "AGENT_3": 11,     # Discuss / download final report
        "DONE": 11,        # Final step
    }
    
    # Main state machine loop
    max_iterations = 50  # Safety limit
    iteration = 0
    phase = "PHASE_1"
    
    while phase != "DONE" and iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"[MAIN] Iteration {iteration}, Phase: {phase}")
        print(f"{'='*80}")
        ui_emit("phase_changed", phase=phase)
        
        try:
            if phase == "PHASE_1":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("status", content="→ Phase 1: Preprocessing...")
                state = run_phase_1(state)
                ui_emit("status", content="✓ Phase 1 complete")
                phase = "PHASE_2a"
            
            elif phase == "PHASE_2a":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("status", content="→ Phase 2a: Enrichment...")
                state = run_phase_2a_only(state)
                ui_emit("status", content="✓ Phase 2a complete")
                phase = "AGENT_1"
            
            elif phase == "AGENT_1":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("message", role="system", content="🤖 Invoking Agent 1: Assembly Analyst")
                state = run_agent_1(state, prompt_library, input_queue=input_queue, ui_callback=ui_emit)
                phase = "PHASE_2b"
            
            elif phase == "PHASE_2b":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("status", content="Phase 2b: monopart analysis and sequence preparation...")
                state = run_phase_2b_onwards(state)
                ui_emit("status", content="Sequence generated")
                phase = "AGENT_2_LOOP"
            
            elif phase == "AGENT_2_LOOP":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("message", role="system", content="👤 Awaiting user approval...")
                state = run_agent_2_loop(state, prompt_library, input_queue=input_queue, ui_callback=ui_emit)
                if state.get("approval"):
                    ui_emit("message", role="system", content="✓ Sequence approved")
                    phase = "PHASE_4"
                else:
                    phase = "DONE"
            
            elif phase == "PHASE_4":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("status", content="→ Phase 4: Rendering & FFA assessment...")
                state = run_phase_4(state, ui_callback=ui_emit)
                ui_emit("status", content="✓ FFA assessment complete")
                phase = "AGENT_3"
            
            elif phase == "AGENT_3":
                ui_emit("progress", step=phase_to_progress.get(phase, 0))
                ui_emit("message", role="system", content="⚡ Invoking Agent 3: FFA Explainer")
                state = run_agent_3(state, prompt_library, input_queue=input_queue, ui_callback=ui_emit)
                phase = "DONE"
            
            else:
                print(f"[MAIN] ✗ Unknown phase: {phase}")
                phase = "DONE"
        
        except Exception as e:
            print(f"\n[MAIN] ✗ ERROR in {phase}: {e}")
            import traceback
            traceback.print_exc()
            break
    
    if phase != "DONE":
        ui_emit("error", content="Workflow did not complete (max iterations reached)")
        print(f"\n[MAIN] ✗ Workflow did not complete (max iterations reached)")
    else:
        ui_emit("phase_changed", phase="DONE")
        ui_emit("complete")
        print(f"\n{'='*80}")
        print(f"[MAIN] ✓ WORKFLOW COMPLETE")
        print(f"{'='*80}")
        print(f"\nSession: {session_root}")
        print(f"Assembly: {assembly_name}")
        print(f"Final Sequence Run: {state.get('sequence_run_counter', 1)}")
        print(f"\nOutputs:")
        print(f"  - Agent notes: {session_root}/Agent_txt_files/")
        print(f"  - Sequence: {session_root}/assembly_sequence_run{state.get('sequence_run_counter', 1)}/")
        print(f"  - FFA assessment: {session_root}/ffa_assessment/ffa_assessment.json")
        print(f"\n")
    
    return state


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="App Workflow V2")
    parser.add_argument("--config", type=Path, default=None, help="Config file path")
    parser.add_argument("--assembly", type=str, default=None, help="Assembly name")
    parser.add_argument("--session", type=Path, default=None, help="Session root path")
    
    args = parser.parse_args()
    
    try:
        state = run_app_workflow_v2(
            config_path=args.config,
            assembly_name=args.assembly,
            session_root=args.session,
        )
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
