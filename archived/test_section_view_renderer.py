#!/usr/bin/env python3
"""
Test Script for Section View Renderer

Tests the new render_section_view() method on an existing assembly sequence.

Usage:
    python test_section_view_renderer.py
"""

import json
from pathlib import Path
from typing import List, Dict

def test_section_view_rendering():
    """Test section view rendering on existing assembly sequence."""
    
    # Setup paths
    base_dir = Path(__file__).parent
    experiment_dir = base_dir / "data" / "experiments" / "run_2026-02-23_081633" / "expX_most_info" / "IPA_Reducer_Case"
    run_dir = experiment_dir / "assembly_sequence_run1"
    
    print(f"\n{'='*80}")
    print(f"TESTING SECTION VIEW RENDERER")
    print(f"{'='*80}")
    print(f"Run directory: {run_dir}")
    
    # Verify paths exist
    sequence_file = run_dir / "assembly_sequence.json"
    if not sequence_file.exists():
        print(f"[ERROR] Assembly sequence not found: {sequence_file}")
        return False
    
    # Find STEP file
    step_file_patterns = [
        base_dir / "data" / "input" / "ALL" / "IPA_Reducer_Case.STEP",
        base_dir / "data" / "input" / "ALL" / "IPA_Reducer_Case.step",
        base_dir / "data" / "input" / "STEP" / "IPA_Reducer_Case.STEP",
    ]
    
    step_file = None
    for pattern in step_file_patterns:
        if pattern.exists():
            step_file = pattern
            break
    
    if not step_file:
        print(f"[ERROR] STEP file not found for IPA_Reducer_Case")
        return False
    
    print(f"✓ STEP file found: {step_file.name}")
    print(f"✓ Sequence file found: {sequence_file.name}")
    
    # Load sequence
    with open(sequence_file, 'r', encoding='utf-8') as f:
        sequence_data = json.load(f)
    
    steps = sequence_data.get('steps', [])
    print(f"✓ Loaded {len(steps)} assembly steps")
    
    # Import required modules
    print(f"\nImporting modules...")
    try:
        from stepparser.io.step_loader import StepLoader
        from stepparser.rendering.renderer import Renderer
        from stepparser.analysis.brep_analyzer import BRepAnalyzer
        from stepparser.identification.part_identifier import PartIdentifier
        from stepparser.rendering.color_generator import ColorGenerator
        from stepparser.core.data_classes import BoundingBox
        print(f"✓ All modules imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import modules: {e}")
        return False
    
    # Load assembly
    print(f"\nLoading assembly from STEP file...")
    loader = StepLoader()
    assembly = loader.load_step_file(str(step_file))
    
    if not assembly:
        print(f"[ERROR] Failed to load assembly")
        return False
    
    print(f"✓ Assembly loaded: {assembly.name}")
    all_parts = assembly.get_all_parts()
    print(f"✓ Total parts: {len(all_parts)}")
    
    # Analyze geometry
    print(f"\nAnalyzing geometry...")
    analyzer = BRepAnalyzer()
    part_identifier = PartIdentifier()
    color_generator = ColorGenerator()
    
    for part in all_parts:
        if not part.geometry_data:
            part.geometry_data = analyzer.analyze_shape(part.shape, part.name)
    
    # Assign IDs and colors
    part_identifier.assign_part_ids(all_parts, prefix="part")
    color_generator.assign_colors_to_parts(all_parts)
    print(f"✓ IDs and colors assigned")
    
    # Compute assembly bounding box
    if all_parts:
        all_mins = []
        all_maxs = []
        for part in all_parts:
            if part.geometry_data and part.geometry_data.bounding_box:
                bbox = part.geometry_data.bounding_box
                all_mins.append(bbox.min_point)
                all_maxs.append(bbox.max_point)
        
        if all_mins and all_maxs:
            min_x = min(p[0] for p in all_mins)
            min_y = min(p[1] for p in all_mins)
            min_z = min(p[2] for p in all_mins)
            max_x = max(p[0] for p in all_maxs)
            max_y = max(p[1] for p in all_maxs)
            max_z = max(p[2] for p in all_maxs)
            
            assembly.bounding_box = BoundingBox(
                min_point=(min_x, min_y, min_z),
                max_point=(max_x, max_y, max_z)
            )
            print(f"✓ Bounding box computed")
            print(f"  Dimensions: X={max_x-min_x:.1f}, Y={max_y-min_y:.1f}, Z={max_z-min_z:.1f}")
    
    # Initialize renderer
    print(f"\nInitializing renderer...")
    renderer = Renderer(output_resolution=(1920, 1080))
    print(f"✓ Renderer initialized")
    
    # Create output directory for test results
    output_dir = run_dir / "section_view_tests"
    output_dir.mkdir(exist_ok=True, parents=True)
    print(f"✓ Output directory: {output_dir}")
    
    # Test section views on all steps
    test_steps = steps
    
    print(f"\n{'='*80}")
    print(f"TESTING SECTION VIEWS")
    print(f"{'='*80}\n")
    
    # Expand subassemblies if needed
    from agent.Assembly_sequence_validation import expand_subassemblies_in_sequence
    sequence_data = expand_subassemblies_in_sequence(sequence_data)
    all_steps = sequence_data.get('steps', [])
    
    results = {
        "test_date": str(Path(__file__).stat().st_mtime),
        "assembly": assembly.name,
        "total_steps": len(steps),
        "tested_steps": len(test_steps),
        "results": [],
        "errors": []
    }
    
    for step in test_steps:
        step_id = step['step_id']
        belongs_to = step.get('belongs_to', 'Assembly (basic config)')
        
        print(f"--- Step {step_id} ({belongs_to}) ---")
        
        # Collect part IDs BEFORE this step (up to step N-1)
        part_ids_before = set()
        if belongs_to == "Assembly (basic config)":
            for s in all_steps:
                if s.get('belongs_to', 'Assembly (basic config)') == 'Assembly (basic config)' and s['step_id'] < step_id:
                    if '_expanded_base_parts' in s:
                        part_ids_before.update(s['_expanded_base_parts'])
                    if '_expanded_joining_parts' in s:
                        part_ids_before.update(s['_expanded_joining_parts'])
        else:
            for s in all_steps:
                if s.get('belongs_to') == belongs_to and s['step_id'] < step_id:
                    if '_expanded_base_parts' in s:
                        part_ids_before.update(s['_expanded_base_parts'])
                    if '_expanded_joining_parts' in s:
                        part_ids_before.update(s['_expanded_joining_parts'])
        
        # Collect part IDs AFTER this step (up to step N)
        part_ids_after = set()
        if belongs_to == "Assembly (basic config)":
            for s in all_steps:
                if s.get('belongs_to', 'Assembly (basic config)') == 'Assembly (basic config)' and s['step_id'] <= step_id:
                    if '_expanded_base_parts' in s:
                        part_ids_after.update(s['_expanded_base_parts'])
                    if '_expanded_joining_parts' in s:
                        part_ids_after.update(s['_expanded_joining_parts'])
        else:
            for s in all_steps:
                if s.get('belongs_to') == belongs_to and s['step_id'] <= step_id:
                    if '_expanded_base_parts' in s:
                        part_ids_after.update(s['_expanded_base_parts'])
                    if '_expanded_joining_parts' in s:
                        part_ids_after.update(s['_expanded_joining_parts'])
        
        part_ids_before = list(part_ids_before)
        part_ids_after = list(part_ids_after)
        
        print(f"Parts BEFORE: {part_ids_before}")
        print(f"Parts AFTER: {part_ids_after}")
        
        # Generate section views for all 3 planes, before and after
        plane_configs = [
            ("xy", "render_section_view"),
            ("xz", "render_section_view_xz"),
            ("yz", "render_section_view_yz")
        ]
        
        for plane_name, method_name in plane_configs:
            for state, state_part_ids in [("before", part_ids_before), ("after", part_ids_after)]:
                # Skip if no parts
                if not state_part_ids:
                    print(f"  - Skipping {plane_name.upper()} {state}: no parts")
                    continue
                
                # Use temporary filename, then rename with entropy
                temp_filename = f"step_{step_id:02d}_section_{plane_name}_{state}_temp.png"
                temp_path = output_dir / temp_filename
                
                try:
                    renderer_method = getattr(renderer, method_name)
                    # Use cutting plane from AFTER state for both BEFORE and AFTER
                    reference_part = part_ids_after[-1] if part_ids_after else state_part_ids[-1]
                    renderer_method(assembly, state_part_ids, str(temp_path), transparency=0.0, 
                                  reference_part_id=reference_part)
                    
                    # Calculate entropy of rendered image
                    image_entropy = renderer.calculate_image_entropy(str(temp_path))
                    
                    # Format entropy: 5.23 -> entropy_5_23
                    entropy_str = f"{image_entropy:.2f}".replace(".", "_")
                    
                    # Rename file with entropy in name
                    final_filename = f"step_{step_id:02d}_section_{plane_name}_{state}_entropy_{entropy_str}.png"
                    final_path = output_dir / final_filename
                    temp_path.rename(final_path)
                    
                    print(f"✓ Section view {plane_name.upper()} {state} rendered: {final_filename}")
                    results["results"].append({
                        "step_id": step_id,
                        "plane": plane_name,
                        "state": state,
                        "belongs_to": belongs_to,
                        "parts": state_part_ids,
                        "reference_part": reference_part,
                        "output_file": final_filename,
                        "entropy": image_entropy,
                        "status": "success"
                    })
                    
                except Exception as e:
                    error_msg = f"Failed to render section view {plane_name.upper()} {state} for step {step_id}: {str(e)}"
                    print(f"✗ {error_msg}")
                    import traceback
                    traceback.print_exc()
                    results["errors"].append({
                        "step_id": step_id,
                        "plane": plane_name,
                        "state": state,
                        "error": str(e)
                    })
        
        print()
    
    # Save results summary
    summary_path = output_dir / "test_results.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    print(f"{'='*80}")
    print(f"TEST COMPLETE")
    print(f"{'='*80}")
    print(f"Successful: {len(results['results'])}")
    print(f"Errors: {len(results['errors'])}")
    print(f"Output directory: {output_dir}")
    print(f"Test summary: {summary_path}")
    
    return len(results['errors']) == 0


if __name__ == "__main__":
    import sys
    success = test_section_view_rendering()
    sys.exit(0 if success else 1)
