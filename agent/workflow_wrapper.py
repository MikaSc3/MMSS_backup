"""
Workflow Wrapper for Interactive Annotation

Provides checkpoint-based execution of the interactive workflow.
Allows running from one checkpoint to another (phase to phase).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import json
from datetime import datetime

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, StateGraph, START
except ImportError:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, StateGraph, START

try:
    from agent.workflow import (
        _node_resolve_paths,
        _node_run_assembly,
        _node_list_parts,
        _node_run_monoparts,
        _node_merge_copy_part_data,
        _node_merge_bom,
        _node_generate_assembly_sequence,
        _node_render_assembly_steps,
        _node_interaction_analysis,
        _node_assess_ffa,
    )
    from agent.prompt_store import load_experiment_settings
    from agent.tools import _get_experiment_output_dir
except ImportError:
    from workflow import (
        _node_resolve_paths,
        _node_run_assembly,
        _node_list_parts,
        _node_run_monoparts,
        _node_merge_copy_part_data,
        _node_merge_bom,
        _node_generate_assembly_sequence,
        _node_render_assembly_steps,
        _node_interaction_analysis,
        _node_assess_ffa,
    )
    from prompt_store import load_experiment_settings
    from tools import _get_experiment_output_dir


# ============================================================================
# PHASE DEFINITIONS
# ============================================================================

PHASE_DEFINITIONS = {
    "phase_1_stop": {
        "description": "After monopart analysis (Phase 1)",
        "stop_after_node": "run_monoparts",
    },
    "phase_2_stop": {
        "description": "After initial sequence generation (Phase 2)",
        "stop_after_node": "generate_assembly_sequence_v1",
    },
    "phase_3_stop": {
        "description": "After user feedback processing (Phase 3)",
        "stop_after_node": "generate_assembly_sequence_v2",
    },
    "end": {
        "description": "After FFA assessment (complete)",
        "stop_after_node": "assess_ffa",
    },
}


def build_interactive_workflow():
    """
    Build the interactive annotation workflow with phase stop points.
    
    Node order:
      resolve_paths → run_assembly → list_parts → run_monoparts
        [PHASE 1 STOP]
      → merge_copy_part_data → merge_bom
      → generate_assembly_sequence_v1 (ISO rendering)
        [PHASE 2 STOP]
      → render_assembly_steps (full rendering)
      → generate_assembly_sequence_v2 (with user remarks)
        [PHASE 3 STOP]
      → interaction_analysis → assess_ffa
        [END]
    """
    graph = StateGraph(dict)
    
    # Add nodes
    graph.add_node("resolve_paths", _node_resolve_paths)
    graph.add_node("run_assembly", _node_run_assembly)
    graph.add_node("list_parts", _node_list_parts)
    graph.add_node("run_monoparts", _node_run_monoparts)
    graph.add_node("merge_copy_part_data", _node_merge_copy_part_data)
    graph.add_node("merge_bom", _node_merge_bom)
    graph.add_node("generate_assembly_sequence_v1", _node_generate_assembly_sequence)
    graph.add_node("render_assembly_steps", _node_render_assembly_steps)
    graph.add_node("generate_assembly_sequence_v2", _node_generate_assembly_sequence)
    graph.add_node("interaction_analysis", _node_interaction_analysis)
    graph.add_node("assess_ffa", _node_assess_ffa)
    
    # Add edges
    graph.set_entry_point("resolve_paths")
    graph.add_edge("resolve_paths", "run_assembly")
    graph.add_edge("run_assembly", "list_parts")
    graph.add_edge("list_parts", "run_monoparts")
    # PHASE 1 STOP: after monopart analysis
    graph.add_edge("run_monoparts", "merge_copy_part_data")
    graph.add_edge("merge_copy_part_data", "merge_bom")
    # PHASE 2 STOP: after initial sequence generation
    graph.add_edge("merge_bom", "generate_assembly_sequence_v1")
    graph.add_edge("generate_assembly_sequence_v1", "render_assembly_steps")
    graph.add_edge("render_assembly_steps", "generate_assembly_sequence_v2")
    # PHASE 3 STOP: after sequence regeneration with user remarks
    graph.add_edge("generate_assembly_sequence_v2", "interaction_analysis")
    graph.add_edge("interaction_analysis", "assess_ffa")
    graph.add_edge("assess_ffa", END)
    
    # Compile with in-memory checkpointing
    checkpointer = InMemorySaver()
    
    return graph.compile(checkpointer=checkpointer)


def run_workflow_until(
    workflow_app: Any,
    datasource_root: str,
    target_phase: Literal["phase_1_stop", "phase_2_stop", "phase_3_stop", "end"],
    thread_id: str,
    remarks: Optional[str] = None,
    config_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the workflow from last checkpoint until target phase is reached.
    
    Args:
        workflow_app: Compiled LangGraph workflow
        datasource_root: Path to assembly data
        target_phase: Which phase to run until ("phase_1_stop", "phase_2_stop", "phase_3_stop", "end")
        thread_id: Thread ID for checkpoint management
        remarks: Optional user remarks to inject into state (for phase 3)
        config_file: Optional path to experiment config
    
    Returns:
        Full workflow state dict when phase is reached
    
    Raises:
        ValueError: If target_phase is invalid
        RuntimeError: If workflow execution fails
    """
    if target_phase not in PHASE_DEFINITIONS:
        raise ValueError(
            f"Invalid target_phase: {target_phase}. "
            f"Must be one of: {list(PHASE_DEFINITIONS.keys())}"
        )
    
    phase_info = PHASE_DEFINITIONS[target_phase]
    stop_after_node = phase_info["stop_after_node"]
    
    # Load settings (config_file passed in or None)
    if config_file:
        os.environ["APA_EXPERIMENT_YAML"] = str(Path(config_file).resolve())
    settings = load_experiment_settings()
    
    # Prepare config for LangGraph
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize state if this is the first run
    existing_state = workflow_app.get_state(config)
    if existing_state.values is None or not existing_state.values:
        # First run: initialize state with datasource_root
        initial_state = {
            "datasource_root": str(Path(datasource_root).expanduser()),
            "assembly_name": Path(datasource_root).name,
            "workflow_print": bool(settings.get("workflow_print", False)),
            "workflow_print_prompt_preview_chars": int(
                settings.get("workflow_print_prompt_preview_chars", 800)
            ),
            "parallel": bool(settings.get("parallel", False)),
            "max_workers": int(settings.get("max_workers", 4)),
            "use_unique_parts": bool(settings.get("use_unique_parts", True)),
            "workflow_phase": "running",
        }
        # Inject user remarks if provided (for phase 3)
        if remarks:
            initial_state["user_remarks"] = remarks
    else:
        # Resume from checkpoint: inject remarks if provided
        initial_state = existing_state.values
        if remarks:
            initial_state["user_remarks"] = remarks
    
    # Stream execution until target phase
    result_state = None
    nodes_executed = []
    
    print(f"\n[workflow_wrapper] Running workflow until: {target_phase}")
    print(f"[workflow_wrapper] Stop after node: {stop_after_node}")
    
    try:
        for event in workflow_app.stream(initial_state, config, stream_mode="updates"):
            for node_name, node_state in event.items():
                if node_name != "__input__" and node_name != "__end__":
                    nodes_executed.append(node_name)
                    print(f"[workflow_wrapper] ✓ Completed node: {node_name}")
                    
                    # Check if we've reached the target phase
                    if node_name == stop_after_node:
                        result_state = node_state
                        print(
                            f"[workflow_wrapper] ✓ Target phase reached: {target_phase}"
                        )
                        # Update state one last time before returning
                        workflow_app.update_state(config, node_state)
                        break
            
            if result_state is not None:
                break
    
    except Exception as e:
        print(f"[workflow_wrapper] ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"Workflow execution failed: {e}")
    
    # Get final state from checkpoint
    final_state_snapshot = workflow_app.get_state(config)
    if final_state_snapshot.values is None:
        raise RuntimeError(f"No state returned after phase: {target_phase}")
    
    result_state = final_state_snapshot.values
    result_state["nodes_executed"] = nodes_executed
    result_state["workflow_phase"] = target_phase
    
    print(f"[workflow_wrapper] Phase complete. State persisted to checkpoint.")
    print(f"[workflow_wrapper] Nodes executed: {', '.join(nodes_executed)}")
    
    return result_state


def get_checkpoint_state(thread_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the current state from a checkpoint.
    
    Args:
        thread_id: Thread ID of the session
    
    Returns:
        State dict or None if no checkpoint exists
    """
    # Note: InMemorySaver stores state in memory only, not persistently
    # Checkpoint state is stored in the compiled graph and only available during execution
    return None


def list_checkpoints() -> list[Dict[str, Any]]:
    """
    List all available checkpoints.
    
    Returns:
        List of checkpoint metadata
    """
    # Note: InMemorySaver stores state in memory only, not persistently
    # Checkpoints are not saved to disk, so this always returns empty
    return []
