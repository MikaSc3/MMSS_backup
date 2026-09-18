"""
FFA Ground Truth Encoder/Decoder
Konvertiert FFA Assessment Daten zwischen String- und Integer-Repräsentation
für Machine Learning Evaluation (Confusion Matrix, F1-Score, etc.).

String → Integer: Für Ground Truth Annotation & LLM Output Evaluation
Integer → String: Für Reverse-Mapping (TODO)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

# Import all FFA-related Enums from structured_output (in agent directory)
from agent.structured_output import (
    NatureOfProvisionOption,
    PartRigidityOption,
    GrippingAreasOption,
    OrientationFeaturesOption,
    SurfaceSensibilityOption,
    AccuracyOfTargetPositionOption,
    PositioningAidsOption,
    AdditionalOrientationByRotationOption,
    AccessibilityToJoiningPositionOption,
    PositioningMotionOption,
    PositioningTolerancesOption,
    StabilityInPositionedStateOption,
    FeedingOfJoiningElementOption,
    FixingOfMountedPartOption,
)

logger = logging.getLogger(__name__)


# ============================================================================
# ENUM MAPPING CREATION
# ============================================================================

def create_ffa_enum_mapping() -> Dict[str, Dict[str, int]]:
    """
    Erstellt globales Enum-Mapping: String → Integer (1-basiert).
    
    Extrahiert alle FFA-relevanten Enums aus structured_output.py und
    erstellt ein Mapping-Dictionary für jedes Enum.
    
    Returns:
        Dict mit Struktur:
        {
            "NatureOfProvisionOption": {
                "in magazine (defined position and orientation)": 1,
                "in magazine (without defined position or orientation)": 2,
                ...
            },
            "PartRigidityOption": {
                "rigid": 1,
                "elastic": 2,
                ...
            },
            ...
        }
    """
    ffa_enum_classes = [
        # SUBPROCESS 1: SEPARATION
        NatureOfProvisionOption,
        
        # SUBPROCESS 2: HANDLING
        PartRigidityOption,
        GrippingAreasOption,
        OrientationFeaturesOption,
        SurfaceSensibilityOption,
        
        # SUBPROCESS 3: POSITIONING
        AccuracyOfTargetPositionOption,
        PositioningAidsOption,
        AdditionalOrientationByRotationOption,
        AccessibilityToJoiningPositionOption,
        PositioningMotionOption,
        PositioningTolerancesOption,
        StabilityInPositionedStateOption,
        
        # SUBPROCESS 4: JOINING
        FeedingOfJoiningElementOption,
        FixingOfMountedPartOption,
    ]
    
    mapping = {}
    
    for enum_class in ffa_enum_classes:
        class_name = enum_class.__name__
        
        # Create 1-based integer mapping for all enum values
        enum_mapping = {}
        for idx, member in enumerate(enum_class, start=1):
            enum_mapping[member.value] = idx
        
        mapping[class_name] = enum_mapping
        logger.debug(f"Created mapping for {class_name}: {len(enum_mapping)} values")
    
    logger.info(f"Created FFA enum mapping with {len(mapping)} enum classes")
    return mapping


def save_enum_mapping(mapping: Dict[str, Dict[str, int]], output_path: Path) -> None:
    """
    Speichert Enum-Mapping als JSON-Datei.
    
    Args:
        mapping: Enum-Mapping Dictionary
        output_path: Pfad zur Output-Datei (z.B. data/experiments/ffa_enum_mapping.json)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved FFA enum mapping to {output_path}")


# ============================================================================
# FFA STRIPPED → ENUM CONVERSION
# ============================================================================

def convert_ffa_stripped_to_enum(
    stripped_data: List[Dict[str, Any]], 
    enum_mapping: Dict[str, Dict[str, int]],
    assembly_name: str
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Konvertiert FFA stripped data (Strings) zu Integer-kodierten Daten.
    
    Struktur wird beibehalten, nur Enum-Strings werden durch Integers ersetzt.
    null-Werte werden zu 0.
    
    Args:
        stripped_data: Liste von Steps aus ffa_assessment_stripped.json
        enum_mapping: Enum-Mapping Dictionary (aus create_ffa_enum_mapping)
        assembly_name: Name der Assembly (für Error-Reporting)
    
    Returns:
        Tuple: (converted_data, error_messages)
        - converted_data: Liste mit Integer-kodierten Steps
        - error_messages: Liste von Fehlermeldungen
    """
    converted_steps = []
    errors = []
    
    # Handle both wrapped (with step_assessments key) and unwrapped (direct list) formats
    if isinstance(stripped_data, dict) and "step_assessments" in stripped_data:
        steps_list = stripped_data["step_assessments"]
    elif isinstance(stripped_data, list):
        steps_list = stripped_data
    else:
        errors.append(f"Assembly {assembly_name}: Unexpected data format (not dict with step_assessments or list)")
        return [], errors
    
    # Field → Enum Class Mapping
    field_to_enum = {
        # Separation
        "nature_of_provision": "NatureOfProvisionOption",
        
        # Handling
        "part_rigidity": "PartRigidityOption",
        "gripping_areas": "GrippingAreasOption",
        "orientation_features": "OrientationFeaturesOption",
        "surface_sensibility": "SurfaceSensibilityOption",
        
        # Positioning
        "accuracy_of_target_position": "AccuracyOfTargetPositionOption",
        "positioning_aids": "PositioningAidsOption",
        "additional_orientation_by_rotation": "AdditionalOrientationByRotationOption",
        "accessibility_to_joining_position": "AccessibilityToJoiningPositionOption",
        "positioning_motion": "PositioningMotionOption",
        "positioning_tolerances": "PositioningTolerancesOption",
        "stability_in_positioned_state": "StabilityInPositionedStateOption",
        
        # Joining
        "feeding_of_joining_element": "FeedingOfJoiningElementOption",
        "fixing_of_mounted_part": "FixingOfMountedPartOption",
    }
    
    for step in steps_list:
        step_id = step.get("step_id", "UNKNOWN")
        converted_step = {}
        
        # Copy non-assessment fields as-is
        for key in ["step_id", "step_description", "base_part_id", "joining_part_id", "joining_process"]:
            if key in step:
                converted_step[key] = step[key]
        
        # Process assessment dict
        if "assessment" in step and step["assessment"]:
            converted_assessment = {}
            
            for subprocess_name, subprocess_data in step["assessment"].items():
                if subprocess_data is None:
                    converted_assessment[subprocess_name] = None
                    continue
                
                converted_subprocess = {}
                
                for field_name, field_value in subprocess_data.items():
                    # Skip reasoning fields (not needed for evaluation)
                    if field_name.endswith("_reasoning"):
                        continue
                    
                    # Check if this field needs enum conversion
                    if field_name in field_to_enum:
                        enum_class_name = field_to_enum[field_name]
                        
                        # Handle null values → 0
                        if field_value is None:
                            converted_subprocess[field_name] = 0
                        else:
                            # Lookup integer code
                            enum_map = enum_mapping.get(enum_class_name, {})
                            if field_value in enum_map:
                                converted_subprocess[field_name] = enum_map[field_value]
                            else:
                                # Error: String not found in enum
                                error_msg = (
                                    f"Assembly: {assembly_name} | "
                                    f"Step: {step_id} | "
                                    f"Field: {subprocess_name}.{field_name} | "
                                    f"Unknown value: '{field_value}' (not in {enum_class_name})"
                                )
                                errors.append(error_msg)
                                converted_subprocess[field_name] = 0  # Fallback to 0
                    else:
                        # Not an enum field, copy as-is (e.g. evidence) - but skip reasoning
                        if not field_name.endswith("_reasoning"):
                            converted_subprocess[field_name] = field_value
                
                converted_assessment[subprocess_name] = converted_subprocess
            
            converted_step["assessment"] = converted_assessment
        
        converted_steps.append(converted_step)
    
    return converted_steps, errors


# ============================================================================
# EXPERIMENT FOLDER PROCESSING
# ============================================================================

def process_experiment_folder(experiment_base_dir: Path) -> None:
    """
    Verarbeitet alle Assemblies in einem Experiment-Ordner.
    
    Struktur:
    - Input: {experiment_base_dir}/{assembly}/ffa_assessment/ffa_assessment_stripped.json
    - Output: {experiment_base_dir}/evaluation/run_{timestamp}/{assembly}_ffa_assessment_enum.json
    - Output: {experiment_base_dir}/evaluation/run_{timestamp}/ffa_enum_mapping.json (global, einmalig)
    
    Args:
        experiment_base_dir: Pfad zum Experiment-Basisverzeichnis
                            (z.B. data/experiments/run_2026-02-06_112449/default)
    
    Example:
        >>> process_experiment_folder(Path("data/experiments/run_2026-02-06_112449/default"))
    """
    experiment_base_dir = Path(experiment_base_dir)
    
    if not experiment_base_dir.exists():
        logger.error(f"Experiment directory does not exist: {experiment_base_dir}")
        print(f"❌ Error: Directory not found: {experiment_base_dir}")
        return
    
    # Create enum mapping (global, same for all assemblies)
    print("\n" + "="*80)
    print("FFA GROUND TRUTH ENCODER - String → Integer Conversion")
    print("="*80)
    print(f"\nExperiment Directory: {experiment_base_dir}")
    print("\n[1/4] Creating FFA Enum Mapping...")
    
    enum_mapping = create_ffa_enum_mapping()
    print(f"      ✓ Created mapping for {len(enum_mapping)} enum classes")
    
    # Extract experiment name from path (last directory component)
    experiment_name = experiment_base_dir.name
    
    # Create output directory in data/evaluation/ with experiment name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace_root = Path(__file__).resolve().parents[1]  # apa_from_cad root
    output_dir = workspace_root / "data" / "evaluation" / f"run_{timestamp}_{experiment_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[2/4] Output Directory: {output_dir.relative_to(workspace_root)}")
    
    # Save global enum mapping
    mapping_path = output_dir / "ffa_enum_mapping.json"
    save_enum_mapping(enum_mapping, mapping_path)
    print(f"      ✓ Saved enum mapping: {mapping_path.name}")
    
    # Find all assemblies with FFA assessment
    print(f"\n[3/4] Scanning for assemblies with FFA assessment...")
    
    assembly_dirs = []
    for item in experiment_base_dir.iterdir():
        if item.is_dir() and item.name != "evaluation":
            ffa_stripped_path = item / "ffa_assessment" / "ffa_assessment_stripped.json"
            if ffa_stripped_path.exists():
                assembly_dirs.append(item)
    
    if not assembly_dirs:
        print(f"      ⚠ No assemblies with ffa_assessment_stripped.json found")
        print(f"      Searched in: {experiment_base_dir}")
        return
    
    print(f"      ✓ Found {len(assembly_dirs)} assemblies:")
    for assembly_dir in assembly_dirs:
        print(f"        - {assembly_dir.name}")
    
    # Process each assembly
    print(f"\n[4/4] Converting FFA data to integer codes...")
    
    total_errors = []
    validation_warnings = []
    
    for assembly_dir in assembly_dirs:
        assembly_name = assembly_dir.name
        input_path = assembly_dir / "ffa_assessment" / "ffa_assessment_stripped.json"
        output_path = output_dir / f"{assembly_name}_ffa_assessment_enum.json"
        
        print(f"\n   Processing: {assembly_name}")
        print(f"      Input:  {input_path.relative_to(experiment_base_dir)}")
        
        # Load stripped data
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                stripped_file = json.load(f)
        except Exception as e:
            error_msg = f"Assembly: {assembly_name} | Failed to load {input_path}: {e}"
            total_errors.append(error_msg)
            print(f"      ❌ Error loading file: {e}")
            continue
        
        # Extract step_assessments list from the file structure
        if isinstance(stripped_file, dict) and "step_assessments" in stripped_file:
            stripped_data = stripped_file["step_assessments"]
            metadata = {k: v for k, v in stripped_file.items() if k != "step_assessments"}
        elif isinstance(stripped_file, list):
            # Fallback: if it's already a list
            stripped_data = stripped_file
            metadata = {}
        else:
            error_msg = f"Assembly: {assembly_name} | Unexpected file structure (no 'step_assessments' key)"
            total_errors.append(error_msg)
            print(f"      ❌ Error: Unexpected file structure")
            continue
        
        # Convert to enum codes
        converted_steps, errors = convert_ffa_stripped_to_enum(stripped_data, enum_mapping, assembly_name)
        
        if errors:
            total_errors.extend(errors)
            print(f"      ⚠ {len(errors)} conversion errors (see report below)")
        else:
            print(f"      ✓ Converted {len(converted_steps)} steps successfully")
        
        # Reconstruct output structure with metadata + converted steps
        output_data = {**metadata, "step_assessments": converted_steps}
        
        # Save encoded data
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"      Output: {output_path.name}")
            
            # Validate the saved file
            file_warnings = validate_enum_file(output_path, assembly_name)
            if file_warnings:
                validation_warnings.extend(file_warnings)
                print(f"      ⚠ {len(file_warnings)} validation warnings (see report below)")
            else:
                print(f"      ✓ Validation passed (no null/0 values)")
                
        except Exception as e:
            error_msg = f"Assembly: {assembly_name} | Failed to save {output_path}: {e}"
            total_errors.append(error_msg)
            print(f"      ❌ Error saving file: {e}")
    
    # Print error report
    print("\n" + "="*80)
    print("CONVERSION REPORT")
    print("="*80)
    
    if total_errors:
        print(f"\n⚠ {len(total_errors)} Conversion Errors:\n")
        for error in total_errors:
            print(f"   {error}")
    
    if validation_warnings:
        print(f"\n⚠ {len(validation_warnings)} Validation Warnings (null/0 values):\n")
        for warning in validation_warnings:
            print(f"   {warning}")
    
    if not total_errors and not validation_warnings:
        print("\n✓ All conversions completed successfully!")
        print("✓ All validations passed (no null/0 values)")
    
    print("="*80)
    
    try:
        rel_path = output_dir.relative_to(workspace_root)
    except ValueError:
        rel_path = output_dir
    
    print(f"\nOutput Location: {rel_path}")
    print(f"  - ffa_enum_mapping.json (global mapping)")
    print(f"  - {len(assembly_dirs)} × {{assembly}}_ffa_assessment_enum.json\n")


# ============================================================================
# REVERSE CONVERSION (TODO)
# ============================================================================

def convert_ffa_enum_to_string(
    enum_data: List[Dict[str, Any]], 
    enum_mapping: Dict[str, Dict[str, int]]
) -> List[Dict[str, Any]]:
    """
    TODO: Reverse conversion - Integer → String.
    
    Benötigt für: 
    - Visualisierung der LLM-Outputs nach Evaluation
    - Debugging von kodierten Ground Truth Daten
    
    Args:
        enum_data: Liste von Steps mit Integer-Codes
        enum_mapping: Enum-Mapping Dictionary
    
    Returns:
        Liste von Steps mit String-Werten
    """
    raise NotImplementedError("Reverse conversion (enum → string) not yet implemented. See TODO in ToDos.md")


def validate_enum_file(file_path: Path, assembly_name: str) -> List[str]:
    """
    Validiert eine enum JSON-Datei auf null/Null/0 Werte.
    
    Args:
        file_path: Pfad zur enum JSON-Datei
        assembly_name: Name des Assemblies (für Fehlermeldungen)
    
    Returns:
        Liste von Warnungen (leer wenn alles OK)
    """
    warnings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check step_assessments
        step_assessments = data.get("step_assessments", [])
        
        for step in step_assessments:
            step_id = step.get("step_id", "UNKNOWN")
            assessment = step.get("assessment", {})
            
            for subprocess_name, subprocess_data in assessment.items():
                if subprocess_data is None:
                    continue  # null subprocess is OK (not applicable)
                
                for field_name, field_value in subprocess_data.items():
                    # Check for problematic values
                    if field_value == 0:
                        warnings.append(f"{assembly_name} | Step {step_id} | {subprocess_name}.{field_name}: value is 0 (should be ≥1)")
                    elif field_value is None:
                        warnings.append(f"{assembly_name} | Step {step_id} | {subprocess_name}.{field_name}: value is null (should be integer)")
                    elif isinstance(field_value, str):
                        if field_value.lower() in ["null", "none", "0"]:
                            warnings.append(f"{assembly_name} | Step {step_id} | {subprocess_name}.{field_name}: value is string '{field_value}' (should be integer)")
    
    except Exception as e:
        warnings.append(f"{assembly_name} | Validation error: {e}")
    
    return warnings

def find_latest_experiment_run(experiments_base_dir: Path = Path("data/experiments")) -> Optional[Path]:
    """
    Findet den aktuellsten Experiment-Run im experiments Ordner.
    
    Sucht nach Ordnern mit Format: run_YYYY-MM-DD_HHMMSS/<experiment_name>/
    und gibt den neuesten (nach Timestamp sortiert) zurück.
    Wenn mehrere Experiment-Unterordner existieren, wird der erste alphabetisch genommen.
    
    Args:
        experiments_base_dir: Basisverzeichnis für Experiments (default: data/experiments)
    
    Returns:
        Path zum neuesten Run (z.B. data/experiments/run_2026-02-06_112449/exp1_baseline)
        oder None wenn kein Run gefunden wurde
    """
    if not experiments_base_dir.exists():
        logger.error(f"Experiments directory does not exist: {experiments_base_dir}")
        return None
    
    # Find all run_* directories
    run_dirs = []
    for item in experiments_base_dir.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            # Find experiment subdirectories (exclude system folders)
            experiment_subdirs = [
                d for d in item.iterdir() 
                if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
            ]
            
            if experiment_subdirs:
                # Use first experiment subdirectory (sorted alphabetically)
                run_dirs.append((item, sorted(experiment_subdirs)[0]))
    
    if not run_dirs:
        logger.warning(f"No run_*/<experiment> directories found in {experiments_base_dir}")
        return None
    
    # Sort by run directory name (timestamp) and take the latest
    latest_run_dir, latest_experiment_dir = sorted(run_dirs, key=lambda x: x[0].name, reverse=True)[0]
    
    logger.info(f"Found latest experiment run: {latest_experiment_dir}")
    logger.info(f"  (from run: {latest_run_dir.name}, experiment: {latest_experiment_dir.name})")
    return latest_experiment_dir


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Auto-detect latest run if no argument provided
    if len(sys.argv) < 2:
        print("No experiment directory specified. Auto-detecting latest run...")
        experiment_dir = find_latest_experiment_run()
        
        if experiment_dir is None:
            print("\n❌ Error: No experiment runs found in data/experiments/")
            print("\nUsage: python -m agent.ffa_str_to_enum <experiment_base_dir>")
            print("\nExample:")
            print("  python -m agent.ffa_str_to_enum data/experiments/run_2026-02-06_112449/exp1_baseline")
            sys.exit(1)
        
        print(f"✓ Using latest run: {experiment_dir}\n")
    else:
        experiment_dir = Path(sys.argv[1])
    
    process_experiment_folder(experiment_dir)
