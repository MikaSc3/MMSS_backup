"""
Debug script for FFA Assessment
Tests FFA assessment with existing assembly sequence data
"""

from pathlib import Path
from datetime import datetime
import json

def test_ffa_assessment():
    """Run FFA assessment on existing assembly sequence."""
    
    # Setup paths
    workspace_root = Path(__file__).parent
    assembly_name = "worm gear demonstrator"
    
    # Find most recent debug_ASG_* folder
    experiments_dir = workspace_root / "data" / "experiments"
    debug_folders = sorted([d for d in experiments_dir.glob("debug_ASG_*") if d.is_dir()], reverse=True)
    
    if not debug_folders:
        print("ERROR: No debug_ASG_* folders found!")
        return
    
    exp_dir = debug_folders[0]  # Most recent
    
    # Input paths
    sequence_json = exp_dir / "assembly_sequence.json"
    enriched_dir = exp_dir / "enriched_parts"
    rendered_steps = exp_dir / "sequence_renderings"
    
    # Output path
    output_dir = exp_dir / "ffa_assessment"
    
    print(f"\n{'='*80}")
    print(f"FFA ASSESSMENT - DEBUG TEST")
    print(f"{'='*80}\n")
    print(f"Assembly: {assembly_name}")
    print(f"Experiment: {exp_dir.name}")
    print(f"Sequence JSON: {sequence_json}")
    print(f"Enriched Parts: {enriched_dir}")
    print(f"Rendered Steps: {rendered_steps}")
    print(f"Output Dir: {output_dir}")
    
    # Find BOM_enriched.json (has assembly name prefix)
    bom_files = list(exp_dir.glob("*_BOM_enriched.json"))
    if not bom_files:
        print(f"ERROR: No BOM_enriched.json found in {exp_dir}")
        return
    
    bom_json = bom_files[0]  # Use first match
    print(f"BOM JSON: {bom_json}")
    print(f"\n{'='*80}\n")
    
    # Check if source files exist
    if not sequence_json.exists():
        print(f"ERROR: Sequence JSON not found: {sequence_json}")
        return
    
    if not rendered_steps.exists():
        print(f"ERROR: Rendered steps dir not found: {rendered_steps}")
        return
    
    # Count available data
    with open(bom_json, "r", encoding="utf-8") as f:
        bom_data = json.load(f)
    bom_parts = bom_data.get("parts", [])
    step_images = list(rendered_steps.glob("Step_*.png"))
    
    print(f"[Data Check]")
    print(f"  BOM parts: {len(bom_parts)} parts")
    print(f"  Step renderings: {len(step_images)} PNG files")
    
    # Preview BOM parts
    print(f"\n  Available parts (from BOM):")
    for part in sorted(bom_parts, key=lambda p: p.get("part_id", ""))[:10]:
        print(f"    - {part.get('part_id', 'unknown')}")
    if len(bom_parts) > 10:
        print(f"    ... and {len(bom_parts) - 10} more")
    
    # Load and preview sequence
    with open(sequence_json, "r", encoding="utf-8") as f:
        sequence_data = json.load(f)
    
    steps = sequence_data.get("steps", [])
    print(f"\n  Assembly sequence: {len(steps)} steps")
    for step in steps[:3]:  # Preview first 3 steps
        print(f"    Step {step['step_id']}: {step['step_description'][:60]}...")
    if len(steps) > 3:
        print(f"    ... and {len(steps) - 3} more steps")
    
    # Run FFA assessment
    print(f"\n{'='*80}")
    print(f"[Running FFA Assessment]")
    print(f"{'='*80}\n")
    
    from agent.FFA_assessment import assess_assembly_sequence_ffa
    
    try:
        result = assess_assembly_sequence_ffa(
            sequence_json_path=sequence_json,
            enriched_dir=enriched_dir,  # Kept for backward compatibility
            rendered_steps_dir=rendered_steps,
            output_dir=output_dir,
            prompt_id="ffa_assessment_full_v1",
            base_metadata_keys=[
                "part_id",
                "part_name_guess"
            ],
            joining_metadata_keys=[
                "part_id",
                "part_name_guess"
            ],
            image_downscale=0.2,
            step_img_keywords=["isometric", "top"],
            prior_step_img_keywords=["isometric", "top"],
            bom_json_path=bom_json,  # Use BOM for efficient loading
        )
        
        print(f"\n{'='*80}")
        print(f"RESULT SUMMARY")
        print(f"{'='*80}\n")
        
        status = result.get("status", "unknown")
        if status == "error":
            print(f"Status: ERROR")
            print(f"Error: {result.get('error')}")
        else:
            total_steps = result.get("total_steps", 0)
            assessed_steps = result.get("assessed_steps", 0)
            print(f"Status: SUCCESS")
            print(f"Total steps: {total_steps}")
            print(f"Assessed steps: {assessed_steps}")
            
            # Count successful assessments
            step_assessments = result.get("step_assessments", [])
            successful = sum(1 for s in step_assessments if "error" not in s)
            failed = sum(1 for s in step_assessments if "error" in s)
            
            print(f"  ✓ Successful: {successful}")
            if failed > 0:
                print(f"  ✗ Failed: {failed}")
            
            # Preview first assessment
            if step_assessments:
                print(f"\nFirst assessment preview:")
                first = step_assessments[0]
                print(f"  Step {first['step_id']}: {first['step_description'][:60]}...")
                print(f"  Base: {first['base_part_id']} | Joining: {first['joining_part_id']}")
                
                if first.get('assessment'):
                    assessment = first['assessment']
                    print(f"\n  Assessment categories:")
                    
                    # Separation
                    if 'separation' in assessment:
                        sep = assessment['separation']
                        print(f"    Separation: {sep.get('nature_of_provision', 'N/A')}")
                    
                    # Handling
                    if 'handling' in assessment:
                        hand = assessment['handling']
                        print(f"    Handling: rigidity={hand.get('part_rigidity', 'N/A')}, gripping={hand.get('gripping_areas', 'N/A')}")
                    
                    # Positioning
                    if 'positioning' in assessment:
                        pos = assessment['positioning']
                        print(f"    Positioning: accuracy={pos.get('accuracy_of_target_position', 'N/A')[:40]}...")
                    
                    # Joining
                    if 'joining' in assessment:
                        join = assessment['joining']
                        print(f"    Joining: feeding={join.get('feeding_of_joining_element', 'N/A')}")
            
            print(f"\n  Output saved to: {output_dir / 'ffa_assessment.json'}")
    
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"ERROR during FFA assessment")
        print(f"{'='*80}\n")
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n{'='*80}")
    print(f"FFA ASSESSMENT COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    test_ffa_assessment()
