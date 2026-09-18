"""
Create checkpoints from existing experiment runs.

Standalone helper script to generate checkpoints from already-completed workflow runs.
Useful for retroactively creating checkpoints from runs that were completed before
checkpoint functionality was added.

Usage:
    python scripts/create_checkpoint_from_run.py <run_path> [--experiment <exp_name>]
    
Example:
    python scripts/create_checkpoint_from_run.py data/experiments/run_2026-02-10_154526 --experiment exp1_baseline
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


def collect_assemblies_from_run(run_path: Path, experiment_name: Optional[str] = None) -> Dict[str, Path]:
    """
    Collect all assembly directories from a run.
    
    Args:
        run_path: Path to run directory (e.g., data/experiments/run_2026-02-10_154526/)
        experiment_name: Optional - specific experiment to use. If None, finds first experiment.
        
    Returns:
        Dict: {assembly_name: assembly_dir_path}
    """
    run_path = Path(run_path)
    
    if not run_path.exists():
        print(f"❌ Run path not found: {run_path}")
        return {}
    
    # Find experiment directory
    if experiment_name:
        exp_dir = run_path / experiment_name
        if not exp_dir.exists():
            print(f"❌ Experiment directory not found: {exp_dir}")
            return {}
    else:
        # Find first non-special directory
        subdirs = [d for d in run_path.iterdir() if d.is_dir() and not d.name.startswith(('evaluation', 'logs', '_'))]
        if not subdirs:
            print(f"❌ No experiments found in {run_path}")
            return {}
        exp_dir = subdirs[0]
        print(f"ℹ️  Using experiment: {exp_dir.name}")
    
    # Collect assemblies
    assemblies = {}
    for assembly_dir in sorted(exp_dir.iterdir()):
        if assembly_dir.is_dir() and not assembly_dir.name.startswith('_'):
            assemblies[assembly_dir.name] = assembly_dir
    
    return assemblies


def create_checkpoint_from_run(
    run_path: Path,
    experiment_name: Optional[str] = None,
    checkpoint_base_path: str = "data/checkpoints"
) -> Tuple[bool, List[str]]:
    """
    Create checkpoints from an existing experiment run.
    
    Processes all assemblies in the run and creates standalone checkpoints.
    
    Checkpoint Structure:
    ```
    data/checkpoints/{timestamp}/
    ├── checkpoint_metadata.json
    └── {assembly_name}/
        ├── metadata.json
        ├── stepparser_renderings/
        ├── BOM_enriched.json
        └── enriched_parts/
    ```
    
    Args:
        run_path: Path to experiment run
        experiment_name: Optional - specific experiment to process
        checkpoint_base_path: Base path for checkpoints
        
    Returns:
        Tuple of (success: bool, messages: List[str])
    """
    workspace_root = WORKSPACE_ROOT
    
    # Collect assemblies
    assemblies = collect_assemblies_from_run(run_path, experiment_name)
    
    if not assemblies:
        return False, ["No assemblies found to process"]
    
    print(f"\n{'='*80}")
    print(f"CREATE CHECKPOINT FROM RUN")
    print(f"{'='*80}")
    print(f"Run: {run_path}")
    print(f"Assemblies: {', '.join(assemblies.keys())}")
    print(f"Checkpoint base: {checkpoint_base_path}")
    print()
    
    # Create checkpoint timestamp
    checkpoint_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    checkpoint_root = workspace_root / checkpoint_base_path / checkpoint_timestamp
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    
    messages = []
    assemblies_processed = []
    
    # Process each assembly
    for assembly_name, assembly_dir in sorted(assemblies.items()):
        print(f"\n[{assembly_name}]")
        checkpoint_assembly_dir = checkpoint_root / assembly_name
        checkpoint_assembly_dir.mkdir(parents=True, exist_ok=True)
        
        assembly_messages = []
        
        try:
            # 1. Load assembly_sequence.json from ground_truth
            ground_truth_seq_file = (
                workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
                assembly_name / "sequence.json"
            )
            
            if ground_truth_seq_file.exists():
                # Already in ground_truth (ideal case)
                assembly_messages.append(f"  ✓ Sequence found in ground_truth")
            else:
                # Try to find it in the run directory (nested in assembly_sequence_run{N}/)
                seq_candidates = []
                for item in assembly_dir.iterdir():
                    if item.is_dir() and item.name.startswith("assembly_sequence_run"):
                        seq_file = item / "assembly_sequence.json"
                        if seq_file.exists():
                            seq_candidates.append(seq_file)
                            break
                
                if seq_candidates:
                    # Copy to ground_truth
                    ground_truth_assembly_dir = (
                        workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
                        assembly_name
                    )
                    ground_truth_assembly_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(seq_candidates[0], ground_truth_assembly_dir / "sequence.json")
                    assembly_messages.append(f"  ✓ Saved sequence to ground_truth")
                else:
                    assembly_messages.append(f"  ⚠️  No sequence.json found in run")
            
            # 2. Load sequence_renderings from ground_truth or run
            ground_truth_rend_dir = (
                workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
                assembly_name / "renderings"
            )
            
            if ground_truth_rend_dir.exists():
                assembly_messages.append(f"  ✓ Renderings found in ground_truth")
            else:
                # Try to find in run directory (nested in assembly_sequence_run{N}/)
                rend_candidates = []
                for item in assembly_dir.iterdir():
                    if item.is_dir() and item.name.startswith("assembly_sequence_run"):
                        rend_dir = item / "sequence_renderings"
                        if rend_dir.exists():
                            rend_candidates.append(rend_dir)
                            break
                
                if rend_candidates:
                    # Copy to ground_truth
                    ground_truth_assembly_dir = (
                        workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
                        assembly_name
                    )
                    ground_truth_assembly_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(
                        rend_candidates[0],
                        ground_truth_assembly_dir / "renderings",
                        dirs_exist_ok=True
                    )
                    rend_count = len(list((ground_truth_assembly_dir / "renderings").glob("*")))
                    assembly_messages.append(f"  ✓ Saved {rend_count} renderings to ground_truth")
                else:
                    assembly_messages.append(f"  ⚠️  No sequence_renderings found in run")
            
            # 2b. Copy interaction_analysis.json (NEW) if it exists
            ia_candidates = []
            for item in assembly_dir.iterdir():
                if item.is_dir() and item.name.startswith("assembly_sequence_run"):
                    ia_file = item / "interaction_analysis.json"
                    if ia_file.exists():
                        ia_candidates.append(ia_file)
                        break
            
            if ia_candidates:
                shutil.copy2(ia_candidates[0], checkpoint_assembly_dir / "interaction_analysis.json")
                assembly_messages.append(f"  ✓ Copied interaction_analysis.json")
            else:
                assembly_messages.append(f"  ⓘ No interaction_analysis.json found (optional)")
            
            # 3. Copy BOM_enriched.json to checkpoint (with original name)
            bom_candidates = list(assembly_dir.glob("*_BOM_enriched.json")) + list(assembly_dir.glob("BOM_enriched.json"))
            if bom_candidates:
                shutil.copy2(bom_candidates[0], checkpoint_assembly_dir / bom_candidates[0].name)
                assembly_messages.append(f"  ✓ Copied {bom_candidates[0].name}")
            else:
                assembly_messages.append(f"  ⚠️  No BOM_enriched.json found")
            
            # 3b. Copy assembly_{assembly_name}_Overview_Enriched.json to checkpoint
            overview_candidates = list(assembly_dir.glob(f"assembly_{assembly_name}_Overview_Enriched.json"))
            if overview_candidates:
                shutil.copy2(overview_candidates[0], checkpoint_assembly_dir / f"assembly_{assembly_name}_Overview_Enriched.json")
                assembly_messages.append(f"  ✓ Copied assembly_{assembly_name}_Overview_Enriched.json")
            else:
                assembly_messages.append(f"  ⚠️  No assembly_{assembly_name}_Overview_Enriched.json found")
            
            # 4. Copy enriched_parts/ to checkpoint
            enriched_candidates = list(assembly_dir.glob("enriched_parts"))
            if enriched_candidates:
                shutil.copytree(
                    enriched_candidates[0],
                    checkpoint_assembly_dir / "enriched_parts",
                    dirs_exist_ok=True
                )
                part_count = len(list((checkpoint_assembly_dir / "enriched_parts").glob("*.json")))
                assembly_messages.append(f"  ✓ Copied {part_count} enriched_parts")
            else:
                assembly_messages.append(f"  ⚠️  No enriched_parts found")
            
            # 5. Copy stepparser_renderings to checkpoint
            stepparser_base = workspace_root / "data" / "processed" / "stepparser"
            possible_sources = [
                stepparser_base / assembly_name / f"assembly_{assembly_name}",
                stepparser_base / assembly_name / f"{assembly_name}.STEP",
                stepparser_base / assembly_name / assembly_name,
            ]
            
            source_dir = None
            for candidate in possible_sources:
                if candidate.exists():
                    source_dir = candidate
                    break
            
            if source_dir:
                target_dir = checkpoint_assembly_dir / "stepparser_renderings"
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # Find and copy images
                patterns = [
                    f"{assembly_name}.STEP-*.png",
                    f"{assembly_name}.step-*.png",
                    f"{assembly_name}-*.png",
                ]
                
                copied_count = 0
                for pattern in patterns:
                    for image_file in source_dir.glob(pattern):
                        if image_file.is_file():
                            shutil.copy2(image_file, target_dir / image_file.name)
                            copied_count += 1
                
                if copied_count > 0:
                    assembly_messages.append(f"  ✓ Copied {copied_count} stepparser renderings")
                else:
                    assembly_messages.append(f"  ⚠️  No stepparser images found")
            else:
                assembly_messages.append(f"  ⚠️  No stepparser directory found")
            
            # 6. Create metadata.json
            metadata = {
                "assembly_name": assembly_name,
                "timestamp": checkpoint_timestamp,
                "checkpoint_version": 1,
                "source_run": str(run_path),
                "created_from_run": True,
                "sequence_generation_settings": {},
                "validation_settings": {},
            }
            
            metadata_path = checkpoint_assembly_dir / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            assembly_messages.append(f"  ✓ Created metadata.json")
            
            # Print assembly messages
            for msg in assembly_messages:
                print(msg)
            
            assemblies_processed.append(assembly_name)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            assembly_messages.append(f"  ❌ Failed: {str(e)}")
    
    # 7. Create global checkpoint_metadata.json
    checkpoint_metadata_path = checkpoint_root / "checkpoint_metadata.json"
    checkpoint_metadata = {
        "checkpoint_type": "standalone",
        "timestamp": checkpoint_timestamp,
        "checkpoint_version": 1,
        "source_run": str(run_path),
        "created_from_run": True,
        "assemblies": list(assemblies.keys()),
    }
    
    with open(checkpoint_metadata_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_metadata, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"CHECKPOINT CREATION COMPLETE")
    print(f"{'='*80}")
    print(f"✓ Checkpoint path: {checkpoint_root}")
    print(f"✓ Assemblies processed: {len(assemblies_processed)}/{len(assemblies)}")
    print(f"✓ Assemblies: {', '.join(assemblies_processed)}")
    print(f"{'='*80}")
    
    return len(assemblies_processed) == len(assemblies), assembly_messages


if __name__ == "__main__":
    # ============================================================================
    # CONFIGURATION: Set these variables to use the script
    # ============================================================================
    
    # Path to the experiment run
    RUN_PATH = "data/experiments/to_evaluate"
    
    # Specific experiment name (or None to use first found)
    EXPERIMENT_NAME = "expX_most_info"
    
    # Base path for checkpoints
    CHECKPOINT_BASE = "data/checkpoints"
    
    # ============================================================================
    
    success, messages = create_checkpoint_from_run(
        run_path=Path(RUN_PATH),
        experiment_name=EXPERIMENT_NAME,
        checkpoint_base_path=CHECKPOINT_BASE
    )
    
    sys.exit(0 if success else 1)
