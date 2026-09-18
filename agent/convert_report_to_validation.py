"""
Convert FFA report JSON to validation format.
Transforms all string arrays into validation objects with is_false field.

Usage:
    python convert_report_to_validation.py <input_json> <output_json>
    
Example:
    python convert_report_to_validation.py ffa_report.json ffa_report_validation.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def convert_statements_to_validation(items):
    """Convert array of strings to array of validation objects."""
    if not isinstance(items, list):
        return items
    
    result = []
    for item in items:
        if isinstance(item, str):
            result.append({
                "statement": item,
                "is_false": None
            })
        else:
            # Already a dict (shouldn't happen in fresh reports)
            result.append(item)
    
    return result


def process_container(obj):
    """Recursively process all containers (dicts, lists with statements)."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in ['drawbacks', 'improvements', 'separation', 'handling', 
                      'positioning', 'joining', 'risks', 'step_description',
                      'geometric_characteristics', 'material', 'nature_of_provision_guess',
                      'gripping_analysis', 'handling_implications', 
                      'assembly_description', 'primary_function']:
                # These should be converted from strings to validation objects
                result[key] = convert_statements_to_validation(value)
            elif isinstance(value, (dict, list)):
                result[key] = process_container(value)
            else:
                result[key] = value
        return result
    
    elif isinstance(obj, list):
        return [process_container(item) for item in obj]
    
    else:
        return obj


def convert_report(input_path, output_path):
    """Main conversion function."""
    print(f"Reading {input_path}...")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    print("Converting to validation format...")
    validation_report = process_container(report)
    
    print(f"Writing {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(validation_report, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Conversion complete!")
    print(f"  Mark statements as false by changing 'is_false': null to 'is_false': \"x\" (or any value)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_validation.json')
    
    try:
        convert_report(input_file, output_file)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
