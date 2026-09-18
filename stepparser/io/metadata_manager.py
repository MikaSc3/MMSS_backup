# ============================================
# src/io/metadata_manager.py
# ============================================
import json
import os
from pathlib import Path
from typing import Union
import pandas as pd

from ..core.assembly import Assembly
from ..core.part import Part


class MetadataManager:
    """Handles saving and loading metadata JSON files"""
    
    @staticmethod
    def save_part_metadata(part: Part, output_folder: str):
        """Save part metadata to JSON"""
        metadata = part.to_metadata_dict()
        # Keep the main stepparser metadata JSON slim; surface/BREP details can be large.
        surface_features = metadata.pop("detailed_brep_analysis", None)
        
        # Create output folder if needed
        os.makedirs(output_folder, exist_ok=True)
        
        # Use part_id for consistent naming (e.g., "part_001" instead of "Part_1")
        part_id = part.get_effective_part_id()
        output_path = os.path.join(output_folder, f"{part_id}_Data_stepparser.json")
        with open(output_path, 'w', encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Saved metadata: {output_path}")

        # Save surface features / detailed BREP analysis into a separate JSON file (if available)
        if surface_features is not None:
            surface_features_path = os.path.join(output_folder, f"{part_id}_surface_features.JSON")
            payload = {
                "part_id": part.get_effective_part_id(),
                "name": part.name,
                "surface_features": surface_features,
            }
            with open(surface_features_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            print(f"Saved surface features: {surface_features_path}")
    
    @staticmethod
    def save_assembly_metadata(assembly: Assembly, output_folder: str):
        """Save assembly metadata to JSON"""
        metadata = assembly.to_metadata_dict()
        
        # Create output folder if needed
        os.makedirs(output_folder, exist_ok=True)
        
        # Strip .STEP extension from assembly name for clean filenames
        clean_name = assembly.name.replace('.STEP', '').replace('.step', '')
        
        # Save to file
        output_path = os.path.join(output_folder, f"{clean_name}_Overview_Stepparser.json")
        with open(output_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Saved metadata: {output_path}")

    @staticmethod
    def save_parts_table(parts: list[Part], output_folder: str, filename: str) -> str:
        """Create a single table (CSV) from the metadata JSON of all parts.

        This guarantees the exported table contains the same keys/values as the
        per-part JSON files on disk.
        """
        os.makedirs(output_folder, exist_ok=True)

        rows = MetadataManager.collect_part_metadata_from_files(
            parts,
            exclude_keys={"detailed_brep_analysis"},
            deduplicate_identicals=True,
        )

        df = pd.json_normalize(rows, sep=".")

        # Put some commonly used columns first (if present)
        preferred = [
            "part_id",
            "name",
            "quantity_in_assembly",
            "volume",
            "surface_area",
            "geometry_hash",
            "output_folder",
        ]
        ordered_cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
        df = df[ordered_cols]

        output_path = os.path.join(output_folder, filename)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"Saved parts table: {output_path}")
        return output_path

    @staticmethod
    def save_parts_list_json(parts: list[Part], output_folder: str, filename: str) -> str:
        """Save a JSON list of all part metadata objects.

        Important: This is a pure list (no assembly header / no extra metadata).
        """
        os.makedirs(output_folder, exist_ok=True)
        rows = MetadataManager.collect_part_metadata_from_files(
            parts,
            exclude_keys={"detailed_brep_analysis"},
            deduplicate_identicals=True,
        )

        output_path = os.path.join(output_folder, filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        print(f"Saved parts list JSON: {output_path}")
        return output_path

    @staticmethod
    def collect_part_metadata_from_files(
        parts: list[Part],
        exclude_keys: set[str] | None = None,
        deduplicate_identicals: bool = False,
    ) -> list[dict]:
        """Load each part's metadata JSON from disk and return as list of dicts.

        If deduplicate_identicals is True, only one representative per duplicate group is returned.
        Duplicate groups are identified primarily via the shared base part_id (e.g. part_001 for
        part_001_copy1/part_001_copy2). The representative selection prefers the non-copy part_id.
        """

        def _base_part_id(row: dict) -> str | None:
            pid = row.get("part_id")
            if not isinstance(pid, str) or not pid.strip():
                return None
            return pid.split("_copy", 1)[0]

        def _part_name_sort_key(name: str) -> tuple[int, str]:
            if not isinstance(name, str):
                return (10**9, str(name))
            import re
            m = re.match(r"(?i)^part_(\d+)$", name.strip())
            if m:
                try:
                    return (int(m.group(1)), name.lower())
                except Exception:
                    return (10**9, name.lower())
            return (10**9, name.lower())

        def _is_copy_part_id(row: dict) -> bool:
            pid = row.get("part_id")
            return isinstance(pid, str) and "_copy" in pid

        rows: list[dict] = []
        rep_index_by_key: dict[str, int] = {}
        exclude_keys = exclude_keys or set()
        for part in parts:
            if not part.output_folder:
                raise ValueError(f"Part '{part.name}' has no output_folder set")

            # Use part_id for consistent naming (matches save_part_metadata)
            part_id = part.get_effective_part_id()
            metadata_path = os.path.join(part.output_folder, f"{part_id}_Data_stepparser.json")
            if not os.path.exists(metadata_path):
                raise FileNotFoundError(f"Part metadata not found: {metadata_path}")

            with open(metadata_path, "r", encoding="utf-8") as f:
                row = json.load(f)

            for key in exclude_keys:
                row.pop(key, None)

            if not deduplicate_identicals:
                rows.append(row)
                continue

            # Determine duplicate-group key
            key = _base_part_id(row) or row.get("geometry_hash") or row.get("name")
            key = str(key)

            if key not in rep_index_by_key:
                rep_index_by_key[key] = len(rows)
                rows.append(row)
                continue

            # Decide whether to replace existing representative.
            idx = rep_index_by_key[key]
            current = rows[idx]

            # Prefer non-copy part_id
            if _is_copy_part_id(current) and not _is_copy_part_id(row):
                rows[idx] = row
                continue
            if (not _is_copy_part_id(current)) and _is_copy_part_id(row):
                continue

            # Otherwise prefer the lower Part_N name if applicable
            cur_name = current.get("name")
            new_name = row.get("name")
            if _part_name_sort_key(str(new_name)) < _part_name_sort_key(str(cur_name)):
                rows[idx] = row

        return rows
    
    @staticmethod
    def load_metadata(file_path: str) -> dict:
        """Load metadata from JSON file"""
        with open(file_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def check_if_processed(assembly_name: str, base_output_folder: str) -> bool:
        """Check if assembly has already been processed"""
        assembly_folder = Path(base_output_folder) / assembly_name

        if not assembly_folder.exists():
            return False

        clean_name = assembly_name.replace(".STEP", "").replace(".step", "")

        # Current stepparser output convention:
        #   {base}/{assembly}/assembly_{assembly}/{assembly}_Overview_Stepparser.json
        #   {base}/{assembly}/assembly_{assembly}/{assembly}_BOM.csv|json
        current_dir = assembly_folder / f"assembly_{clean_name}"
        current_metadata = current_dir / f"{clean_name}_Overview_Stepparser.json"
        current_bom_csv = current_dir / f"{clean_name}_BOM.csv"
        current_bom_json = current_dir / f"{clean_name}_BOM.json"

        if current_metadata.exists() and (current_bom_csv.exists() or current_bom_json.exists()):
            return True

        # Legacy convention kept for older processed folders.
        legacy_dir = assembly_folder / assembly_name
        legacy_metadata = legacy_dir / f"{assembly_name}-Metadata_assembly_stepparser.json"
        legacy_bom_csv = legacy_dir / f"{assembly_name}-BOM_stepparser.csv"
        legacy_bom_json = legacy_dir / f"{assembly_name}-BOM_stepparser.json"

        return legacy_metadata.exists() and (legacy_bom_csv.exists() or legacy_bom_json.exists())
    
    @staticmethod
    def clear_cache():
        """
        Clears the cache for the MetadataManager.
        """
        print("MetadataManager cache cleared.")
