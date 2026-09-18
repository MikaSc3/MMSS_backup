"""
Debug script for Assembly Sequence Generation
Tests with worm gear demonstrator data
"""

from pathlib import Path
from datetime import datetime
import shutil
import json

def test_assembly_sequence_generation():
    """Run assembly sequence generation on worm gear demonstrator."""
    
    # Setup paths
    workspace_root = Path(__file__).parent
    assembly_name = "worm gear demonstrator"
    
    # Input paths
    stepparser_dir = workspace_root / "data" / "processed" / "stepparser" / assembly_name
    assembly_step_dir = stepparser_dir / f"assembly_{assembly_name}"  # Updated: assembly_ prefix
    source_data_dir = workspace_root / "data" / "experiments" / "run_2026-01-22_103612" / "default" / assembly_name  # Updated: latest run
    
    # Output path with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = workspace_root / "data" / "experiments" / f"debug_ASG_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"ASSEMBLY SEQUENCE GENERATION - DEBUG TEST")
    print(f"{'='*80}\n")
    print(f"Assembly: {assembly_name}")
    print(f"Stepparser Dir: {assembly_step_dir}")
    print(f"Source Data: {source_data_dir}")
    print(f"Output Dir: {output_dir}")
    print(f"\n{'='*80}\n")
    
    # Check if source directories exist
    if not assembly_step_dir.exists():
        print(f"ERROR: Assembly STEP dir not found: {assembly_step_dir}")
        return
    
    if not source_data_dir.exists():
        print(f"ERROR: Source data dir not found: {source_data_dir}")
        return
    
    # Copy enriched data to output directory
    print(f"[1/3] Copying enriched data to output directory...")
    
    # Copy enriched_parts folder if exists
    source_enriched = source_data_dir / "enriched_parts"
    if source_enriched.exists():
        dest_enriched = output_dir / "enriched_parts"
        shutil.copytree(source_enriched, dest_enriched)
        print(f"      > Copied enriched_parts/ ({len(list(dest_enriched.glob('*.json')))} files)")
    
    # Copy merged_bom files if they exist
    for bom_file in source_data_dir.glob("merged_bom*.json"):
        shutil.copy(bom_file, output_dir)
        print(f"      > Copied {bom_file.name}")
    
    # Copy any other JSON files (metadata, etc.)
    for json_file in source_data_dir.glob("*.json"):
        if not json_file.name.startswith("merged_bom"):
            shutil.copy(json_file, output_dir)
            print(f"      > Copied {json_file.name}")
    
    # Run assembly sequence generation
    print(f"\n[2/5] Running Assembly Sequence Generation...")
    
    from agent.Assembly_sequence_generation import generate_assembly_sequence
    
    try:
        result = generate_assembly_sequence(
            assembly_name=assembly_name,
            assembly_dir=assembly_step_dir,
            exp_output_dir=output_dir,
            json_dir=output_dir,  # Use our output dir with copied JSONs
            image_keywords=None,  # Use defaults from settings
            json_keywords=None    # Use defaults from settings
        )
        
        if "error" in result:
            print(f"\nERROR: {result['error']}")
            return
        
        print(f"\n      > Assembly Sequence Generated: {result.get('assembly_sequence_path')}")
        
        # Print sequence summary
        sequence_data = result.get("sequence_data")
        if sequence_data:
            print(f"      > Assembly: {sequence_data.get('assembly_name')}")
            print(f"      > Base Part: {sequence_data.get('base_part', {}).get('part_id')}")
            print(f"      > Steps: {len(sequence_data.get('steps', []))}")
            print(f"      > Subassemblies: {len(sequence_data.get('subassemblies', []))}")
        
        # [3/5] Render assembly steps
        print(f"\n[3/5] Rendering assembly steps...")
        
        from agent.Assembly_sequence_validation import render_assembly_steps
        
        render_result = render_assembly_steps(
            assembly_name=assembly_name,
            experiment_name="debug",
            exp_output_dir=output_dir
        )
        
        if render_result.get("status") == "error":
            print(f"\n      ERROR: {render_result.get('message')}")
            print(f"      Skipping validation...")
        else:
            print(f"      > Renderings created: {render_result.get('renderings_count')}")
            print(f"      > Output dir: {render_result.get('output_dir')}")
            
            # [4/5] Validate assembly sequence
            print(f"\n[4/5] Validating assembly sequence...")
            
            from agent.Assembly_sequence_validation import validate_assembly_sequence
            
            validation_result = validate_assembly_sequence(
                assembly_name=assembly_name,
                experiment_name="debug",
                exp_output_dir=output_dir
            )
            
            if validation_result.get("status") == "error":
                print(f"\n      ERROR: {validation_result.get('message')}")
            else:
                print(f"      > Validation complete: {validation_result.get('validation_path')}")
                
                # Print validation summary
                validation_data = validation_result.get("validation_data")
                if validation_data:
                    step_validations = validation_data.get("step_validations", [])
                    print(f"      > Steps validated: {len(step_validations)}")
                    
                    # Count issues
                    issues = []
                    for sv in step_validations:
                        if sv.get("issues"):
                            issues.extend(sv["issues"])
                    
                    if issues:
                        print(f"      > Issues found: {len(issues)}")
                        print(f"\n      First 3 Issues:")
                        for issue in issues[:3]:
                            print(f"        - {issue}")
                    else:
                        print(f"      > [OK] No issues found!")
        
        # Print steps
        if sequence_data:
            steps = sequence_data.get('steps', [])
            if steps:
                print(f"\n      Assembly Steps Preview:")
                for i, step in enumerate(steps[:5], 1):  # Show first 5 steps
                    joining = step.get('joining_part')
                    if isinstance(joining, list):
                        joining_str = f"[{', '.join(joining)}]"
                    else:
                        joining_str = str(joining)
                    print(f"        {i}. {step.get('base_part')} + {joining_str}")
                if len(steps) > 5:
                    print(f"        ... and {len(steps) - 5} more steps")
        
        print(f"\n[5/5] Results Summary:")
        print(f"      > Output: {output_dir}")
        print(f"      > Assembly Sequence: {result.get('assembly_sequence_path')}")
        if render_result.get("status") != "error":
            print(f"      > Renderings: {render_result.get('output_dir')}")
        if 'validation_result' in locals() and validation_result.get("status") != "error":
            print(f"      > Validation: {validation_result.get('validation_path')}")
        
        print(f"\n{'='*80}")
        print(f"[OK] DEBUG TEST COMPLETE")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\nEXCEPTION: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_assembly_sequence_generation()
