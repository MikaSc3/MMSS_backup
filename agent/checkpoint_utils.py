"""
Checkpoint Management Utilities

Handles creation, validation, and loading of workflow checkpoints.
Checkpoints are standalone, reproducible snapshots of data after sequence rendering
that enable re-running FFA assessment with different settings.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone


def copy_stepparser_renderings(
    assembly_name: str,
    checkpoint_assembly_dir: Path
) -> List[str]:
    """
    Copy all Stepparser-generated rendering images to checkpoint.
    
    Searches in data/processed/stepparser/{assembly}/assembly_{assembly}/
    for images matching patterns:
    - {assembly}.STEP-*.png (standard)
    - {assembly}.step-*.png (fallback)
    - {assembly}-*.png (legacy)
    
    Args:
        assembly_name: Assembly name (e.g., "Connecting_Rod")
        checkpoint_assembly_dir: Path to checkpoint assembly directory
        
    Returns:
        List of copied image filenames
        
    Raises:
        Warning if no images found (non-fatal)
    """
    workspace_root = Path(__file__).resolve().parents[1]
    stepparser_base = workspace_root / "data" / "processed" / "stepparser"
    
    # Possible source directories
    possible_sources = [
        stepparser_base / assembly_name / f"assembly_{assembly_name}",
        stepparser_base / assembly_name / f"{assembly_name}.STEP",
        stepparser_base / assembly_name / assembly_name,
    ]
    
    source_dir = None
    for candidate in possible_sources:
        if candidate.exists() and candidate.is_dir():
            source_dir = candidate
            break
    
    if not source_dir:
        print(f"  ⚠ copy_stepparser_renderings: No stepparser directory found for {assembly_name}")
        print(f"    Searched: {possible_sources}")
        return []
    
    # Create target directory
    target_dir = checkpoint_assembly_dir / "stepparser_renderings"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all image files with matching patterns
    copied_files = []
    patterns = [
        f"{assembly_name}.STEP-*.png",
        f"{assembly_name}.step-*.png",
        f"{assembly_name}-*.png",
    ]
    
    for pattern in patterns:
        for image_file in source_dir.glob(pattern):
            if image_file.is_file():
                target_path = target_dir / image_file.name
                shutil.copy2(image_file, target_path)
                copied_files.append(image_file.name)
    
    if not copied_files:
        print(f"  ⚠ copy_stepparser_renderings: No images found for {assembly_name}")
        print(f"    Source: {source_dir}")
        return []
    
    print(f"  ✓ Copied {len(copied_files)} stepparser renderings to checkpoint")
    
    return copied_files


def create_checkpoint(
    exp_output_dir: Path,
    assembly_name: str,
    checkpoint_base_path: str = "data/checkpoints",
    current_settings: Optional[Dict[str, Any]] = None,
    protect_ground_truth: bool = False,
    checkpoint_dir_override: Optional[Path] = None,
) -> Path:
    """
    Create a standalone checkpoint after sequence rendering.
    
    A checkpoint is a snapshot containing:
    - assembly_sequence.json (from node 7) → stored in data/ground_truth_assembly_sequence/sequences/
    - sequence_renderings/ (from node 8) → stored in data/ground_truth_assembly_sequence/renderings/
    - stepparser_renderings/ (copied from processed/stepparser)
    - BOM_enriched.json (from node 6)
    - enriched_parts/ (from node 5)
    - metadata.json (settings + assembly info)
    
    Note: Sequences and renderings are stored in ground_truth for reusability.
    Other data stays in checkpoint for isolation.
    
    All checkpoints for a run are collected under {base}/{timestamp}/
    
    Args:
        exp_output_dir: Current experiment output directory
        assembly_name: Assembly being processed
        checkpoint_base_path: Base path for checkpoints (relative to workspace root)
        current_settings: Current settings dict (for metadata)
        protect_ground_truth: If True, skip ALL writes to data/ground_truth/.
            Must be set when running the sequence_gt workflow where the ground truth
            is the INPUT (not the output) — writing back would corrupt the reference data.
        checkpoint_dir_override: If provided, use this directory as the parent for
            the assembly checkpoint folder instead of computing {base}/{timestamp}.
            Use this to share a single checkpoint root across all assemblies and
            experiments in one run (e.g. data/checkpoints/{run_ts}/{exp_name}).
        
    Returns:
        Path to created checkpoint assembly directory
        
    Raises:
        FileNotFoundError: If required files missing from exp_output_dir
    """
    workspace_root = Path(__file__).resolve().parents[1]
    
    if checkpoint_dir_override is not None:
        # Use the caller-supplied directory as the parent; just add assembly_name below it
        checkpoint_root = Path(checkpoint_dir_override)
        # Derive timestamp from the override path name if possible (e.g. "2026-03-02_095819"),
        # otherwise fall back to the current time so metadata.json is always populated.
        ts_candidate = checkpoint_root.parent.name
        try:
            datetime.strptime(ts_candidate, "%Y-%m-%d_%H%M%S")
            checkpoint_timestamp = ts_candidate
        except ValueError:
            checkpoint_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    else:
        checkpoint_base = workspace_root / checkpoint_base_path
        # Determine checkpoint timestamp (use current time)
        checkpoint_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        checkpoint_root = checkpoint_base / checkpoint_timestamp
    
    checkpoint_assembly_dir = checkpoint_root / assembly_name
    
    # Create checkpoint assembly directory
    checkpoint_assembly_dir.mkdir(parents=True, exist_ok=True)
    
    exp_output_path = Path(exp_output_dir)
    
    print(f"\n[checkpoint] Creating checkpoint for {assembly_name}")
    print(f"[checkpoint] Target: {checkpoint_assembly_dir}")
    
    # 1. Save assembly_sequence.json to ground_truth/assembly_sequence_ground_truth/{assembly_name}/
    sequence_json = None
    # Try current iteration directory first
    for run_dir in exp_output_path.glob("assembly_sequence_run*"):
        candidate = run_dir / "assembly_sequence.json"
        if candidate.exists():
            sequence_json = candidate
            break
    
    # Fallback to root
    if not sequence_json:
        sequence_json = exp_output_path / "assembly_sequence.json"
    
    if not sequence_json.exists():
        raise FileNotFoundError(f"assembly_sequence.json not found in {exp_output_path}")

    if protect_ground_truth:
        # ── PROTECTED MODE ────────────────────────────────────────────────────
        # The ground_truth directory is the authoritative INPUT for this run.
        # Writing back any generated data would silently corrupt the reference.
        # Sequence + renderings are saved to the checkpoint directory only.
        print(f"  ℹ [protect_ground_truth] Skipping write to data/ground_truth/ "
              f"(sequence_gt workflow — GT is read-only input)")
        # Copy sequence.json into checkpoint dir so it's still preserved
        shutil.copy2(sequence_json, checkpoint_assembly_dir / "sequence.json")
        print(f"  ✓ Copied sequence.json into checkpoint (NOT into ground_truth)")
    else:
        # Save to ground_truth/assembly_sequence_ground_truth/{assembly_name}/
        ground_truth_assembly_dir = workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / assembly_name
        ground_truth_assembly_dir.mkdir(parents=True, exist_ok=True)
        ground_truth_seq_file = ground_truth_assembly_dir / "sequence.json"
        shutil.copy2(sequence_json, ground_truth_seq_file)
        print(f"  ✓ Saved assembly_sequence.json to ground_truth/assembly_sequence_ground_truth/{assembly_name}/")

    # 2. Save sequence_renderings/ — destination depends on protect_ground_truth
    sequence_renderings = None
    # Try current iteration directory first
    for run_dir in exp_output_path.glob("assembly_sequence_run*"):
        candidate = run_dir / "sequence_renderings"
        if candidate.exists():
            sequence_renderings = candidate
            break

    # Fallback to root
    if not sequence_renderings:
        sequence_renderings = exp_output_path / "sequence_renderings"

    if sequence_renderings.exists():
        if protect_ground_truth:
            # Save renderings into checkpoint only
            checkpoint_renderings = checkpoint_assembly_dir / "sequence_renderings"
            if checkpoint_renderings.exists():
                shutil.rmtree(checkpoint_renderings)
            shutil.copytree(sequence_renderings, checkpoint_renderings)
            rendering_count = len(list(checkpoint_renderings.glob("*")))
            print(f"  ✓ Copied sequence_renderings/ into checkpoint ({rendering_count} files) (NOT into ground_truth)")
        else:
            ground_truth_assembly_dir = workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / assembly_name
            ground_truth_renderings = ground_truth_assembly_dir / "renderings"
            if ground_truth_renderings.exists():
                shutil.rmtree(ground_truth_renderings)
            shutil.copytree(sequence_renderings, ground_truth_renderings)
            rendering_count = len(list(ground_truth_renderings.glob("*")))
            print(f"  ✓ Saved sequence_renderings/ to ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/ ({rendering_count} files)")
    else:
        print(f"  ⚠ sequence_renderings not found, skipping")
    
    # 3. Copy BOM_enriched.json to checkpoint (with original name)
    bom_files = list(exp_output_path.glob(f"{assembly_name}_BOM_enriched.json"))
    if not bom_files:
        bom_files = list(exp_output_path.glob("*_BOM_enriched.json"))
    
    if bom_files:
        shutil.copy2(bom_files[0], checkpoint_assembly_dir / bom_files[0].name)
        print(f"  ✓ Copied {bom_files[0].name} to checkpoint")
    else:
        print(f"  ⚠ BOM_enriched.json not found, skipping")
    
    # 3b. Copy assembly_{assembly_name}_Overview_Enriched.json to checkpoint
    overview_files = list(exp_output_path.glob(f"assembly_{assembly_name}_Overview_Enriched.json"))
    if overview_files:
        shutil.copy2(overview_files[0], checkpoint_assembly_dir / f"assembly_{assembly_name}_Overview_Enriched.json")
        print(f"  ✓ Copied assembly_{assembly_name}_Overview_Enriched.json to checkpoint")
    else:
        print(f"  ⚠ assembly_{assembly_name}_Overview_Enriched.json not found, skipping")
    
    # 4. Copy enriched_parts/ to checkpoint
    enriched_parts = exp_output_path / "enriched_parts"
    if enriched_parts.exists():
        target_enriched = checkpoint_assembly_dir / "enriched_parts"
        if target_enriched.exists():
            shutil.rmtree(target_enriched)
        shutil.copytree(enriched_parts, target_enriched)
        part_count = len(list(target_enriched.glob("*.json")))
        print(f"  ✓ Copied enriched_parts/ to checkpoint ({part_count} part files)")
    else:
        print(f"  ⚠ enriched_parts not found, skipping")
    
    # 4b. Copy interaction_analysis.json to checkpoint (optional)
    ia_json = None
    # Look in assembly_sequence_run* subdirs first (matches workflow output structure)
    for run_dir in sorted(exp_output_path.glob("assembly_sequence_run*")):
        candidate = run_dir / "interaction_analysis.json"
        if candidate.exists():
            ia_json = candidate
            break
    # Fallback: root of experiment output dir
    if ia_json is None:
        candidate = exp_output_path / "interaction_analysis.json"
        if candidate.exists():
            ia_json = candidate

    if ia_json is not None:
        shutil.copy2(ia_json, checkpoint_assembly_dir / "interaction_analysis.json")
        print(f"  ✓ Copied interaction_analysis.json to checkpoint")
    else:
        print(f"  ⓘ interaction_analysis.json not found (optional, skipping)")

    # 5. Copy stepparser renderings
    copy_stepparser_renderings(assembly_name, checkpoint_assembly_dir)
    
    # 6. Write assembly-specific metadata.json
    metadata = {
        "assembly_name": assembly_name,
        "timestamp": checkpoint_timestamp,
        "checkpoint_version": 1,
        "sequence_generation_settings": current_settings.get("sequence_settings", {}) if current_settings else {},
        "validation_settings": current_settings.get("validation_settings", {}) if current_settings else {},
    }
    
    metadata_path = checkpoint_assembly_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Created metadata.json")
    
    # 7. Update global checkpoint_metadata.json
    checkpoint_metadata_path = checkpoint_root / "checkpoint_metadata.json"
    if checkpoint_metadata_path.exists():
        with open(checkpoint_metadata_path, "r", encoding="utf-8") as f:
            checkpoint_metadata = json.load(f)
    else:
        checkpoint_metadata = {
            "checkpoint_type": "standalone",
            "timestamp": checkpoint_timestamp,
            "checkpoint_version": 1,
            "assemblies": []
        }
    
    # Add assembly to list if not present
    if assembly_name not in checkpoint_metadata.get("assemblies", []):
        checkpoint_metadata["assemblies"].append(assembly_name)
    
    with open(checkpoint_metadata_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_metadata, f, indent=2, ensure_ascii=False)
    
    print(f"  ✓ Updated checkpoint_metadata.json")
    print(f"[checkpoint] Checkpoint created: {checkpoint_assembly_dir}")
    
    return checkpoint_assembly_dir


def validate_checkpoint(checkpoint_path: str) -> tuple[bool, List[str]]:
    """
    Validate that a checkpoint has all required files for FFA assessment.
    
    Note: assembly_sequence.json and sequence_renderings are in ground_truth,
    NOT in checkpoint.
    
    Required files per assembly in checkpoint:
    - metadata.json (optional)
    - stepparser_renderings/ (directory)
    - BOM_enriched.json
    - enriched_parts/ (directory)
    
    Required files in ground_truth/assembly_sequence_ground_truth/{assembly_name}/:
    - sequence.json
    - renderings/ (directory)
    
    Args:
        checkpoint_path: Path to checkpoint root (e.g., data/checkpoints/{timestamp}/)
        
    Returns:
        Tuple of (is_valid: bool, errors: List[str])
    """
    checkpoint = Path(checkpoint_path)
    errors = []
    
    if not checkpoint.exists():
        return False, [f"Checkpoint path does not exist: {checkpoint}"]
    
    # Try to load checkpoint_metadata if it exists, otherwise discover assemblies
    assemblies = []
    checkpoint_metadata = checkpoint / "checkpoint_metadata.json"
    
    if checkpoint_metadata.exists():
        try:
            with open(checkpoint_metadata, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            assemblies = metadata.get("assemblies", [])
        except Exception as e:
            errors.append(f"Failed to read checkpoint_metadata.json: {e}")
    
    # If metadata doesn't exist or has no assemblies, discover them
    if not assemblies:
        # Auto-discover assemblies from subdirectories
        for item in checkpoint.iterdir():
            if item.is_dir() and not item.name.startswith("_") and item.name != "checkpoint_metadata.json":
                assemblies.append(item.name)
    
    if not assemblies:
        return False, ["No assemblies found in checkpoint"]
    
    # Checkpoint no longer contains sequences/renderings
    required_dirs = ["stepparser_renderings", "enriched_parts"]
    
    # Check ground_truth for sequences/renderings
    workspace_root = Path(__file__).resolve().parents[1]
    ground_truth_base = workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth"
    
    for assembly_name in assemblies:
        assembly_dir = checkpoint / assembly_name
        
        if not assembly_dir.exists():
            errors.append(f"Assembly directory missing in checkpoint: {assembly_name}")
            continue
        
        # Check checkpoint directories
        for required in required_dirs:
            req_path = assembly_dir / required
            if not req_path.exists():
                errors.append(f"{assembly_name}: Missing directory {required}")
        
        # Check for BOM_enriched.json (accept both standardized and prefixed names)
        bom_candidates = list(assembly_dir.glob("BOM_enriched.json")) + list(assembly_dir.glob("*_BOM_enriched.json"))
        if not bom_candidates:
            errors.append(f"{assembly_name}: Missing file BOM_enriched.json")
        
        # Check ground_truth files
        ground_truth_assembly_dir = ground_truth_base / assembly_name
        ground_truth_seq = ground_truth_assembly_dir / "sequence.json"
        ground_truth_rend = ground_truth_assembly_dir / "renderings"
        
        if not ground_truth_seq.exists():
            errors.append(f"{assembly_name}: Missing sequence in ground_truth/assembly_sequence_ground_truth/{assembly_name}/")
        
        if not ground_truth_rend.exists():
            errors.append(f"{assembly_name}: Missing renderings in ground_truth/assembly_sequence_ground_truth/{assembly_name}/")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def load_ground_truth_sequence(assembly_name: str) -> Optional[Dict[str, Any]]:
    """
    Load assembly_sequence.json from ground_truth/assembly_sequence_ground_truth/{assembly_name}/
    
    Args:
        assembly_name: Assembly name (e.g., "Connecting_Rod")
        
    Returns:
        Loaded sequence dict, or None if not found
    """
    workspace_root = Path(__file__).resolve().parents[1]
    sequence_file = (
        workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
        assembly_name / "sequence.json"
    )
    
    if not sequence_file.exists():
        print(f"  ⚠ Ground truth sequence not found: {sequence_file}")
        return None
    
    try:
        with open(sequence_file, "r", encoding="utf-8") as f:
            sequence = json.load(f)
        return sequence
    except Exception as e:
        print(f"  ⚠ Failed to load sequence: {e}")
        return None


def get_ground_truth_renderings_path(assembly_name: str) -> Optional[Path]:
    """
    Get path to assembly sequence renderings in ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/
    
    Args:
        assembly_name: Assembly name (e.g., "Connecting_Rod")
        
    Returns:
        Path to renderings directory, or None if not found
    """
    workspace_root = Path(__file__).resolve().parents[1]
    renderings_path = (
        workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth" / 
        assembly_name / "renderings"
    )
    
    if not renderings_path.exists():
        print(f"  ⚠ Ground truth renderings not found: {renderings_path}")
        return None
    
    return renderings_path


def load_checkpoint_assemblies(checkpoint_path: str) -> List[str]:
    """
    Load list of assemblies in checkpoint.
    
    First tries to load from checkpoint_metadata.json if it exists.
    If metadata doesn't exist, auto-discovers assemblies from subdirectories.
    
    Args:
        checkpoint_path: Path to checkpoint root
        
    Returns:
        List of assembly names
    """
    checkpoint = Path(checkpoint_path)
    
    # Try to load from metadata first
    checkpoint_metadata = checkpoint / "checkpoint_metadata.json"
    if checkpoint_metadata.exists():
        try:
            with open(checkpoint_metadata, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            assemblies = metadata.get("assemblies", [])
            if assemblies:
                return assemblies
        except Exception:
            pass
    
    # Fallback: auto-discover from subdirectories
    assemblies = []
    try:
        for item in checkpoint.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                assemblies.append(item.name)
    except Exception:
        pass
    
    return sorted(assemblies)
