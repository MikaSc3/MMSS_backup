"""
FFA Enum to String Decoder

Konvertiert Integer-kodierte FFA Assessment Daten zurück zu String-Repräsentation.
Verwendet das ffa_enum_mapping.json aus dem evaluation Run.

Integer → String: Für Visualisierung nach Evaluation, Debugging
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def find_latest_evaluation_run(evaluation_base_dir: Path = Path("data/evaluation")) -> Optional[Path]:
    """
    Findet den aktuellsten Evaluation-Run im evaluation Ordner.
    
    Sucht nach Ordnern mit Format: run_YYYYMMDD_HHMMSS/
    und gibt den neuesten (nach Timestamp sortiert) zurück.
    
    Args:
        evaluation_base_dir: Basisverzeichnis für Evaluations (default: data/evaluation)
    
    Returns:
        Path zum neuesten Run (z.B. data/evaluation/run_20260209_120113)
        oder None wenn kein Run gefunden wurde
    """
    if not evaluation_base_dir.exists():
        logger.error(f"Evaluation directory does not exist: {evaluation_base_dir}")
        return None
    
    # Find all run_* directories
    run_dirs = [item for item in evaluation_base_dir.iterdir() 
                if item.is_dir() and item.name.startswith("run_")]
    
    if not run_dirs:
        logger.warning(f"No run_* directories found in {evaluation_base_dir}")
        return None
    
    # Sort by directory name (which includes timestamp) and take the latest
    latest_run = sorted(run_dirs, key=lambda x: x.name, reverse=True)[0]
    
    logger.info(f"Found latest evaluation run: {latest_run}")
    return latest_run


def load_enum_mapping(mapping_path: Path) -> Dict[str, Dict[str, int]]:
    """
    Lädt das Enum-Mapping aus JSON-Datei.
    
    Args:
        mapping_path: Pfad zur ffa_enum_mapping.json
    
    Returns:
        Enum-Mapping Dictionary (String → Int)
    """
    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    
    logger.info(f"Loaded enum mapping with {len(mapping)} enum classes")
    return mapping


def create_reverse_mapping(enum_mapping: Dict[str, Dict[str, int]]) -> Dict[str, Dict[int, str]]:
    """
    Erstellt Reverse-Mapping: Integer → String.
    
    Args:
        enum_mapping: Original mapping (String → Int)
    
    Returns:
        Reverse mapping (Int → String)
    """
    reverse_mapping = {}
    
    for enum_class_name, str_to_int in enum_mapping.items():
        int_to_str = {v: k for k, v in str_to_int.items()}
        reverse_mapping[enum_class_name] = int_to_str
    
    logger.debug(f"Created reverse mapping for {len(reverse_mapping)} enum classes")
    return reverse_mapping


# ============================================================================
# FFA ENUM → STRING CONVERSION
# ============================================================================

def convert_ffa_enum_to_string(
    enum_data: List[Dict[str, Any]], 
    reverse_mapping: Dict[str, Dict[int, str]],
    assembly_name: str
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Konvertiert FFA enum data (Integers) zu String-Werten.
    
    Struktur wird beibehalten, nur Integer-Codes werden durch Strings ersetzt.
    0 wird zu null.
    
    Args:
        enum_data: Liste von Steps aus *_ffa_assessment_enum.json
        reverse_mapping: Reverse Enum-Mapping Dictionary (Int → String)
        assembly_name: Name der Assembly (für Error-Reporting)
    
    Returns:
        Tuple: (converted_data, error_messages)
        - converted_data: Liste mit String-kodierten Steps
        - error_messages: Liste von Fehlermeldungen
    """
    converted_steps = []
    errors = []
    
    # Field → Enum Class Mapping (same as in ffa_str_to_enum)
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
    
    for step in enum_data:
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
                    # Check if this field needs enum conversion
                    if field_name in field_to_enum:
                        enum_class_name = field_to_enum[field_name]
                        
                        # Handle 0 → null
                        if field_value == 0:
                            converted_subprocess[field_name] = None
                        elif isinstance(field_value, int):
                            # Lookup string value
                            reverse_map = reverse_mapping.get(enum_class_name, {})
                            if field_value in reverse_map:
                                converted_subprocess[field_name] = reverse_map[field_value]
                            else:
                                # Error: Integer not found in reverse mapping
                                error_msg = (
                                    f"Assembly: {assembly_name} | "
                                    f"Step: {step_id} | "
                                    f"Field: {subprocess_name}.{field_name} | "
                                    f"Unknown integer: {field_value} (not in {enum_class_name})"
                                )
                                errors.append(error_msg)
                                converted_subprocess[field_name] = None  # Fallback to null
                        else:
                            # Not an integer, copy as-is (shouldn't happen)
                            converted_subprocess[field_name] = field_value
                    else:
                        # Not an enum field, copy as-is
                        converted_subprocess[field_name] = field_value
                
                converted_assessment[subprocess_name] = converted_subprocess
            
            converted_step["assessment"] = converted_assessment
        
        converted_steps.append(converted_step)
    
    return converted_steps, errors


# ============================================================================
# EVALUATION RUN PROCESSING
# ============================================================================

def process_evaluation_run(evaluation_run_dir: Path = None) -> None:
    """
    Verarbeitet einen Evaluation-Run: Konvertiert Integer → String.
    
    Struktur:
    - Input: {evaluation_run_dir}/{assembly}_ffa_assessment_enum.json
    - Input: {evaluation_run_dir}/ffa_enum_mapping.json
    - Output: {evaluation_run_dir}/{assembly}_ffa_assessment_str.json
    
    Args:
        evaluation_run_dir: Pfad zum Evaluation-Run-Verzeichnis
                           (z.B. data/evaluation/run_20260209_120113)
                           Wenn None: Auto-detect latest run
    
    Example:
        >>> process_evaluation_run(Path("data/evaluation/run_20260209_120113"))
        >>> process_evaluation_run()  # Auto-detect latest
    """
    # Auto-detect latest run if not provided
    if evaluation_run_dir is None:
        print("No evaluation run directory specified. Auto-detecting latest run...")
        evaluation_run_dir = find_latest_evaluation_run()
        
        if evaluation_run_dir is None:
            print("\n❌ Error: No evaluation runs found in data/evaluation/")
            print("\nUsage: python -m agent.ffa_enum_to_str [<evaluation_run_dir>]")
            print("\nExample:")
            print("  python -m agent.ffa_enum_to_str data/evaluation/run_20260209_120113")
            return
        
        print(f"✓ Using latest run: {evaluation_run_dir}\n")
    else:
        evaluation_run_dir = Path(evaluation_run_dir)
    
    if not evaluation_run_dir.exists():
        logger.error(f"Evaluation run directory does not exist: {evaluation_run_dir}")
        print(f"❌ Error: Directory not found: {evaluation_run_dir}")
        return
    
    # Header
    print("\n" + "="*80)
    print("FFA ENUM TO STRING DECODER - Integer → String Conversion")
    print("="*80)
    print(f"\nEvaluation Run Directory: {evaluation_run_dir}")
    
    # Load enum mapping
    print("\n[1/3] Loading Enum Mapping...")
    mapping_path = evaluation_run_dir / "ffa_enum_mapping.json"
    
    if not mapping_path.exists():
        print(f"      ❌ Error: ffa_enum_mapping.json not found in {evaluation_run_dir}")
        return
    
    enum_mapping = load_enum_mapping(mapping_path)
    print(f"      ✓ Loaded mapping for {len(enum_mapping)} enum classes")
    
    # Create reverse mapping
    reverse_mapping = create_reverse_mapping(enum_mapping)
    print(f"      ✓ Created reverse mapping (Int → String)")
    
    # Find all encoded files
    print(f"\n[2/3] Scanning for encoded FFA files...")
    
    encoded_files = list(evaluation_run_dir.glob("*_ffa_assessment_enum.json"))
    
    if not encoded_files:
        print(f"      ⚠ No *_ffa_assessment_enum.json files found")
        print(f"      Searched in: {evaluation_run_dir}")
        return
    
    print(f"      ✓ Found {len(encoded_files)} encoded files:")
    for file in encoded_files:
        assembly_name = file.name.replace("_ffa_assessment_enum.json", "")
        print(f"        - {assembly_name}")
    
    # Process each file
    print(f"\n[3/3] Converting Integer codes to Strings...")
    
    total_errors = []
    
    for encoded_file in encoded_files:
        assembly_name = encoded_file.name.replace("_ffa_assessment_enum.json", "")
        output_path = evaluation_run_dir / f"{assembly_name}_ffa_assessment_str.json"
        
        print(f"\n   Processing: {assembly_name}")
        print(f"      Input:  {encoded_file.name}")
        
        # Load encoded data
        try:
            with open(encoded_file, 'r', encoding='utf-8') as f:
                encoded_file_data = json.load(f)
        except Exception as e:
            error_msg = f"Assembly: {assembly_name} | Failed to load {encoded_file}: {e}"
            total_errors.append(error_msg)
            print(f"      ❌ Error loading file: {e}")
            continue
        
        # Extract step_assessments list
        if isinstance(encoded_file_data, dict) and "step_assessments" in encoded_file_data:
            enum_data = encoded_file_data["step_assessments"]
            metadata = {k: v for k, v in encoded_file_data.items() if k != "step_assessments"}
        elif isinstance(encoded_file_data, list):
            enum_data = encoded_file_data
            metadata = {}
        else:
            error_msg = f"Assembly: {assembly_name} | Unexpected file structure"
            total_errors.append(error_msg)
            print(f"      ❌ Error: Unexpected file structure")
            continue
        
        # Convert to strings
        decoded_steps, errors = convert_ffa_enum_to_string(enum_data, reverse_mapping, assembly_name)
        
        if errors:
            total_errors.extend(errors)
            print(f"      ⚠ {len(errors)} conversion errors (see report below)")
        else:
            print(f"      ✓ Decoded {len(decoded_steps)} steps successfully")
        
        # Reconstruct output structure
        output_data = {**metadata, "step_assessments": decoded_steps}
        
        # Save decoded data
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"      Output: {output_path.name}")
        except Exception as e:
            error_msg = f"Assembly: {assembly_name} | Failed to save {output_path}: {e}"
            total_errors.append(error_msg)
            print(f"      ❌ Error saving file: {e}")
    
    # Print error report
    print("\n" + "="*80)
    print("DECODING REPORT")
    print("="*80)
    
    if total_errors:
        print(f"\n⚠ {len(total_errors)} Errors Found:\n")
        for error in total_errors:
            print(f"   {error}")
        print("\n" + "="*80)
    else:
        print("\n✓ All decodings completed successfully!")
        print("="*80)
    
    workspace_root = Path(__file__).resolve().parents[1]
    try:
        rel_path = evaluation_run_dir.relative_to(workspace_root)
    except ValueError:
        rel_path = evaluation_run_dir
    
    print(f"\nOutput Location: {rel_path}")
    print(f"  - {len(encoded_files)} × {{assembly}}_ffa_assessment_str.json\n")


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Auto-detect latest run if no argument provided
    if len(sys.argv) < 2:
        process_evaluation_run()
    else:
        evaluation_run_dir = Path(sys.argv[1])
        process_evaluation_run(evaluation_run_dir)
