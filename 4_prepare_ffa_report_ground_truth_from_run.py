"""
Prepare Ground Truth from Run/Experiment

Creates timestamped PRE ground truth folders from a completed run/experiment.

Usage:
    python prepare_ground_truth_from_run.py

Configuration (edit these at the top):
    RUN_EXP_PATH: Path to run/experiment (e.g., data/experiments/run_2026-02-13_100643/exp2)
    GROUND_TRUTH_BASE: Base path for ground truth (default: data/ground_truth)
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import sys

# ============================================================================
# CONFIGURATION - Edit these values
# ============================================================================

RUN_EXP_PATH = "data/experiments/test/End_to_End_final_System"
GROUND_TRUTH_BASE = "data/ground_truth/TEST"

# ============================================================================
# IMPORTS - From evaluation module
# ============================================================================

try:
    from evaluation.ffa_str_to_enum import convert_ffa_stripped_to_enum, create_ffa_enum_mapping
except ImportError as e:
    print(f"❌ Error importing from evaluation.ffa_str_to_enum: {e}")
    print("Make sure evaluation/ffa_str_to_enum.py exists")
    sys.exit(1)


# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def discover_assemblies_in_run_exp(run_exp_path: Path) -> List[str]:
    """
    Discover all assembly directories in a run/experiment path.
    
    Args:
        run_exp_path: Path to run/exp directory
    
    Returns:
        List of assembly names
    """
    if not run_exp_path.exists():
        raise FileNotFoundError(f"Run/exp path does not exist: {run_exp_path}")
    
    assemblies = []
    for item in run_exp_path.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            assemblies.append(item.name)
    
    return sorted(assemblies)


def prepare_ground_truth_from_run(
    run_exp_path: Path,
    ground_truth_base_path: Path
) -> tuple[bool, List[str]]:
    """
    Creates PRE ground truth folders from a run/experiment.
    
    Discovers all assemblies and creates:
    - {timestamp}_PRE_assembly_sequence_ground_truth/{assembly}/
    - {timestamp}_PRE_ffa_ground_truth/
    
    Args:
        run_exp_path: Path to run/experiment (e.g., data/experiments/run_2026-02-13_100643/exp2)
        ground_truth_base_path: Base path for ground truth (e.g., data/ground_truth)
    
    Returns:
        Tuple of (success: bool, messages: List[str])
    """
    workspace_root = Path(__file__).resolve().parent
    run_exp_path = Path(run_exp_path)
    ground_truth_base_path = Path(ground_truth_base_path)
    
    # Make paths absolute
    if not run_exp_path.is_absolute():
        run_exp_path = workspace_root / run_exp_path
    if not ground_truth_base_path.is_absolute():
        ground_truth_base_path = workspace_root / ground_truth_base_path
    
    messages = []
    
    # Validate input
    if not run_exp_path.exists():
        msg = f"❌ Run/exp path does not exist: {run_exp_path}"
        messages.append(msg)
        return False, messages
    
    # Discover assemblies
    try:
        assemblies = discover_assemblies_in_run_exp(run_exp_path)
    except Exception as e:
        msg = f"❌ Error discovering assemblies: {e}"
        messages.append(msg)
        return False, messages
    
    if not assemblies:
        msg = f"❌ No assemblies found in {run_exp_path}"
        messages.append(msg)
        return False, messages
    
    msg = f"✓ Found {len(assemblies)} assemblies: {', '.join(assemblies)}"
    messages.append(msg)
    
    # Create PRE ground truth folders with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_assembly_seq_dir = ground_truth_base_path / f"{timestamp}_PRE_assembly_sequence_ground_truth"
    pre_ffa_dir = ground_truth_base_path / f"{timestamp}_PRE_ffa_ground_truth"
    
    pre_assembly_seq_dir.mkdir(parents=True, exist_ok=True)
    pre_ffa_dir.mkdir(parents=True, exist_ok=True)
    
    msg = f"\n📁 Created PRE ground truth directories:"
    messages.append(msg)
    msg = f"  - {pre_assembly_seq_dir.relative_to(workspace_root)}"
    messages.append(msg)
    msg = f"  - {pre_ffa_dir.relative_to(workspace_root)}"
    messages.append(msg)
    
    # Process each assembly
    processed = 0
    successful = 0
    failed = 0
    
    for assembly_name in assemblies:
        assembly_run_dir = run_exp_path / assembly_name
        msg = f"\n📦 Processing {assembly_name}..."
        messages.append(msg)
        
        try:
            # 1. Copy assembly_sequence.json from assembly_sequence_run{N}/
            sequence_file = None
            for item in assembly_run_dir.iterdir():
                if item.is_dir() and item.name.startswith("assembly_sequence_run"):
                    candidate = item / "assembly_sequence.json"
                    if candidate.exists():
                        sequence_file = candidate
                        break
            
            if sequence_file:
                assembly_seq_dir = pre_assembly_seq_dir / assembly_name
                assembly_seq_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sequence_file, assembly_seq_dir / "sequence.json")
                msg = f"  ✓ Copied sequence.json"
                messages.append(msg)
            else:
                msg = f"  ⚠️  No assembly_sequence.json found in assembly_sequence_run{N}/"
                messages.append(msg)
            
            # 2. Copy sequence_renderings from assembly_sequence_run{N}/
            renderings_dir = None
            for item in assembly_run_dir.iterdir():
                if item.is_dir() and item.name.startswith("assembly_sequence_run"):
                    candidate = item / "sequence_renderings"
                    if candidate.exists():
                        renderings_dir = candidate
                        break
            
            if renderings_dir:
                assembly_seq_dir = pre_assembly_seq_dir / assembly_name
                assembly_seq_dir.mkdir(parents=True, exist_ok=True)
                target_renderings = assembly_seq_dir / "renderings"
                if target_renderings.exists():
                    shutil.rmtree(target_renderings)
                shutil.copytree(renderings_dir, target_renderings)
                rend_count = len(list(target_renderings.glob("*")))
                msg = f"  ✓ Copied {rend_count} renderings"
                messages.append(msg)
            else:
                msg = f"  ⚠️  No sequence_renderings found in assembly_sequence_run{N}/"
                messages.append(msg)
            
            # 3. Find and convert FFA assessment (str → enum)
            ffa_dir = assembly_run_dir / "ffa_assessment"
            if ffa_dir.exists():
                # Find ffa_assessment_stripped.json
                ffa_stripped_file = ffa_dir / "ffa_assessment_stripped.json"
                
                if ffa_stripped_file.exists():
                    # Load the stripped JSON
                    with open(ffa_stripped_file, 'r') as f:
                        ffa_data = json.load(f)
                    
                    # Convert str to enum
                    try:
                        # Create enum mapping
                        enum_mapping = create_ffa_enum_mapping()
                        
                        # Convert the data
                        ffa_enum_data, conversion_errors = convert_ffa_stripped_to_enum(
                            stripped_data=ffa_data,
                            enum_mapping=enum_mapping,
                            assembly_name=assembly_name
                        )
                        
                        if conversion_errors:
                            for error in conversion_errors:
                                msg = f"    ⚠️  {error}"
                                messages.append(msg)
                        
                        # Save as {assembly_name}_ffa_assessment_enum_gt.json
                        enum_filename = f"{assembly_name}_ffa_assessment_enum_gt.json"
                        enum_path = pre_ffa_dir / enum_filename
                        
                        with open(enum_path, 'w') as f:
                            json.dump(ffa_enum_data, f, indent=2, default=str)
                        
                        msg = f"  ✓ Converted and saved {enum_filename}"
                        messages.append(msg)
                    except Exception as e:
                        msg = f"  ❌ Error converting FFA assessment: {e}"
                        messages.append(msg)
                else:
                    msg = f"  ⚠️  No ffa_assessment_stripped.json found in ffa_assessment/"
                    messages.append(msg)
            else:
                msg = f"  ⚠️  No ffa_assessment directory found"
                messages.append(msg)
            
            processed += 1
            successful += 1
            msg = f"  ✓ Assembly complete"
            messages.append(msg)
            
        except Exception as e:
            failed += 1
            msg = f"  ❌ Error processing assembly: {e}"
            messages.append(msg)
    
    # Summary
    msg = f"\n{'='*80}"
    messages.append(msg)
    msg = f"GROUND TRUTH PREPARATION COMPLETE"
    messages.append(msg)
    msg = f"{'='*80}"
    messages.append(msg)
    msg = f"✓ Assemblies processed: {successful}/{processed}"
    messages.append(msg)
    msg = f"✓ Assembly sequence dir: {pre_assembly_seq_dir.relative_to(workspace_root)}"
    messages.append(msg)
    msg = f"✓ FFA ground truth dir:  {pre_ffa_dir.relative_to(workspace_root)}"
    messages.append(msg)
    
    if failed > 0:
        msg = f"⚠️  Failed assemblies: {failed}"
        messages.append(msg)
        return True, messages  # Partial success
    
    return True, messages


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print(f"\n{'='*80}")
    print(f"PREPARE GROUND TRUTH FROM RUN")
    print(f"{'='*80}")
    
    success, messages = prepare_ground_truth_from_run(
        run_exp_path=Path(RUN_EXP_PATH),
        ground_truth_base_path=Path(GROUND_TRUTH_BASE)
    )
    
    # Print all messages
    for msg in messages:
        print(msg)
    
    if not success:
        sys.exit(1)
    else:
        print(f"\n✅ Ground truth preparation successful!")
        sys.exit(0)
