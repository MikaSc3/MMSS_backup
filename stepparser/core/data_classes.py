from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

@dataclass
class BoundingBox:
    min_point: Tuple[float, float, float]
    max_point: Tuple[float, float, float]
    
    def get_center(self) -> Tuple[float, float, float]:
        return tuple((a + b) / 2 for a, b in zip(self.min_point, self.max_point))
    
    def get_dimensions(self) -> Tuple[float, float, float]:
        return tuple(b - a for a, b in zip(self.min_point, self.max_point))
    
    def get_diagonal(self) -> float:
        dims = self.get_dimensions()
        return (dims[0]**2 + dims[1]**2 + dims[2]**2)**0.5

@dataclass
class Color:
    r: int  # 0-255
    g: int
    b: int
    
    def to_tuple(self) -> Tuple[int, int, int]:
        return (self.r, self.g, self.b)
    
    def to_normalized(self) -> Tuple[float, float, float]:
        return (self.r/255, self.g/255, self.b/255)

@dataclass
class GeometryData:
    volume: float
    surface_area: float
    bounding_box: BoundingBox
    face_count: int
    edge_count: int
    vertex_count: int
    cylinder_surfaces: int
    plane_surfaces: int
    sphere_surfaces: int
    other_surfaces: int

class FeatureType(Enum):
    HOLE_THROUGH = "hole_through"
    HOLE_BLIND = "hole_blind"
    POCKET = "pocket"
    CHAMFER = "chamfer"
    FILLET = "fillet"

@dataclass
class Feature:
    feature_type: FeatureType
    properties: dict  # Flexible for different feature types
    position: Tuple[float, float, float]
    orientation: Tuple[float, float, float]