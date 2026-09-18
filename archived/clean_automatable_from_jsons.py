"""
Utility script to remove "automatable" fields from all JSON files in a directory.
Recursively processes all JSON files and removes "automatable" keys from nested structures.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def remove_automatable_recursive(obj: Any) -> Any:
    """
    Recursively remove "automatable" keys from a nested data structure.
    
    Args:
        obj: Any JSON-serializable object (dict, list, str, int, etc.)
    
    Returns:
        The modified object with all "automatable" keys removed
    """
    if isinstance(obj, dict):
        # Remove "automatable" key and recurse on remaining values
        return {
            key: remove_automatable_recursive(value)
            for key, value in obj.items()
            if key != "automatable"
        }
    elif isinstance(obj, list):
        # Recurse on all list items
        return [remove_automatable_recursive(item) for item in obj]
    else:
        # Return primitive types as-is
        return obj


def clean_automatable_from_path(directory_path: str, dry_run: bool = False) -> None:
    """
    Find all JSON files in a directory and remove "automatable" fields.
    
    Args:
        directory_path: Path to directory containing JSON files
        dry_run: If True, only print what would be removed (don't modify files)
    
    Example:
        >>> clean_automatable_from_path("c:\\Users\\KAB-MS\\VSCode\\apa_from_cad\\data\\evaluation")
        >>> clean_automatable_from_path("path/to/jsons", dry_run=True)  # Preview changes
    """
    directory = Path(directory_path)
    
    if not directory.exists():
        logger.error(f"Directory not found: {directory}")
        return
    
    # Find all JSON files recursively
    json_files = list(directory.rglob("*.json"))
    
    if not json_files:
        logger.info(f"No JSON files found in {directory}")
        return
    
    logger.info(f"Found {len(json_files)} JSON file(s) in {directory}")
    
    for json_file in json_files:
        try:
            # Load JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if "automatable" exists in data
            original_str = json.dumps(data)
            
            # Remove automatable
            cleaned_data = remove_automatable_recursive(data)
            
            cleaned_str = json.dumps(cleaned_data)
            
            # Check if anything changed
            if original_str == cleaned_str:
                logger.info(f"✓ No changes needed: {json_file.name}")
                continue
            
            if dry_run:
                logger.info(f"[DRY RUN] Would clean: {json_file.name}")
                # Show what would be removed
                changes = find_removed_keys(data, cleaned_data)
                if changes:
                    logger.info(f"  Removed {changes} 'automatable' field(s)")
            else:
                # Write back to file
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_data, f, indent=2)
                logger.info(f"✓ Cleaned: {json_file.name}")
        
        except json.JSONDecodeError as e:
            logger.error(f"✗ Invalid JSON in {json_file.name}: {e}")
        except Exception as e:
            logger.error(f"✗ Error processing {json_file.name}: {e}")


def find_removed_keys(original: Any, cleaned: Any) -> int:
    """Count how many 'automatable' keys were removed."""
    count = 0
    
    def count_automatable(obj):
        nonlocal count
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "automatable":
                    count += 1
                else:
                    count_automatable(value)
        elif isinstance(obj, list):
            for item in obj:
                count_automatable(item)
    
    count_automatable(original)
    return count


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    # Example usage
    directory = r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\ground_truth\ffa_ground_truth_evaluierungsdaten"
    
    print("=" * 70)
    print("CLEANING AUTOMATABLE FIELDS FROM JSON FILES")
    print("=" * 70)
    print(f"\nDirectory: {directory}\n")
    
    # First, do a dry run to see what would be changed
    print("DRY RUN (preview):")
    print("-" * 70)
    clean_automatable_from_path(directory, dry_run=True)
    
    # Then ask user to confirm
    print("\n" + "=" * 70)
    response = input("\nProceed with actual cleaning? (yes/no): ").strip().lower()
    
    if response in ['yes', 'y']:
        print("\nApplying changes...")
        print("-" * 70)
        clean_automatable_from_path(directory, dry_run=False)
        print("\n✓ Done!")
    else:
        print("\nCancelled.")
