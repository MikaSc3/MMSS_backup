#!/usr/bin/env python3
"""
Analyze entropy differences between BEFORE and AFTER section views.

Shows entropy change (after - before) for each step and section plane.
Positive values = more information visible after part added
Negative values = less information visible after part added
"""

import re
from pathlib import Path
from collections import defaultdict

def extract_entropy_from_filename(filename: str) -> dict:
    """Extract step_id, plane, state, and entropy from section view filename.
    
    Example: step_02_section_xy_before_entropy_5_23.png
    Returns: {'step': 2, 'plane': 'xy', 'state': 'before', 'entropy': 5.23}
    """
    # Pattern: step_XX_section_YY_STATE_entropy_N_NN.png
    pattern = r'step_(\d+)_section_(xy|xz|yz)_(before|after)_entropy_(\d+)_(\d+)'
    match = re.search(pattern, filename)
    
    if match:
        step_id = int(match.group(1))
        plane = match.group(2)
        state = match.group(3)
        entropy_int = int(match.group(4))
        entropy_dec = int(match.group(5))
        entropy = float(f"{entropy_int}.{entropy_dec}")
        
        return {
            'step': step_id,
            'plane': plane,
            'state': state,
            'entropy': entropy
        }
    return None

def main():
    """Main analysis function."""
    # Setup path
    results_dir = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\experiments\run_2026-02-23_081633\expX_most_info\IPA_Reducer_Case\assembly_sequence_run1\section_view_tests")
    
    if not results_dir.exists():
        print(f"[ERROR] Directory not found: {results_dir}")
        return
    
    print(f"\n{'='*80}")
    print(f"ANALYZING ENTROPY DIFFERENCES")
    print(f"{'='*80}\n")
    
    # Parse all section view files
    entropy_data = defaultdict(lambda: defaultdict(dict))  # {step: {plane: {state: entropy}}}
    
    for img_file in sorted(results_dir.glob("*.png")):
        filename = img_file.name
        data = extract_entropy_from_filename(filename)
        
        if data:
            step = data['step']
            plane = data['plane']
            state = data['state']
            entropy = data['entropy']
            
            entropy_data[step][plane][state] = entropy
    
    if not entropy_data:
        print("[WARNING] No section view images found matching pattern")
        return
    
    # Calculate and display differences
    for step_id in sorted(entropy_data.keys()):
        print(f"Step {step_id}")
        
        for plane in sorted(entropy_data[step_id].keys()):
            state_data = entropy_data[step_id][plane]
            
            before_entropy = state_data.get('before', None)
            after_entropy = state_data.get('after', None)
            
            if before_entropy is not None and after_entropy is not None:
                diff = after_entropy - before_entropy
                direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                print(f"  {plane.upper()}  before: {before_entropy:.2f}  after: {after_entropy:.2f}  diff: {diff:+.2f} {direction}")
            elif before_entropy is not None:
                print(f"  {plane.upper()}  before: {before_entropy:.2f}  after: N/A")
            elif after_entropy is not None:
                print(f"  {plane.upper()}  before: N/A  after: {after_entropy:.2f}")
        
        print()
    
    # Summary statistics
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    all_diffs = []
    for step_id in entropy_data.keys():
        for plane in entropy_data[step_id].keys():
            state_data = entropy_data[step_id][plane]
            if 'before' in state_data and 'after' in state_data:
                diff = state_data['after'] - state_data['before']
                all_diffs.append((step_id, plane, diff))
    
    if all_diffs:
        avg_diff = sum(d[2] for d in all_diffs) / len(all_diffs)
        max_increase = max(all_diffs, key=lambda x: x[2])
        max_decrease = min(all_diffs, key=lambda x: x[2])
        
        print(f"Total steps analyzed: {len(entropy_data)}")
        print(f"Total comparisons: {len(all_diffs)}")
        print(f"Average entropy change: {avg_diff:+.2f}")
        print(f"Max increase: Step {max_increase[0]} {max_increase[1].upper()}: {max_increase[2]:+.2f}")
        print(f"Max decrease: Step {max_decrease[0]} {max_decrease[1].upper()}: {max_decrease[2]:+.2f}")
        print(f"\nInterpretation:")
        print(f"  Positive diff = More visual information after part added")
        print(f"  Negative diff = Less visual information after part added")
    else:
        print("[WARNING] No complete before/after pairs found")

if __name__ == "__main__":
    main()
