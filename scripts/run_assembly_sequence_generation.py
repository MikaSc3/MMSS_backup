"""
Re-generate Assembly Sequences for existing run.

Lädt enriched Daten aus einem existierenden Run und ruft die Assembly Sequence Generation
+ Rendering Node auf. Outputs zunächst in assembly_sequence_rerun/ ablegen, dann mit
Bestätigung ins finale Verzeichnis verschieben.

Usage:
    python scripts/run_assembly_sequence_generation.py <run_folder> [--config <yaml>]
    
Example:
    python scripts/run_assembly_sequence_generation.py data/experiments/run_2026-02-17_080335
    python scripts/run_assembly_sequence_generation.py data/experiments/run_2026-02-17_080335 --config configs/full_workflow/exp1_baseline.yaml
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

# Setup paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# ============================================================================
# CONFIGURATION - Edit here
# ============================================================================
run_folder = "data/experiments/run_2026-02-16_154439"  # e.g., "data/experiments/run_2026-02-17_080335"
config_path = "configs/full_workflow/exp1_baseline.yaml"  # Optional: "configs/full_workflow/exp1_baseline.yaml" (uses default if None)
# ============================================================================

try:
    from agent.Assembly_sequence_generation import generate_assembly_sequence
    from agent.Assembly_sequence_validation import render_assembly_steps
    from agent.prompt_store import load_experiment_settings
except ImportError:
    print("❌ ERROR: Could not import required modules")
    print("   Make sure you're running from workspace root and agent/ is available")
    sys.exit(1)


def discover_assemblies_in_run(run_folder: Path) -> Dict[str, Path]:
    """
    Finde alle Assembly-Ordner in einem Run.
    
    Structure: run_TIMESTAMP/exp_name/{assembly_1}/{assembly_2}/...
    
    Returns:
        Dict: {assembly_name: assembly_output_dir}
    """
    assemblies = {}
    
    # Find all directories in run folder
    for exp_folder in run_folder.iterdir():
        if not exp_folder.is_dir() or exp_folder.name.startswith("_"):
            continue
        
        # Iterate through experiment subdirectories
        for asm_folder in exp_folder.iterdir():
            if not asm_folder.is_dir() or asm_folder.name.startswith("_"):
                continue
            
            # Check if this has the expected structure (enriched_parts, BOM, etc.)
            enriched_parts = asm_folder / "enriched_parts"
            if enriched_parts.exists():
                assemblies[asm_folder.name] = asm_folder
    
    return assemblies


def find_stepparser_assembly_dir(assembly_name: str) -> Optional[Path]:
    """
    Finde das Stepparser Assembly-Verzeichnis für einen Assembly-Namen.
    
    Sucht in: data/processed/stepparser/{assembly_name}/assembly_{assembly_name}/
    """
    stepparser_root = WORKSPACE_ROOT / "data" / "processed" / "stepparser"
    assembly_dir = stepparser_root / assembly_name / f"assembly_{assembly_name}"
    
    if assembly_dir.exists():
        return assembly_dir
    
    # Fallback: Versuche ohne neues Convention
    assembly_dir = stepparser_root / assembly_name
    if assembly_dir.exists():
        return assembly_dir
    
    return None


def get_assembly_output_dir(run_assembly_dir: Path, use_rerun: bool = True) -> Path:
    """
    Get the output directory for assembly sequence.
    
    If use_rerun=True, returns assembly_sequence_rerun/ (für previw vor Überschreiben)
    If use_rerun=False, returns assembly_sequence_run1/ (finale output)
    """
    if use_rerun:
        output_dir = run_assembly_dir / "assembly_sequence_rerun"
    else:
        output_dir = run_assembly_dir / "assembly_sequence_run1"
    
    return output_dir


def regenerate_assembly_sequence(
    assembly_name: str,
    run_assembly_dir: Path,
    config_path: Optional[Path] = None,
    use_rerun: bool = True,
) -> bool:
    """
    Regeneriere Assembly Sequence für ein Assembly.
    
    Args:
        assembly_name: Name der Baugruppe
        run_assembly_dir: Path zu experiment output (mit enriched_parts/, etc.)
        config_path: Optional custom config path
        use_rerun: If True, output to assembly_sequence_rerun/, else assembly_sequence_run1/
    
    Returns:
        True wenn erfolgreich, False sonst
    """
    print(f"\n{'='*80}")
    print(f"REGENERATING: {assembly_name}")
    print(f"{'='*80}")
    
    # Load config
    if config_path:
        os.environ["APA_EXPERIMENT_YAML"] = str(config_path)
    
    # Get stepparser assembly directory
    assembly_dir = find_stepparser_assembly_dir(assembly_name)
    if not assembly_dir:
        print(f"❌ ERROR: Stepparser assembly directory not found for {assembly_name}")
        print(f"   Expected: data/processed/stepparser/{assembly_name}/assembly_{assembly_name}/")
        return False
    
    # Get output directory
    output_dir = get_assembly_output_dir(run_assembly_dir, use_rerun=use_rerun)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Assembly Dir: {assembly_dir}")
    print(f"Run Dir: {run_assembly_dir}")
    print(f"Output Dir: {output_dir}")
    
    try:
        # Step 1: Generate assembly sequence
        print(f"\n[1/2] Generating assembly sequence...")
        result = generate_assembly_sequence(
            assembly_name=assembly_name,
            assembly_dir=assembly_dir,
            exp_output_dir=output_dir,
            json_dir=run_assembly_dir,  # Use enriched_parts, BOM from run
        )
        
        if not result or result.get("status") == "error":
            print(f"❌ ERROR: Generation failed")
            print(f"   Result: {result}")
            return False
        
        sequence_path = result.get("assembly_sequence_path")
        if sequence_path:
            print(f"✓ Assembly sequence saved: {Path(sequence_path).name}")
        else:
            print(f"⚠️  WARNING: No assembly_sequence_path returned")
        
        # Step 2: Render assembly steps (IMPORTANT - always run)
        print(f"\n[2/2] Rendering assembly steps...")
        try:
            render_result = render_assembly_steps(
                assembly_name=assembly_name,
                experiment_name="direct_run",
                exp_output_dir=output_dir,
                transparency_values=[0.0, 0.3],
            )
            
            if render_result and render_result.get("status") == "success":
                print(f"✓ Renderings created successfully")
                rendered_count = render_result.get("rendered_count", 0)
                print(f"  → {rendered_count} steps rendered")
            else:
                print(f"⚠️  WARNING: Rendering had issues")
                print(f"   Result: {render_result}")
        
        except Exception as e:
            print(f"⚠️  WARNING: Rendering failed: {e}")
            print(f"   Continuing anyway...")
        
        print(f"\n✓ Successfully regenerated {assembly_name}")
        return True
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def confirm_overwrite_single(assembly_name: str) -> bool:
    """
    Ask user to confirm overwriting a single assembly.
    
    Args:
        assembly_name: Name of the assembly
    
    Returns:
        True if user confirms, False otherwise
    """
    print("\nNew assembly sequence generated in assembly_sequence_rerun/")
    print(f"Do you want to overwrite the existing {assembly_name}/ with this new output?")
    print("\nOptions:")
    print("  yes / y  → Overwrite and keep new sequence")
    print("  no  / n  → Keep existing data, delete regenerated sequence for this assembly")
    
    while True:
        response = input("\nOverwrite? (yes/no): ").strip().lower()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("Please enter 'yes' or 'no'")


def finalize_single_assembly(run_folder: Path, assembly_name: str, overwrite: bool):
    """
    Move or delete regenerated assembly sequence for a single assembly.
    
    Args:
        run_folder: Path to run directory (contains exp_* folders)
        assembly_name: Name of the assembly to finalize
        overwrite: If True, overwrite original; if False, delete rerun
    """
    found = False
    
    for exp_folder in run_folder.iterdir():
        if not exp_folder.is_dir() or not exp_folder.name.startswith('exp'):
            continue
        
        asm_folder = exp_folder / assembly_name
        if not asm_folder.is_dir():
            continue
        
        found = True
        rerun_dir = asm_folder / "assembly_sequence_rerun"
        final_dir = asm_folder / "assembly_sequence_run1"
        
        if not rerun_dir.exists():
            print(f"  ⚠️  No rerun directory found for {assembly_name}")
            continue
        
        if overwrite:
            print(f"  • Overwriting assembly_sequence_run1/...")
            
            # Backup original
            if final_dir.exists():
                backup_dir = asm_folder / f"assembly_sequence_run1_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(final_dir), str(backup_dir))
                print(f"    ✓ Backed up to {backup_dir.name}")
            
            # Move rerun to final
            shutil.move(str(rerun_dir), str(final_dir))
            print(f"    ✓ Updated to new sequence")
        
        else:
            print(f"  • Deleting assembly_sequence_rerun/ (keeping original)...")
            shutil.rmtree(str(rerun_dir))
            print(f"    ✓ Deleted")
    
    if not found:
        print(f"  ⚠️  Assembly '{assembly_name}' not found in run folder")



def main():
    """Main entry point."""
    global run_folder, config_path
    
    # Validate run_folder is set
    if not run_folder:
        print(f"❌ ERROR: run_folder not set in script")
        print(f"   Edit line ~14 and set run_folder to your run folder path")
        print(f"   Example: run_folder = 'data/experiments/run_2026-02-17_080335'")
        sys.exit(1)
    
    run_folder_path = (WORKSPACE_ROOT / run_folder).resolve()
    
    # Validate run folder exists
    if not run_folder_path.exists():
        print(f"❌ ERROR: Run folder not found: {run_folder_path}")
        sys.exit(1)
    
    # Use default config if not specified
    if config_path is None:
        config_file = WORKSPACE_ROOT / "configs" / "full_workflow" / "exp1_baseline.yaml"
    else:
        config_file = (WORKSPACE_ROOT / config_path).resolve()
    
    if not config_file.exists():
        print(f"❌ ERROR: Config file not found: {config_file}")
        sys.exit(1)
    
    # Set environment variables
    os.environ["APA_EXPERIMENT_YAML"] = str(config_file)
    
    print(f"\n{'='*80}")
    print(f"ASSEMBLY SEQUENCE REGENERATION")
    print(f"{'='*80}\n")
    print(f"Run Folder: {run_folder_path}")
    print(f"Config: {config_file}")
    
    # Discover assemblies
    assemblies = discover_assemblies_in_run(run_folder_path)
    
    if not assemblies:
        print(f"❌ ERROR: No assemblies found in run folder")
        print(f"   Expected structure: {run_folder}/exp_name/assembly_name/enriched_parts/")
        sys.exit(1)
    
    print(f"\nFound {len(assemblies)} assemblies:")
    for asm_name in sorted(assemblies.keys()):
        print(f"  • {asm_name}")
    
    # Process each assembly
    print(f"\n{'='*80}")
    print(f"PROCESSING ASSEMBLIES")
    print(f"{'='*80}\n")
    
    successful = []
    failed = []
    
    for asm_name, asm_dir in sorted(assemblies.items()):
        config_file_path = (WORKSPACE_ROOT / config_path).resolve() if config_path else None
        success = regenerate_assembly_sequence(
            assembly_name=asm_name,
            run_assembly_dir=asm_dir,
            config_path=config_file_path,
            use_rerun=True,  # Output to assembly_sequence_rerun/
        )
        
        if success:
            successful.append(asm_name)
            
            # Ask for each assembly individually
            print(f"\n{'='*80}")
            print(f"CONFIRM OVERWRITE: {asm_name}")
            print(f"{'='*80}\n")
            
            overwrite = confirm_overwrite_single(asm_name)
            
            if overwrite:
                print(f"\n✓ Overwriting {asm_name}...")
                finalize_single_assembly(run_folder_path, asm_name, overwrite=True)
            else:
                print(f"\n⊘ Keeping original for {asm_name}, deleting rerun...")
                finalize_single_assembly(run_folder_path, asm_name, overwrite=False)
        else:
            failed.append(asm_name)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}\n")
    print(f"✓ Successfully regenerated & processed: {len(successful)}/{len(assemblies)}")
    for asm in successful:
        print(f"  • {asm}")
    
    if failed:
        print(f"\n❌ Failed to regenerate: {len(failed)}")
        for asm in failed:
            print(f"  • {asm}")
    
    print(f"\n{'='*80}")
    print(f"✓ COMPLETE")
    print(f"{'='*80}\n")
    
    sys.exit(0 if not failed else 1)



if __name__ == "__main__":
    main()
