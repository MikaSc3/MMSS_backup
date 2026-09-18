#!/usr/bin/env python3
"""Test expand_subassemblies_in_sequence function"""

from agent.Assembly_sequence_validation import expand_subassemblies_in_sequence
import json

# Test data - simulates your worm gear assembly
test_sequence = {
    "assembly_name": "test_assembly",
    "steps": [
        {
            "step_number": 1,
            "base_part": "part_003",
            "joining_part": None,
            "joining_process": "place_on_table"
        },
        {
            "step_number": 2,
            "base_part": "part_003",
            "joining_part": "part_003_copy1",
            "subassembly": {
                "id": "SubAssy_1",
                "name": "Worm Gear with Bearings",
                "parts": ["part_002", "part_003", "part_003_copy1"]
            }
        },
        {
            "step_number": 3,
            "base_part": "part_001",
            "joining_part": ["part_003_copy2", "part_003_copy3"],
            "subassembly": {
                "id": "SubAssy_2",
                "name": "Second Worm Gear with Bearings",
                "parts": ["part_001", "part_003_copy2", "part_003_copy3"]
            }
        },
        {
            "step_number": 4,
            "base_part": "SubAssy_1",  # ← SUBASSEMBLY REFERENCE!
            "joining_part": ["SubAssy_2", "part_004"],  # ← SUBASSEMBLY REFERENCE!
            "joining_process": "align_and_lower"
        }
    ],
    "subassemblies": [
        {
            "id": "SubAssy_1",
            "name": "Worm Gear with Bearings",
            "parts": ["part_002", "part_003", "part_003_copy1"]
        },
        {
            "id": "SubAssy_2",
            "name": "Second Worm Gear with Bearings",
            "parts": ["part_001", "part_003_copy2", "part_003_copy3"]
        }
    ]
}

print("=" * 80)
print("Testing expand_subassemblies_in_sequence()")
print("=" * 80)

result = expand_subassemblies_in_sequence(test_sequence)

print("\nStep 4 (with SubAssy references):")
step4 = result["steps"][3]
print(f"  base_part: {step4['base_part']}")
print(f"  → _expanded_base_parts: {step4.get('_expanded_base_parts', [])}")
print(f"  joining_part: {step4['joining_part']}")
print(f"  → _expanded_joining_parts: {step4.get('_expanded_joining_parts', [])}")

print("\nExpected:")
print(f"  _expanded_base_parts: ['part_002', 'part_003', 'part_003_copy1']")
print(f"  _expanded_joining_parts: ['part_001', 'part_003_copy2', 'part_003_copy3', 'part_004']")

# Verify correctness
assert set(step4.get('_expanded_base_parts', [])) == {'part_002', 'part_003', 'part_003_copy1'}, \
    f"base_part expansion failed: {step4.get('_expanded_base_parts')}"

assert set(step4.get('_expanded_joining_parts', [])) == {'part_001', 'part_003_copy2', 'part_003_copy3', 'part_004'}, \
    f"joining_part expansion failed: {step4.get('_expanded_joining_parts')}"

print("\n✅ All assertions passed! Function works correctly.")
