"""
Debug script to verify paths and structure for FFA evaluation orchestrator
"""

from pathlib import Path

run_root = Path("data/experiments/run_2026-02-10_154526")
exp_name = "exp1_baseline"
exp_path = run_root / exp_name

print("=" * 70)
print("PATH VERIFICATION")
print("=" * 70)

# Check experiment path
print(f"\n1. Experiment Path:")
print(f"   {exp_path}")
print(f"   Exists: {exp_path.exists()}")

# Check assemblies
if exp_path.exists():
    assemblies = [d.name for d in exp_path.iterdir() if d.is_dir()]
    print(f"\n2. Found {len(assemblies)} assemblies:")
    for asm in sorted(assemblies):
        print(f"   - {asm}")
        
        # Check ffa_assessment_stripped.json
        stripped_file = exp_path / asm / "ffa_assessment" / "ffa_assessment_stripped.json"
        print(f"     Stripped: {stripped_file}")
        print(f"     Exists: {stripped_file.exists()}")

# Check ground truth
gt_root = Path("data/ground_truth")
print(f"\n3. Ground Truth Path:")
print(f"   {gt_root}")
print(f"   Exists: {gt_root.exists()}")

if gt_root.exists():
    gt_files = list(gt_root.glob("*_ffa_assessment_enum*.json"))
    gt_files = [f for f in gt_files if f.name != "ffa_enum_mapping.json"]
    print(f"   Found {len(gt_files)} ground truth files:")
    for gt in sorted(gt_files):
        print(f"   - {gt.name}")

# Check if assembly names match
print(f"\n4. Assembly Name Matching:")
assemblies = [d.name for d in exp_path.iterdir() if d.is_dir()]
gt_files = list(gt_root.glob("*_ffa_assessment_enum*.json"))
gt_files = [f for f in gt_files if f.name != "ffa_enum_mapping.json"]

for asm in sorted(assemblies):
    # Normalize assembly name
    normalized_asm = asm.replace(" ", "_")
    
    # Look for matching GT file
    matching_gt = [f for f in gt_files if normalized_asm in f.name]
    
    if matching_gt:
        print(f"   ✓ {asm} → {matching_gt[0].name}")
    else:
        print(f"   ✗ {asm} → NO MATCH (expected: {normalized_asm}_ffa_assessment_enum_gt.json)")
