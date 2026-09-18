"""
merge_copy_part_data: Merge enriched part data with instance-specific Stepparser metadata.

CRITICAL for Phase 4.2: Handles duplicate parts by preserving instance-specific
position/orientation data for each copy (e.g., Part001, Part001-copy1).

Process:
1. Read ALL Stepparser metadata from data/processed/stepparser/{assembly}/
2. For each Part folder (including copies):
   - Load Part_XXX-Metadata_stepparser.json (has unique position/orientation)
   - Find corresponding enriched JSON (or copy from base part if not exists)
   - MERGE: Append Stepparser fields to enriched data
   - Save as Part_XXX-enriched-merged.json

Input:
  - enriched_parts/Part_1-Metadata_enriched.json (LLM enrichment, no position)
  - data/processed/stepparser/{assembly}/Part_4/Part_4-Metadata_stepparser.json (position x,y,z)

Output:
  - enriched_parts/Part_1-enriched-merged.json (LLM + position)
  - enriched_parts/Part_4-enriched-merged.json (LLM copied from Part_1 + Part_4 position)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


def merge_copy_part_data(
    assembly_name: str,
    experiment_output_dir: Path,
    stepparser_root: Path = None,
) -> Dict[str, Any]:
    """
    Merge enriched part data with instance-specific Stepparser metadata.
    
    Args:
        assembly_name: Name of the assembly (e.g., "worm gear demonstrator")
        experiment_output_dir: Path to experiment output (e.g., run_XXX/exp1_baseline/{assembly}/)
        stepparser_root: Root path to stepparser data (default: data/processed/stepparser)
    
    Returns:
        Dictionary with:
            - status: "success" or "error"
            - merged_count: Number of merged files created
            - output_dir: Path to enriched_parts/ with -merged.json files
            - details: List of merged part_ids
    """
    # Default stepparser root
    if stepparser_root is None:
        stepparser_root = Path("data/processed/stepparser")
    
    # Paths
    enriched_parts_dir = experiment_output_dir / "enriched_parts"
    stepparser_assembly_dir = stepparser_root / assembly_name
    
    # Validate directories
    if not enriched_parts_dir.exists():
        # Create enriched_parts directory if it doesn't exist
        # (it may not exist if run_monoparts was skipped or had errors)
        enriched_parts_dir.mkdir(parents=True, exist_ok=True)
    
    if not stepparser_assembly_dir.exists():
        return {
            "status": "error",
            "error": f"Stepparser assembly directory not found: {stepparser_assembly_dir}"
        }
    
    # Find all Part folders in Stepparser (part_001, part_001_copy1, etc.)
    # New convention: "part_XXX" folders (lowercase)
    # Legacy: "Part_X" folders
    part_folders = [d for d in stepparser_assembly_dir.iterdir() if d.is_dir() and (d.name.startswith("Part_") or d.name.startswith("part_"))]
    
    if not part_folders:
        return {
            "status": "error",
            "error": f"No Part_* folders found in {stepparser_assembly_dir}"
        }
    
    # Track merging results
    merged_parts = []
    errors = []
    
    # Process each Part folder
    for part_folder in sorted(part_folders):
        part_folder_name = part_folder.name  # e.g., "part_001", "part_003_copy1"
        
        # Load Stepparser metadata (search for matching file)
        # Try new convention first: {folder_name}_Data_stepparser.json
        stepparser_metadata_path = None
        for candidate in [
            part_folder / f"{part_folder_name}_Data_stepparser.json",
            part_folder / f"{part_folder_name}-Metadata_stepparser.json",
        ]:
            if candidate.exists():
                stepparser_metadata_path = candidate
                break
        
        if not stepparser_metadata_path:
            errors.append(f"Missing stepparser metadata for {part_folder_name}")
            continue
        
        try:
            with open(stepparser_metadata_path, 'r', encoding='utf-8') as f:
                stepparser_data = json.load(f)
        except Exception as e:
            errors.append(f"Failed to load stepparser metadata for {part_folder_name}: {e}")
            continue
        
        # Get part_id from Stepparser (e.g., "part_001", "part_003_copy1")
        part_id = stepparser_data.get("part_id", "unknown")
        
        # Find corresponding enriched JSON
        # Strategy: Look for {part_id}_Data_enriched.json (matches part_id, not folder name)
        # If this is a copy (e.g., part_003_copy1), fallback to base part (part_003)
        enriched_json_path = enriched_parts_dir / f"{part_id}_Data_enriched.json"
        
        enriched_data = None
        
        if enriched_json_path.exists():
            # Direct match found
            try:
                with open(enriched_json_path, 'r', encoding='utf-8') as f:
                    enriched_data = json.load(f)
            except Exception as e:
                errors.append(f"Failed to load enriched data for {part_id}: {e}")
                continue
        
        else:
            # This is a copy - find base part
            # part_id = "part_003_copy1" → base_part_id = "part_003"
            if "_copy" in part_id:
                base_part_id = part_id.split("_copy")[0]  # "part_003"
                
                # Look for base enriched file directly (naming matches part_id)
                base_enriched_path = enriched_parts_dir / f"{base_part_id}_Data_enriched.json"
                
                if base_enriched_path.exists():
                    try:
                        with open(base_enriched_path, 'r', encoding='utf-8') as f:
                            enriched_data = json.load(f)
                    except Exception as e:
                        errors.append(f"Failed to load base enriched data for {part_id} (base: {base_part_id}): {e}")
                        continue
                else:
                    errors.append(f"Base enriched JSON not found for {part_id} (expected: {base_enriched_path})")
                    continue
            else:
                errors.append(f"Enriched JSON not found for {part_id} and part_id does not indicate copy")
                continue
        
        # MERGE: Combine enriched_data with Stepparser metadata
        # Strategy: Flatten enriched structure and merge with stepparser fields
        merged_data = {}
        
        # FLATTEN: Extract enriched fields from nested structure
        # Flatten enriched data structure (handles old nested format)
        flattened_enriched = {}
        if isinstance(enriched_data, dict):
            if "metadata_monopart_enriched" in enriched_data:
                # Old nested structure: extract analysis and top-level fields
                analysis = enriched_data.get("metadata_monopart_enriched", {}).get("analysis", {})
                flattened_enriched.update(analysis)
                for key, value in enriched_data.items():
                    if key != "metadata_monopart_enriched":
                        flattened_enriched[key] = value
            else:
                # Already flat
                flattened_enriched = enriched_data.copy()
        
        # BUILD in Option 2 order: ID → Name → Description → Quantity → Relations → Geometry → Analysis → Schema
        # Extract key fields
        part_name_guess = flattened_enriched.get("part_name_guess")
        part_identification = flattened_enriched.get("part_identification")
        monopart_analysis = flattened_enriched.get("monopart_analysis")
        schema_info = flattened_enriched.get("_schema_info")
        part_is_touching = flattened_enriched.get("part_is_touching")
        
        # Clear merged_data and rebuild in desired order
        merged_data = {}
        
        # 1. Identification (part_id first)
        merged_data["part_id"] = part_id
        
        # 2. Naming & Description
        if part_name_guess:
            merged_data["part_name_guess"] = part_name_guess
        if part_identification:
            merged_data["part_identification"] = part_identification
        
        # 3. Assembly Context (quantity, relationships)
        merged_data["quantity_in_assembly"] = stepparser_data.get("quantity_in_assembly", 1)
        merged_data["identical_to"] = stepparser_data.get("identical_to", [])
        
        # 4. Touching/Mating (spatial relationships)
        if part_is_touching:
            merged_data["part_is_touching"] = part_is_touching
        merged_data["potential_mating_parts"] = stepparser_data.get("potential_mating_parts", [])
        
        # 5. Geometry (shape & spatial properties)
        merged_data["volume"] = stepparser_data.get("volume")
        merged_data["bounding_box"] = stepparser_data.get("bounding_box")
        merged_data["COM"] = stepparser_data.get("COM")
        merged_data["color"] = stepparser_data.get("color")
        merged_data["directory"] = stepparser_data.get("directory")
        
        # 6. Analysis (monopart enrichment)
        if monopart_analysis:
            merged_data["monopart_analysis"] = monopart_analysis
        
        # 7. Metadata
        if schema_info:
            merged_data["_schema_info"] = schema_info
        
        # 8. Any remaining enriched fields not explicitly handled
        handled_keys = {"part_name_guess", "part_identification", "monopart_analysis", "_schema_info", "part_is_touching"}
        for key, value in flattened_enriched.items():
            if key not in handled_keys and key not in merged_data:
                merged_data[key] = value
        
        # Optional: Add detailed BREP analysis if available
        if "detailed_brep_analysis" in stepparser_data:
            merged_data["detailed_brep_analysis"] = stepparser_data["detailed_brep_analysis"]
        
        # Write merged JSON (named by part_id for consistency)
        output_path = enriched_parts_dir / f"{part_id}_Data_enriched_merged.json"
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, indent=2, ensure_ascii=False)
            merged_parts.append({
                "part_folder": part_folder_name,
                "part_id": part_id,
                "output_file": output_path.name
            })
        except Exception as e:
            errors.append(f"Failed to write merged JSON for {part_folder_name} ({part_id}): {e}")
            continue
    
    # Result summary
    return {
        "status": "success" if merged_parts else "error",
        "merged_count": len(merged_parts),
        "output_dir": str(enriched_parts_dir),
        "details": merged_parts,
        "errors": errors if errors else None
    }
