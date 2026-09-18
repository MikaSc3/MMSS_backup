"""
Data Manipulation Script: Set 'automatable: 1' in Ground Truth Files

Sets the 'automatable' field to 1 for all subprocesses in ground truth files,
overwriting any existing values.
"""

import json
from pathlib import Path
from typing import Dict, Any


def add_automatable_to_subprocess(subprocess_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sets 'automatable: 1' in a subprocess dict, overwriting existing values.
    
    Args:
        subprocess_data: Subprocess assessment dict
    
    Returns:
        Updated subprocess dict
    """
    if subprocess_data is None:
        return None
    
    # Always set automatable to 1 (overwrite if exists)
    subprocess_data["automatable"] = 1
    
    return subprocess_data


def process_ground_truth_file(file_path: Path) -> None:
    """
    Processes a single ground truth JSON file, setting 'automatable: 1' for all subprocesses.
    
    Args:
        file_path: Path to the ground truth JSON file
    """
    print(f"Processing: {file_path.name}")
    
    # Load JSON
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Track changes
    changes_made = 0
    
    # Process each step assessment
    if "step_assessments" in data:
        for step in data["step_assessments"]:
            if "assessment" in step and step["assessment"]:
                assessment = step["assessment"]
                
                # Process each subprocess (separation, handling, positioning, joining)
                for subprocess_name in ["separation", "handling", "positioning", "joining"]:
                    if subprocess_name in assessment:
                        subprocess_data = assessment[subprocess_name]
                        
                        if subprocess_data is not None:
                            subprocess_data["automatable"] = 1
                            changes_made += 1
    
    # Save updated JSON
    if changes_made > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Set {changes_made} 'automatable' fields to 1")
    else:
        print(f"   • No subprocesses found to update")


def main():
    """Main function: Process all ground truth files."""
    
    # Ground truth directory
    gt_dir = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\evaluation\ground_truth")
    
    if not gt_dir.exists():
        print(f"ERROR: Ground truth directory not found: {gt_dir}")
        return
    
    # Find all JSON files
    json_files = list(gt_dir.glob("*.json"))
    
    if not json_files:
        print(f"No JSON files found in {gt_dir}")
        return
    
    print(f"Found {len(json_files)} ground truth files")
    print("=" * 80)
    
    # Process each file
    for json_file in json_files:
        process_ground_truth_file(json_file)
    
    print("=" * 80)
    print(f"✓ Completed processing {len(json_files)} files")


if __name__ == "__main__":
    main()
