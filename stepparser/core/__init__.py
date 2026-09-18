
# ============================================
# src/core/__init__.py
# ============================================
from .data_classes import (
    BoundingBox,
    Color,
    GeometryData,
    Feature,
    FeatureType
)
from .part import Part
from .assembly import Assembly

__all__ = [
    'BoundingBox',
    'Color',
    'GeometryData',
    'Feature',
    'FeatureType',
    'Part',
    'Assembly'
]
