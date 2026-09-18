# ============================================
# src/identification/part_identifier.py
# ============================================
from typing import Dict, List
from collections import defaultdict
import hashlib

from ..core.part import Part

class PartIdentifier:
    """Identifies duplicate parts based on geometric similarity"""
    
    def __init__(self, volume_tolerance: float = 0.01, area_tolerance: float = 0.01):
        """
        Args:
            volume_tolerance: Relative tolerance for volume comparison (1% default)
            area_tolerance: Relative tolerance for surface area comparison (1% default)
        """
        self.volume_tolerance = volume_tolerance
        self.area_tolerance = area_tolerance
    
    def compute_hash(self, part: Part) -> str:
        """
        Compute geometry hash for a part
        Uses volume and surface area rounded to reasonable precision
        """
        if not part.geometry_data:
            return None
        
        # Round to avoid floating point issues
        vol = round(part.geometry_data.volume, 2)
        area = round(part.geometry_data.surface_area, 2)
        
        hash_input = f"{vol}_{area}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def find_duplicates(self, parts: List[Part]) -> Dict[str, List[Part]]:
        """
        Group parts by geometric similarity
        Returns dict: {geometry_hash: [list of identical parts]}
        """
        groups = defaultdict(list)
        
        for part in parts:
            if part.geometry_data:
                geom_hash = self.compute_hash(part)
                part.geometry_hash = geom_hash
                groups[geom_hash].append(part)
        
        return dict(groups)
    
    def assign_part_ids(self, parts: List[Part], prefix: str = "part"):
        """
        Assign unique IDs to parts
        Identical parts get base_id with suffix: part_001, part_001_copy1, part_001_copy2
        """
        duplicate_groups = self.find_duplicates(parts)
        
        part_counter = 1
        for _geom_hash, identical_parts in duplicate_groups.items():
            # First part gets the base ID
            base_id = f"{prefix}_{part_counter:03d}"
            identical_parts[0].part_id = base_id
            identical_parts[0].quantity_in_assembly = len(identical_parts)
            
            # Subsequent identical parts get suffixed IDs
            for idx, part in enumerate(identical_parts[1:], start=1):
                part.part_id = f"{base_id}_copy{idx}"
                part.quantity_in_assembly = len(identical_parts)
            
            # Update all parts with references to their twins (use part_ids for stability)
            for part in identical_parts:
                part.identical_to = [p.part_id for p in identical_parts if p.part_id != part.part_id]
            
            part_counter += 1
    
    def are_parts_identical(self, part1: Part, part2: Part) -> bool:
        """Check if two parts are geometrically identical"""
        if not (part1.geometry_data and part2.geometry_data):
            return False
        
        vol1 = part1.geometry_data.volume
        vol2 = part2.geometry_data.volume
        area1 = part1.geometry_data.surface_area
        area2 = part2.geometry_data.surface_area
        
        # Check relative difference
        vol_diff = abs(vol1 - vol2) / max(vol1, vol2) if max(vol1, vol2) > 0 else 0
        area_diff = abs(area1 - area2) / max(area1, area2) if max(area1, area2) > 0 else 0
        
        return vol_diff <= self.volume_tolerance and area_diff <= self.area_tolerance
    
    # Add a placeholder reset method
    def reset(self):
        """
        Resets the state of the PartIdentifier.
        """
        print("PartIdentifier state reset.")