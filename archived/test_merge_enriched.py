"""Test merge_copy_part_data with worm gear demonstrator"""

from pathlib import Path
from agent.merge_enriched import merge_copy_part_data

# Paths
assembly_name = "worm gear demonstrator"
exp_output_dir = Path("data/experiments/run_2026-01-20_105536/exp1_baseline") / assembly_name
stepparser_root = Path("data/processed/stepparser")

print(f"Testing merge_copy_part_data...")
print(f"  Assembly: {assembly_name}")
print(f"  Output dir: {exp_output_dir}")
print(f"  Stepparser root: {stepparser_root}")
print()

# Run merge
result = merge_copy_part_data(
    assembly_name=assembly_name,
    experiment_output_dir=exp_output_dir,
    stepparser_root=stepparser_root
)

print(f"Result:")
print(f"  Status: {result['status']}")
print(f"  Merged count: {result.get('merged_count', 0)}")
print(f"  Output dir: {result.get('output_dir', 'N/A')}")
print()

if result.get('details'):
    print(f"Merged parts:")
    for detail in result['details']:
        print(f"  - {detail['part_name']} ({detail['part_id']}) → {detail['output_file']}")
print()

if result.get('errors'):
    print(f"Errors ({len(result['errors'])}):")
    for error in result['errors']:
        print(f"  - {error}")
