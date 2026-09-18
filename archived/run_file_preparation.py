"""
File Preparation Script
Creates folder structure and placeholder files for STEP assemblies
"""

import os
from pathlib import Path
from datetime import datetime


def main():
    # Define paths
    step_input_dir = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\input\STEP")
    processed_base_dir = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\processed\File preparation")
    
    # Get all STEP files
    step_files = list(step_input_dir.glob("*.step")) + list(step_input_dir.glob("*.stp"))
    
    if not step_files:
        print(f"No STEP files found in {step_input_dir}")
        return
    
    print(f"Found {len(step_files)} STEP file(s):")
    for step_file in step_files:
        print(f"  - {step_file.name}")
    
    # Create run timestamp folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = processed_base_dir / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)
    print(f"\nCreated run folder: {run_folder}")
    
    # Process each STEP file
    for step_file in step_files:
        # Get assembly name (without extension)
        assembly_name = step_file.stem
        
        # Create assembly folder
        assembly_folder = run_folder / assembly_name
        assembly_folder.mkdir(exist_ok=True)
        
        # Create the four txt files
        additional_info_file = assembly_folder / f"additional_info_{assembly_name}.txt"
        assembly_sequence_file = assembly_folder / f"assembly_sequence_{assembly_name}.txt"
        ground_truth_sequence_file = assembly_folder / f"ground_truth_assembly_sequence_{assembly_name}.txt"
        remarks_file = assembly_folder / f"remarks_{assembly_name}.txt"
        
        # Create txt files with header text
        additional_info_file.write_text("Additional Info\n", encoding='utf-8')
        assembly_sequence_file.write_text("Assembly Sequence Master given by Expert\n", encoding='utf-8')
        ground_truth_sequence_file.write_text("Ground Truth Assembly Sequence:\n", encoding='utf-8')
        remarks_file.write_text("", encoding='utf-8')  # Empty file
        
        print(f"  Created folder and files for: {assembly_name}")
    
    print(f"\nFile preparation complete!")
    print(f"Output directory: {run_folder}")


if __name__ == "__main__":
    main()
