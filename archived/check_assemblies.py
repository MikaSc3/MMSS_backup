"""
Debug script to identify which assemblies are missing stripped FFA files
"""

from pathlib import Path

run_root = Path("data/experiments/run_2026-02-10_154526")
exp_path = run_root / "exp1_baseline"

print("=" * 70)
print("ASSEMBLY STATUS CHECK")
print("=" * 70)

# Find all assembly folders
assemblies = sorted([d.name for d in exp_path.iterdir() if d.is_dir()])
print(f"\nFound {len(assemblies)} assembly folders:")
for asm in assemblies:
    print(f"  - {asm}")

# Check for stripped FFA files
print(f"\n\nStripped FFA File Status:")
print("-" * 70)

found = 0
missing = 0

for asm in assemblies:
    stripped_file = exp_path / asm / "ffa_assessment" / "ffa_assessment_stripped.json"
    exists = stripped_file.exists()
    
    status = "✓" if exists else "✗"
    print(f"{status} {asm}")
    
    if exists:
        found += 1
    else:
        missing += 1
        # Show what IS in the ffa_assessment folder
        ffa_folder = exp_path / asm / "ffa_assessment"
        if ffa_folder.exists():
            files = list(ffa_folder.iterdir())
            print(f"    Files in ffa_assessment/: {', '.join([f.name for f in files])}")

print(f"\n\nSummary:")
print(f"  Found (with stripped JSON): {found}")
print(f"  Missing (without stripped JSON): {missing}")
