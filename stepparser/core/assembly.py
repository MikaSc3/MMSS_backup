# ============================================
# src/core/assembly.py
# ============================================
from pathlib import Path
from typing import Optional, List, Union
from OCC.Core.TopoDS import TopoDS_Shape

from .data_classes import BoundingBox
from .part import Part


class Assembly:
    def __init__(self, shape: TopoDS_Shape, name: str = None):
        self.shape = shape
        self.name = name or "Unnamed_Assembly"
        self.assembly_id: Optional[str] = None
        
        # Hierarchy
        self.children: List[Union['Assembly', Part]] = []
        self.parent: Optional['Assembly'] = None
        self.depth: int = 0
        
        # Analysis results
        self.bounding_box: Optional[BoundingBox] = None
        self.total_volume: float = 0.0
        
        # File paths
        self.output_folder: Optional[str] = None
    
    def add_child(self, child: Union['Assembly', Part]):
        """Add subassembly or part"""
        self.children.append(child)
        if isinstance(child, Assembly):
            child.parent = self
            child.depth = self.depth + 1
    
    def get_all_parts(self) -> List[Part]:
        """Recursively collect all parts"""
        parts = []
        for child in self.children:
            if isinstance(child, Part):
                parts.append(child)
            elif isinstance(child, Assembly):
                parts.extend(child.get_all_parts())
        return parts
    
    def get_all_assemblies(self) -> List['Assembly']:
        """Recursively collect all subassemblies"""
        assemblies = [self]
        for child in self.children:
            if isinstance(child, Assembly):
                assemblies.extend(child.get_all_assemblies())
        return assemblies
    
    def get_unique_parts(self) -> List[Part]:
        """Get parts with unique geometry hashes"""
        all_parts = self.get_all_parts()
        unique = {}
        for part in all_parts:
            if part.geometry_hash not in unique:
                unique[part.geometry_hash] = part
        return list(unique.values())
    
    def to_metadata_dict(self) -> dict:
        """Convert assembly data to JSON-serializable dict"""
        bbox_abs = None
        if self.bounding_box:
            bbox_abs = {
                "x": round(abs(self.bounding_box.max_point[0] - self.bounding_box.min_point[0]), 3),
                "y": round(abs(self.bounding_box.max_point[1] - self.bounding_box.min_point[1]), 3),
                "z": round(abs(self.bounding_box.max_point[2] - self.bounding_box.min_point[2]), 3),
            }

        com_abs = self._compute_center_of_mass_absolute()
        com_rel_centered = self._compute_center_of_mass_relative_bbox_centered(com_abs)

        return {
            "assembly_id": self.assembly_id,
            "depth": self.depth,
            "total_parts": len(self.get_all_parts()),
            "unique_parts": len(self.get_unique_parts()),
            "direct_children": len(self.children),
            "subassemblies": [c.assembly_id for c in self.children if isinstance(c, Assembly)],
            "parts": [c.get_effective_part_id() for c in self.children if isinstance(c, Part)],
            "bounding_box": bbox_abs if self.bounding_box else None,
            "COM": {
                "absolute": [round(x, 3) for x in com_abs] if com_abs else None,
                "relative_bbox_centered": [round(x, 4) for x in com_rel_centered] if com_rel_centered else None,
            },
            "total_volume": round(self.total_volume, 3),
        }

    def _compute_center_of_mass_absolute(self) -> Optional[tuple[float, float, float]]:
        """Compute center of mass in model coordinates for the assembly shape."""
        try:
            from OCC.Core.GProp import GProp_GProps
            from OCC.Core.BRepGProp import brepgprop

            props = GProp_GProps()
            brepgprop.VolumeProperties(self.shape, props)
            com = props.CentreOfMass()
            return (float(com.X()), float(com.Y()), float(com.Z()))
        except Exception:
            return None

    def _compute_center_of_mass_relative_bbox_centered(
        self,
        com_abs: Optional[tuple[float, float, float]],
    ) -> Optional[tuple[float, float, float]]:
        """Normalize COM to bounding box center with scale (range approx [-0.5..0.5])."""
        if not com_abs or not self.bounding_box:
            return None

        min_x, min_y, min_z = self.bounding_box.min_point
        max_x, max_y, max_z = self.bounding_box.max_point

        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        cz = (min_z + max_z) / 2

        dx = max_x - min_x
        dy = max_y - min_y
        dz = max_z - min_z

        def _norm_centered(value: float, center: float, d: float) -> float:
            if d == 0:
                return 0.0
            return (value - center) / d

        return (
            _norm_centered(com_abs[0], cx, dx),
            _norm_centered(com_abs[1], cy, dy),
            _norm_centered(com_abs[2], cz, dz),
        )