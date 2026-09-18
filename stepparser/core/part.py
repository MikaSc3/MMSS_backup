"""Core domain model for a single CAD part."""

from __future__ import annotations

import hashlib
import itertools
from pathlib import Path
from typing import List, Optional

from OCC.Core.TopoDS import TopoDS_Shape

from .data_classes import Color, Feature, GeometryData


class Part:
    _instance_counter = itertools.count(1)

    def __init__(self, shape: TopoDS_Shape, name: str | None = None):
        self.shape = shape
        self.name = name or "Unnamed_Part"

        # Stable per-run identifier (independent from duplicate detection)
        self.instance_id: int = next(Part._instance_counter)

        # Assigned later by PartIdentifier (e.g. part_001, part_001_copy1)
        self.part_id: Optional[str] = None

        self.color: Optional[Color] = None

        # Duplicate tracking
        self.geometry_hash: Optional[str] = None
        self.identical_to: List[str] = []
        self.quantity_in_assembly: int = 1

        # File paths
        self.output_folder: Optional[str] = None

        # Analysis results
        self.geometry_data: Optional[GeometryData] = None
        self.features: List[Feature] = []
        self.detailed_brep_analysis: Optional[dict] = None
        
        # Spatial touching analysis (assigned later by processor)
        self.part_is_touching: List[str] = []  # List of part_ids whose bboxes touch this part

    
    def compute_geometry_hash(self) -> Optional[str]:
        """Create hash based on volume and surface area for duplicate detection"""
        if self.geometry_data:
            hash_input = f"{self.geometry_data.volume:.6f}_{self.geometry_data.surface_area:.6f}"
            self.geometry_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        return self.geometry_hash

    def get_effective_part_id(self) -> str:
        """Return a usable ID even if PartIdentifier hasn't assigned one yet."""
        return self.part_id or f"inst_{self.instance_id:04d}"
    
    def to_metadata_dict(self) -> dict:
        """Convert part data to JSON-serializable dict with rounded values (reduced version)"""
        com_abs = self._compute_center_of_mass_absolute()

        metadata = {
            "part_id": self.get_effective_part_id(),
            "volume": round(self.geometry_data.volume, 3) if self.geometry_data else None,
            "bounding_box": {
                "x": round(abs(self.geometry_data.bounding_box.max_point[0] - self.geometry_data.bounding_box.min_point[0]), 3),
                "y": round(abs(self.geometry_data.bounding_box.max_point[1] - self.geometry_data.bounding_box.min_point[1]), 3),
                "z": round(abs(self.geometry_data.bounding_box.max_point[2] - self.geometry_data.bounding_box.min_point[2]), 3),
            } if self.geometry_data else None,
            "COM": {
                "absolute": [round(x, 3) for x in com_abs] if com_abs else None,
            },
            "color": list(self.color.to_tuple()) if self.color else None,
            "quantity_in_assembly": self.quantity_in_assembly,
            "identical_to": self.identical_to,
            "part_is_touching": self.part_is_touching,
        }
        
        return metadata

    def _compute_center_of_mass_absolute(self) -> Optional[tuple[float, float, float]]:
        """Compute center of mass in model coordinates.

        Uses OpenCascade volume properties when available.
        """
        try:
            from OCC.Core.GProp import GProp_GProps
            from OCC.Core.BRepGProp import brepgprop

            props = GProp_GProps()
            brepgprop.VolumeProperties(self.shape, props)
            com = props.CentreOfMass()
            return (float(com.X()), float(com.Y()), float(com.Z()))
        except Exception:
            return None

    def _compute_center_of_mass_relative_to_bbox(
        self,
        com_abs: Optional[tuple[float, float, float]],
    ) -> Optional[tuple[float, float, float]]:
        """Normalize COM into bounding box coordinates (0..1) per axis."""
        if not com_abs or not self.geometry_data:
            return None

        bbox = self.geometry_data.bounding_box
        min_x, min_y, min_z = bbox.min_point
        max_x, max_y, max_z = bbox.max_point

        dx = max_x - min_x
        dy = max_y - min_y
        dz = max_z - min_z

        def _norm(value: float, vmin: float, d: float) -> float:
            if d == 0:
                return 0.5
            return (value - vmin) / d

        return (
            _norm(com_abs[0], min_x, dx),
            _norm(com_abs[1], min_y, dy),
            _norm(com_abs[2], min_z, dz),
        )
    
    def _feature_to_dict(self, feature: Feature) -> dict:
        return {
            "type": feature.feature_type.value,
            "properties": feature.properties,
            "position": [round(x, 3) for x in feature.position],
            "orientation": [round(x, 3) for x in feature.orientation]
        }
    
    @staticmethod
    def compute_spatial_relations(parts: List['Part'], max_neighbors: int = 5, bbox_threshold_mm: float = 3.0):
        """
        Compute which parts are touching each other based on bounding box overlap/contact.
        
        Populates part.part_is_touching with list of part_ids whose bounding boxes
        are touching or overlapping (bbox_distance <= 0.0).
        
        Args:
            parts: List of all parts in the assembly
            max_neighbors: (Unused, kept for compatibility)
            bbox_threshold_mm: (Unused, kept for compatibility)
        """
        for part in parts:
            if not part.geometry_data or not part.geometry_data.bounding_box:
                continue
            
            bbox_self = part.geometry_data.bounding_box
            touching_parts = []
            
            for other_part in parts:
                # Skip self
                if other_part.get_effective_part_id() == part.get_effective_part_id():
                    continue
                
                if not other_part.geometry_data or not other_part.geometry_data.bounding_box:
                    continue
                
                bbox_other = other_part.geometry_data.bounding_box
                
                # Compute BBox distance (minimum distance between box surfaces)
                bbox_dist = Part._compute_bbox_distance(bbox_self, bbox_other)
                
                # Only include if bboxes are touching or overlapping
                if bbox_dist <= 0.0:
                    touching_parts.append(other_part.get_effective_part_id())
            
            part.part_is_touching = touching_parts
    
    @staticmethod
    def _compute_bbox_distance(bbox1, bbox2) -> float:
        """
        Compute minimum distance between two axis-aligned bounding boxes.
        Returns 0 if boxes overlap/touch, otherwise the gap distance.
        
        Args:
            bbox1, bbox2: BoundingBox objects with min_point and max_point
            
        Returns:
            Minimum distance in mm
        """
        # Extract coordinates
        min1_x, min1_y, min1_z = bbox1.min_point
        max1_x, max1_y, max1_z = bbox1.max_point
        min2_x, min2_y, min2_z = bbox2.min_point
        max2_x, max2_y, max2_z = bbox2.max_point
        
        # Compute distance per axis (0 if overlapping)
        dx = max(0, max(min1_x - max2_x, min2_x - max1_x))
        dy = max(0, max(min1_y - max2_y, min2_y - max1_y))
        dz = max(0, max(min1_z - max2_z, min2_z - max1_z))
        
        # Euclidean distance between closest points
        import math
        return math.sqrt(dx*dx + dy*dy + dz*dz)