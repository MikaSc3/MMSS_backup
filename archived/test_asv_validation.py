#!/usr/bin/env python
"""
Quick Test: Assembly Sequence Validation

Testet die validate_assembly_sequence() Funktion mit IPA_Cranfield.
"""

import sys
import json
from pathlib import Path

# Add workspace to path
workspace_root = Path(__file__).parent
sys.path.insert(0, str(workspace_root))

from agent.Assembly_sequence_validation import validate_assembly_sequence


def main():
    """Test assembly sequence validation."""
    
    print("\n" + "="*80)
    print("ASSEMBLY SEQUENCE VALIDATION - QUICK TEST")
    print("="*80)
    
    assembly_name = "worm gear demonstrator"
    
    # NEW: Handle experiment path with subdirectory structure (e.g., run_*/default/assembly/)
    # User provided: run_2026-01-29_170706\default\worm gear demonstrator\assembly_sequence_run1
    experiment_name = "run_2026-01-29_170706/default"  # Path to the folder containing the assembly
    
    # Settings - Load from default_settings.yaml and override for testing
    from agent.prompt_store import load_experiment_settings
    settings = load_experiment_settings()
    
    # Override specific settings for this test (use actual values from default_settings.yaml)
    # ASV_json_keywords: ["merged_bom"] - from default_settings.yaml line 97
    # ASV_parts_json_keys: ["part_id", "part_is_touching", "volume", "part_name_guess", "geometry_features", "material_info"] - from line 98
    # ASV_step_img_keywords: ["iso1_transp_0_3"] - from line 99
    # ASV_prior_step_img_keywords: ["iso1_transp_0_3"] - from line 100
    # ASV_finished_assy_keywords: ["iso1_transp_0_3"] - from line 101
    # image_downscale_factor: 0.5 - global setting
    # All settings are already loaded from default_settings.yaml, no need to override
    
    print(f"\nTest Configuration:")
    print(f"  Assembly: {assembly_name}")
    print(f"  Experiment: {experiment_name}")
    print(f"\nLoaded Settings from default_settings.yaml:")
    print(f"  ASV_json_keywords: {settings.get('ASV_json_keywords')}")
    print(f"  ASV_parts_json_keys: {settings.get('ASV_parts_json_keys')}")
    print(f"  ASV_step_img_keywords: {settings.get('ASV_step_img_keywords')}")
    print(f"  ASV_prior_step_img_keywords: {settings.get('ASV_prior_step_img_keywords')}")
    print(f"  ASV_finished_assy_keywords: {settings.get('ASV_finished_assy_keywords')}")
    print(f"  image_downscale_factor: {settings.get('image_downscale_factor')}")
    
    # Run validation
    print(f"\n[1/2] Running validation...")
    print("-"*80)
    
    try:
        result = validate_assembly_sequence(
            assembly_name=assembly_name,
            experiment_name=experiment_name,
            settings=settings
        )
        
        print("\n[2/2] Processing results...")
        print("-"*80)
        
        # Check result
        if result.get("status") == "error":
            print(f"\n[ERROR] {result.get('message')}")
            return False
        
        # Display summary
        print(f"\nValidation Summary:")
        print(f"  Overall Valid: {result.get('overall_valid')}")
        print(f"  Overall Confidence: {result.get('overall_confidence'):.1f}%")
        print(f"  Overall Risk: {result.get('overall_risk_level')}")
        
        validation_summary = result.get("validation_summary", {})
        print(f"\nDetailed Metrics:")
        print(f"  Total Steps: {validation_summary.get('total_steps')}")
        print(f"  Validated Steps: {validation_summary.get('validated_steps')}")
        print(f"  Valid Steps: {validation_summary.get('valid_steps')}")
        print(f"  Invalid Steps: {validation_summary.get('invalid_steps')}")
        print(f"  Errors: {validation_summary.get('errors')}")
        
        # List created files
        exp_dir = workspace_root / "data" / "experiments" / experiment_name 
        val_dir = exp_dir / "assembly_sequence_validation"
        
        if val_dir.exists():
            print(f"\nCreated Files in {val_dir.name}/:")
            for f in sorted(val_dir.glob("*.json")):
                size_kb = f.stat().st_size / 1024
                print(f"  - {f.name} ({size_kb:.1f} KB)")
        
        # Display first step validation details
        step_validations = result.get("step_validations", [])
        if step_validations:
            print(f"\nFirst Step Validation Details:")
            first = step_validations[0]
            print(f"  Step {first.get('step_number')}:")
            print(f"    Valid: {first.get('is_valid')}")
            print(f"    Confidence: {first.get('confidence')}%")
            print(f"    Risk: {first.get('risk_level')}")
            print(f"    Remarks: {first.get('remarks')[:100]}..." if len(first.get('remarks', '')) > 100 else f"    Remarks: {first.get('remarks')}")
            
            if first.get('geometric_issues'):
                print(f"    Geometric Issues:")
                for issue in first.get('geometric_issues'):
                    print(f"      - {issue}")
            
            if first.get('suggested_improvements'):
                print(f"    Suggested Improvements:")
                for imp in first.get('suggested_improvements'):
                    print(f"      - {imp}")
        
        print(f"\n" + "="*80)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*80)
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
