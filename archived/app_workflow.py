#!/usr/bin/env python3
"""
Interactive Annotation Workflow - Entry Point

Usage:
    python app_workflow.py {assembly_name}
    python app_workflow.py {assembly_name} --config configs/interactive_annotation/custom_config.yaml
    python app_workflow.py {assembly_name} --session-only  # Resume existing session

Example:
    python app_workflow.py IPA_Cranfield
    python app_workflow.py IPA_Reducer --config configs/interactive_annotation/custom_config.yaml
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import os

from colorama import init as colorama_init
colorama_init(autoreset=True)

# Load environment variables from agent/.env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "agent" / ".env")

try:
    from agent.pm_agent import build_pm_agent, create_pm_agent_state
    from agent.prompt_store import load_experiment_settings
    from agent.tools import _get_experiment_output_dir
except ImportError:
    from pm_agent import build_pm_agent, create_pm_agent_state
    from prompt_store import load_experiment_settings
    from tools import _get_experiment_output_dir


def validate_assembly_path(assembly_name: str) -> Path:
    """
    Validate that the assembly data exists.
    
    Expected structure:
        data/session/{assembly_name}/input/{assembly_name}.STEP
    
    Args:
        assembly_name: Name of the assembly
    
    Returns:
        Path to the assembly input directory
    
    Raises:
        ValueError: If assembly data not found
    """
    settings = load_experiment_settings()
    session_root = Path(settings.get("session_input_root", "data/session"))
    assembly_input_dir = session_root / assembly_name / "input"
    
    if not assembly_input_dir.exists():
        raise ValueError(
            f"Assembly data not found: {assembly_input_dir}\n"
            f"Expected: data/session/{assembly_name}/input/{assembly_name}.STEP"
        )
    
    step_file = assembly_input_dir / f"{assembly_name}.STEP"
    if not step_file.exists():
        raise ValueError(
            f"STEP file not found: {step_file}\n"
            f"Please place your STEP file at: data/session/{assembly_name}/input/{assembly_name}.STEP"
        )
    
    return assembly_input_dir


def setup_session_directories(assembly_name: str) -> Dict[str, Path]:
    """
    Create and setup session output directories.
    
    Structure:
        data/session/{assembly_name}/
        ├── input/
        ├── processed/
        └── output/
            ├── textbased_info/
            ├── renderings/
            └── ffa_assessment/
    
    Returns:
        Dict with paths to session directories
    """
    settings = load_experiment_settings()
    session_root = Path(settings.get("session_input_root", "data/session"))
    assembly_session = session_root / assembly_name
    
    output_dir = assembly_session / "output"
    processed_dir = assembly_session / "processed"
    
    # Create directories
    output_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "textbased_info").mkdir(exist_ok=True)
    (output_dir / "renderings").mkdir(exist_ok=True)
    (output_dir / "ffa_assessment").mkdir(exist_ok=True)
    
    # Set experiment output environment variable
    # This is used by nodes to find where to save results
    import os
    os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(output_dir)
    
    return {
        "session_root": assembly_session,
        "input_dir": assembly_session / "input",
        "output_dir": output_dir,
        "processed_dir": processed_dir,
    }


def save_session_state(
    state: Dict[str, Any],
    assembly_name: str,
) -> Path:
    """
    Save the final PM agent state to session_state.json
    
    Args:
        state: Final agent state
        assembly_name: Assembly name
    
    Returns:
        Path to saved session state file
    """
    settings = load_experiment_settings()
    session_root = Path(settings.get("session_input_root", "data/session"))
    output_file = session_root / assembly_name / "output" / "session_state.json"
    
    # Prepare state for serialization
    serializable_state = {
        "assembly_name": state.get("assembly_name"),
        "thread_id": state.get("thread_id"),
        "session_start_time": state.get("session_start_time"),
        "last_checkpoint_time": state.get("last_checkpoint_time"),
        "current_phase": state.get("current_phase"),
        "assembly_function": state.get("assembly_function"),
        "sub_assemblies": state.get("sub_assemblies"),
        "handling_constraints": state.get("handling_constraints"),
        "sequence_remarks": state.get("sequence_remarks"),
        "workflow_nodes_executed": state.get("workflow_nodes_executed", []),
        "decisions_log": state.get("decisions_log", []),
        "saved_at": datetime.now().isoformat(),
    }
    
    # Add message count
    messages = state.get("messages", [])
    serializable_state["message_count"] = len(messages)
    
    with open(output_file, "w") as f:
        json.dump(serializable_state, f, indent=2)
    
    return output_file


def print_banner():
    """Print welcome banner"""
    banner = r"""
========================================================================
         INTERACTIVE ANNOTATION WORKFLOW - APP_WORKFLOW
                                                                
  Guided assembly annotation with PM (Process Manager) Agent
                                                                
  Phases:
  [1] Assembly Analysis & Questions                            
  [2] Sequence Generation & User Review                        
  [3] Final Analysis (Interaction + FFA)                       
                                                                
  Status: READY
========================================================================
    """
    print(banner)


def print_completion_summary(assembly_name: str, output_dir: Path):
    """Print completion summary"""
    summary = f"""
========================================================================
                    SESSION COMPLETE
========================================================================

Assembly: {assembly_name}
Output Directory: {output_dir}

Generated Files:
  [OK] assembly_sequence.json - Final assembly sequence
  [OK] ffa_assessment/ffa_assessment.json - Automation evaluation
  [OK] interaction_analysis.json - Geometric interactions
  [OK] session_state.json - Session metadata
  [OK] textbased_info/ - User responses and remarks
  [OK] renderings/ - Assembly step visualizations

Next Steps:
  - Review the assembly sequence in assembly_sequence.json
  - Check FFA results in ffa_assessment/ffa_assessment.json
  - Iterate if needed (PM agent will manage resumption)

Questions? Check the workflow_app.md documentation.
    """
    print(summary)


def main():
    """Main entry point"""
    # Set UTF-8 encoding for Windows compatibility
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    parser = argparse.ArgumentParser(
        description="Interactive Annotation Workflow for Assembly Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app_workflow.py IPA_Cranfield
  python app_workflow.py IPA_Reducer --config configs/interactive_annotation/custom_config.yaml
  python app_workflow.py IPA_Cranfield --no-render  # Skip rendering for speed
        """,
    )
    
    parser.add_argument(
        "assembly_name",
        help="Assembly name (e.g., IPA_Cranfield)",
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom config file (default: uses standard config)",
    )
    
    parser.add_argument(
        "--session-only",
        action="store_true",
        help="Resume an existing session (skip initialization)",
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    assembly_name = args.assembly_name
    
    try:
        # Validate assembly
        print(f"[*] Validating assembly data for: {assembly_name}")
        assembly_input = validate_assembly_path(assembly_name)
        print(f"    [OK] Found: {assembly_input}")
        
        # Setup session directories
        print(f"[*] Setting up session directories...")
        session_dirs = setup_session_directories(assembly_name)
        assembly_datasource = str(session_dirs["input_dir"])
        print(f"    [OK] Output: {session_dirs['output_dir']}")
        
        # Load settings
        print(f"[*] Loading configuration...")
        if args.config:
            os.environ["APA_EXPERIMENT_YAML"] = str(Path(args.config).resolve())
        settings = load_experiment_settings()
        print(f"    [OK] Config loaded (model: {settings.get('llm_model')})")
        
        # Build PM agent
        print(f"[*] Building PM Agent...")
        pm_agent = build_pm_agent()
        print(f"    [OK] Agent ready")
        
        # Initialize agent state
        print(f"[*] Initializing session...")
        initial_state = create_pm_agent_state(
            assembly_name=assembly_name,
            datasource_root=assembly_datasource,
            config_file=args.config,
        )
        thread_id = initial_state["thread_id"]
        print(f"    [OK] Thread ID: {thread_id}")
        
        # Run PM agent
        print(f"\n{'='*60}")
        print(f"Starting Interactive Annotation Workflow")
        print(f"Assembly: {assembly_name}")
        print(f"{'='*60}\n")
        
        config = {"configurable": {"thread_id": thread_id}}
        
        # Stream the agent execution
        final_state = None
        for event in pm_agent.stream(initial_state, config):
            for node, values in event.items():
                if node != "__end__":
                    final_state = values
        
        # Save session state
        if final_state:
            print(f"\n[*] Saving session state...")
            session_file = save_session_state(final_state, assembly_name)
            print(f"    [OK] Saved to: {session_file}")
        
        # Print completion summary
        print_completion_summary(assembly_name, session_dirs["output_dir"])
        
        return 0
        
    except ValueError as e:
        print(f"\n[ERROR] Validation Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n[WARN] Workflow interrupted by user")
        return 2
    except Exception as e:
        print(f"\n[ERROR] Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
