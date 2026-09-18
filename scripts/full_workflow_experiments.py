"""
Full Workflow Experiments Orchestrator

Unified workflow that:
1. Takes a master input directory (STEP files)
2. Checks which assemblies have already been rendered
3. Renders only the missing ones (via stepparser)
4. Runs sequence-GT experiments on all assemblies

This eliminates the need to manually run stepparser and run_experiments_sequence_gt separately.

Usage:
    python scripts/full_workflow_experiments.py
    python scripts/full_workflow_experiments.py my_experiment.yaml
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from agent.config import WorkflowConfig
from agent.workflow import run_all_nodes_sequence_gt, run_all_nodes_sequence_gt_prerendered
from agent.checkpoint_utils import load_checkpoint_assemblies, validate_checkpoint, create_checkpoint
from agent.config_utils import load_experiment_config, discover_experiments as discover_experiments_from_config
from stepparser.processor import StepProcessor


# ============================================================================
# CONFIGURATION: Master Input Directory & Rendering Settings
# ============================================================================

# FOLDER STRUCTURE & "ALREADY PROCESSED" LOGIC:
# 
# Stepparser (PHASE 1):
#   Input: {MASTER_STEP_INPUT_FOLDER}/{assembly_name}.STEP
#   Output: {STEPPARSER_OUTPUT_FOLDER}/{assembly_name}/assembly_{assembly_name}/[metadata files]
#   Already processed check: MetadataManager.check_if_processed()
#     Looks for: {assembly_name}_Overview_Stepparser.json + BOM file
#
# Experiments (PHASE 2):
#   Input: {STEPPARSER_OUTPUT_FOLDER}/{assembly_name}/[renderings] (pre-computed)
#   Output: {LLM_OUTPUT_FOLDER}/{experiment_name}/{assembly_name}/[results]
#   Already processed check: ffa_assessment/ffa_assessment.json exists
#
# ============================================================================

MASTER_STEP_INPUT_FOLDER: str = "data/input/test"  # Location of all STEP files
STEPPARSER_OUTPUT_FOLDER: str = "data/processed/stepparser3"  # Where renderings are stored (same as run_experiments_sequence_gt default)
LLM_OUTPUT_FOLDER: str = "data/experiments/singletest"  # Where LLM workflow outputs are stored
TEXTBASED_ADDITIONAL_DATA: str = "data/input/Textbased_Data"  # Optional per-assembly TXT context files
EXPERIMENT_CONFIG_FOLDER: str = "configs/sequence_gt"  # Folder containing experiment YAML config(s)
EXPERIMENT_CONFIG_NAME: Optional[str] = "all"  # YAML stem/name, .yaml path, or None/"all"

# Rendering configuration
STEPPARSER_COLOR_MODE: str = "geometry"
STEPPARSER_TRANSPARENCY_VALUES: List[float] = [0.0, 0.3]
STEPPARSER_HEADLESS_MODE: bool = True
SKIP_ALREADY_RENDERED: bool = True  # Only render missing assemblies

# Experiment execution
ENABLE_CHECKPOINT_CREATION: bool = False  # Checkpoint creation disabled by default
STEP_FILES_OVERRIDE: Optional[Union[str, List[str]]] = "all"  # Which assemblies to process
# ============================================================================


def get_rendered_assemblies() -> set:
    """
    Return set of assembly names that have already been rendered via stepparser.
    
    An assembly is considered rendered if it has the required metadata files:
    - {STEPPARSER_OUTPUT_FOLDER}/{assembly_name}/assembly_{assembly_name}/{assembly_name}_Overview_Stepparser.json
    - {STEPPARSER_OUTPUT_FOLDER}/{assembly_name}/assembly_{assembly_name}/{assembly_name}_BOM.csv or .json
    
    This matches the metadata_manager.check_if_processed() logic used by stepparser.
    """
    from stepparser.io.metadata_manager import MetadataManager
    
    output_path = Path(STEPPARSER_OUTPUT_FOLDER)
    if not output_path.exists():
        print(f"      [DEBUG] Stepparser output folder does not exist: {output_path}")
        return set()
    
    # Use the actual stepparser metadata check (same as processor.py uses)
    rendered = set()
    for asm_dir in output_path.iterdir():
        if asm_dir.is_dir():
            assembly_name = asm_dir.name
            is_processed = MetadataManager.check_if_processed(assembly_name, STEPPARSER_OUTPUT_FOLDER)
            
            # Debug: show what files exist in the current stepparser convention.
            asm_subdir = asm_dir / f"assembly_{assembly_name}"
            metadata_file = asm_subdir / f"{assembly_name}_Overview_Stepparser.json"
            bom_csv = asm_subdir / f"{assembly_name}_BOM.csv"
            bom_json = asm_subdir / f"{assembly_name}_BOM.json"
            
            print(f"      [DEBUG] {assembly_name}:")
            print(f"             Subdir exists: {asm_subdir.exists()}")
            print(f"             Metadata: {metadata_file.exists()}")
            print(f"             BOM CSV: {bom_csv.exists()}")
            print(f"             BOM JSON: {bom_json.exists()}")
            print(f"             check_if_processed result: {is_processed}")
            
            if is_processed:
                rendered.add(assembly_name)
    
    return rendered


def get_step_files() -> Dict[str, Path]:
    """
    Return mapping of assembly_name -> step_file_path for all STEP files.
    
    Assembly name is derived from filename without extension.
    """
    input_path = Path(MASTER_STEP_INPUT_FOLDER)
    if not input_path.exists():
        raise FileNotFoundError(f"Master input folder not found: {input_path}")
    
    step_files = {}
    for step_file in sorted(input_path.glob("*.STEP")):
        # Assembly name is filename without .STEP extension
        assembly_name = step_file.stem
        step_files[assembly_name] = step_file
    
    return step_files


def ensure_textbased_additional_data(assembly_names: List[str]) -> Dict[str, List[Path]]:
    """
    Ensure data/input/Textbased_Data/{assembly_name}/ exists with expected TXT files.

    Existing files are never overwritten. Missing files are created as empty
    placeholders so users can fill in optional context manually.
    """
    textbased_root = Path(TEXTBASED_ADDITIONAL_DATA)
    textbased_root.mkdir(parents=True, exist_ok=True)

    created: Dict[str, List[Path]] = {}
    for assembly_name in sorted(assembly_names):
        assembly_dir = textbased_root / assembly_name
        assembly_dir.mkdir(parents=True, exist_ok=True)

        expected_files = [
            assembly_dir / f"additional_info_{assembly_name}.txt",
            assembly_dir / f"assembly_sequence_{assembly_name}.txt",
            assembly_dir / f"ground_truth_assembly_sequence_{assembly_name}.txt",
            assembly_dir / f"remarks_{assembly_name}.txt",
        ]

        for txt_file in expected_files:
            if txt_file.exists():
                continue
            txt_file.write_text("", encoding="utf-8")
            created.setdefault(assembly_name, []).append(txt_file)

    return created


def get_completed_experiments(experiment_output_dir: Path) -> set:
    """
    Return set of assembly names that have already been processed in an experiment.
    
    An assembly is considered completed if it has:
    {experiment_output_dir}/{assembly_name}/ffa_assessment/ffa_assessment.json
    
    This matches the logic in run_experiments_sequence_gt.discover_completed_assemblies_in_experiment().
    """
    completed = set()
    if not experiment_output_dir.exists():
        return completed
    
    for asm_dir in experiment_output_dir.iterdir():
        if not asm_dir.is_dir():
            continue
        ffa_file = asm_dir / "ffa_assessment" / "ffa_assessment.json"
        if ffa_file.exists():
            completed.add(asm_dir.name)
    
    return completed


def render_missing_assemblies() -> int:
    """
    Run stepparser on any assemblies that haven't been rendered yet.
    
    Returns: number of assemblies that were rendered
    """
    print("\n" + "=" * 80)
    print("PHASE 1: RENDERING MISSING ASSEMBLIES")
    print("=" * 80)
    
    # Get all STEP files
    step_files = get_step_files()
    print(f"\n📊 Found {len(step_files)} STEP files in {MASTER_STEP_INPUT_FOLDER}")
    print(f"   Files: {', '.join(sorted(step_files.keys()))}")
    
    # Get already-rendered assemblies (using metadata check, not just folder existence)
    rendered = get_rendered_assemblies()
    print(f"\n✓ Already rendered: {len(rendered)} assemblies")
    print(f"   Check method: MetadataManager.check_if_processed()")
    print(f"   Looking for: assembly_{{AssemblyName}}/{{AssemblyName}}_Overview_Stepparser.json + BOM file")
    if rendered:
        print(f"   Assemblies: {', '.join(sorted(rendered))}")
    
    # Identify missing assemblies
    missing = set(step_files.keys()) - rendered
    print(f"\n⚠️  Missing (need rendering): {len(missing)} assemblies")
    if missing:
        print(f"   Assemblies: {', '.join(sorted(missing))}")
    else:
        print("   ✓ All assemblies already rendered! Skipping stepparser.")
        return 0
    
    # Run stepparser with skip_if_processed=True
    print(f"\n🔄 Running stepparser...")
    print(f"   Input: {MASTER_STEP_INPUT_FOLDER}")
    print(f"   Output: {STEPPARSER_OUTPUT_FOLDER}")
    print(f"   Skip already processed: {SKIP_ALREADY_RENDERED}")
    
    try:
        processor = StepProcessor(
            input_folder=MASTER_STEP_INPUT_FOLDER,
            output_folder=STEPPARSER_OUTPUT_FOLDER,
            skip_if_processed=SKIP_ALREADY_RENDERED,
            color_mode=STEPPARSER_COLOR_MODE,
            transparency_values=STEPPARSER_TRANSPARENCY_VALUES,
            headless_mode=STEPPARSER_HEADLESS_MODE,
        )
        processor.process_all_step_files()
        print("\n✅ Stepparser completed successfully")
        return len(missing)
    except Exception as e:
        print(f"\n❌ Stepparser failed: {e}")
        raise


def discover_experiments() -> List[Path]:
    """Resolve experiment YAML files from the configured folder/name."""
    config_folder = Path(EXPERIMENT_CONFIG_FOLDER)
    config_name = EXPERIMENT_CONFIG_NAME

    if config_name and str(config_name).lower() not in {"all", "*"}:
        config_path = Path(str(config_name))
        if not config_path.suffix:
            config_path = config_folder / f"{config_path.name}.yaml"
        elif not config_path.is_absolute() and config_path.parent == Path("."):
            config_path = config_folder / config_path

        return [config_path] if config_path.exists() else []

    if not config_folder.exists():
        return []

    return [
        yaml_file for yaml_file in sorted(config_folder.glob("*.yaml"))
        if yaml_file.name != "exp_example.yaml"
    ]


def run_experiments():
    """Run sequence-GT experiments using run_experiments_sequence_gt.py logic."""
    print("\n" + "=" * 80)
    print("PHASE 2: RUNNING EXPERIMENTS WITH GROUND TRUTH SEQUENCES")
    print("=" * 80)
    
    # Get the STEP files that actually exist in master input
    valid_assemblies = set(get_step_files().keys())
    print(f"\n✓ Valid assemblies (from master input): {len(valid_assemblies)}")
    print(f"   {', '.join(sorted(valid_assemblies))}")
    
    # Get all assemblies currently in stepparser
    stepparser_path = Path(STEPPARSER_OUTPUT_FOLDER)
    if stepparser_path.exists():
        all_in_stepparser = {d.name for d in stepparser_path.iterdir() if d.is_dir() and not d.name.startswith("_")}
        orphaned = all_in_stepparser - valid_assemblies
        
        if orphaned:
            print(f"\n⚠️  Orphaned assemblies in stepparser (no STEP file): {len(orphaned)}")
            print(f"   {', '.join(sorted(orphaned))}")
            print(f"\n   🧹 Removing orphaned folders from stepparser...")
            for orphan_name in orphaned:
                orphan_path = stepparser_path / orphan_name
                try:
                    import shutil
                    shutil.rmtree(orphan_path)
                    print(f"      ✓ Removed: {orphan_name}")
                except Exception as e:
                    print(f"      ✗ Failed to remove {orphan_name}: {e}")
    
    # Discover experiment configs
    yaml_files = discover_experiments()
    if not yaml_files:
        print("❌ No experiment YAML files found!")
        return False
    
    print(f"\n📋 Found {len(yaml_files)} experiment config(s):")
    for yaml_file in yaml_files:
        print(f"   - {yaml_file.name}")
    
    # Import and run the experiment logic from run_experiments_sequence_gt
    try:
        # Import the function that orchestrates experiment runs
        from importlib import import_module

        run_single_experiment = import_module("3_run_experiments_sequence_gt").run_single_experiment
        
        print(f"\n🚀 Starting experiment workflow...")
        print(f"   Processing {len(valid_assemblies)} valid assemblies with STEP files")
        
        for yaml_file in yaml_files:
            print(f"\n   📌 Processing: {yaml_file.name}")
            
            # Run experiment with rendering already done
            # The stepparser_root points to where renderings are stored
            run_single_experiment(
                experiment_yaml=yaml_file,
                stepparser_root=Path(STEPPARSER_OUTPUT_FOLDER),
                run_root_dir=Path(LLM_OUTPUT_FOLDER),
            )
        
        print("\n✅ Experiments completed successfully")
        return True
    except Exception as e:
        print(f"\n❌ Experiment execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main orchestration logic."""
    print("\n" + "=" * 80)
    print("FULL WORKFLOW EXPERIMENTS ORCHESTRATOR")
    print("=" * 80)
    print(f"Master Input Directory: {MASTER_STEP_INPUT_FOLDER}")
    print(f"Rendering Output: {STEPPARSER_OUTPUT_FOLDER}")
    print(f"LLM Output: {LLM_OUTPUT_FOLDER}")
    print(f"Textbased Additional Data: {TEXTBASED_ADDITIONAL_DATA}")
    print(f"Checkpoint Creation: {'ENABLED' if ENABLE_CHECKPOINT_CREATION else 'DISABLED'}")
    
    start_time = time.time()
    
    try:
        # Phase 0: Ensure optional per-assembly text data folders/files exist
        step_files = get_step_files()
        created_text_files = ensure_textbased_additional_data(list(step_files.keys()))
        if created_text_files:
            print("\n" + "=" * 80)
            print("PHASE 0: PREPARING TEXTBASED ADDITIONAL DATA")
            print("=" * 80)
            for assembly_name, files in created_text_files.items():
                print(f"  Created {len(files)} file(s) for {assembly_name}:")
                for file_path in files:
                    print(f"    - {file_path}")
        else:
            print("\n✓ Textbased additional data folders/files already exist")

        # Phase 1: Render missing assemblies
        rendered_count = render_missing_assemblies()
        
        # Phase 2: Run experiments
        success = run_experiments()
        
        elapsed = time.time() - start_time
        print("\n" + "=" * 80)
        print("WORKFLOW COMPLETE")
        print("=" * 80)
        print(f"⏱️  Total time: {elapsed / 60:.1f} minutes")
        print(f"📊 Rendered: {rendered_count} new assemblies")
        print(f"✅ Status: {'SUCCESS' if success else 'FAILED'}")
        print("=" * 80 + "\n")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Workflow failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
