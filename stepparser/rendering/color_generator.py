# ============================================
# src/rendering/color_generator.py
# ============================================
import colorsys
import hashlib
import random
from typing import Dict, List

from ..core.data_classes import Color
from ..core.part import Part


class ColorGenerator:
    """
    Deterministic color generator with size-based saturation:

    - Small parts   → high saturation
    - Medium parts  → medium saturation
    - Large parts   → low saturation

    - Identical parts → identical colors
    - Different parts → different hues with minimum hue distance
    """

    MIN_HUE_DISTANCE = 30  # degrees
    VALUE = 0.85           # constant brightness for all parts

    def __init__(self):
        self.color_cache: Dict[str, Color] = {}

    def reset(self) -> None:
        self.color_cache.clear()

    # ------------------------------------------------------------------

    def assign_colors_to_parts(self, parts: List[Part]):
        """Main entry point"""

        geom_parts = [p for p in parts if p.geometry_data]
        if not geom_parts:
            return

        # Group identical parts
        unique_parts: Dict[str, Part] = {}
        for p in geom_parts:
            unique_parts.setdefault(p.geometry_hash, p)

        unique_parts = list(unique_parts.values())

        # Sort by volume (small → large)
        unique_parts.sort(key=lambda p: p.geometry_data.volume)

        volumes = [p.geometry_data.volume for p in unique_parts]
        min_v, max_v = min(volumes), max(volumes)

        # Pre-generate hue slots
        hues = self._generate_hue_slots(
            count=len(unique_parts),
            min_distance=self.MIN_HUE_DISTANCE
        )

        random.seed(42) 
        random.shuffle(hues)

        # Assign colors to unique parts
        for idx, part in enumerate(unique_parts):

            volume_norm = self._normalize(
                part.geometry_data.volume,
                min_v,
                max_v
            )

            saturation = self._saturation_from_volume(volume_norm)

            color = self._hsv_color(
                hue=hues[idx],
                saturation=saturation,
                value=self.VALUE
            )

            self.color_cache[part.geometry_hash] = color

        # Apply cached colors to all parts
        for part in parts:
            if part.geometry_hash in self.color_cache:
                part.color = self.color_cache[part.geometry_hash]

    def generate_colors_all_different(self, parts: List[Part]):
        """
        Generate unique colors for all parts based on their part_id.
        Each part gets a distinct color derived from a hash of its part_id.
        
        Saturation decreases with part volume (larger parts → less saturated).
        This mode assigns a unique hue to each part but sizes still affect saturation.
        
        Hues are distributed across the entire colorspace for maximum variety.
        """
        self.color_cache.clear()
        
        # Get all parts with geometry data for volume normalization
        geom_parts = [p for p in parts if p.geometry_data]
        if not geom_parts:
            # Fallback: no geometry data, use constant saturation
            for part in parts:
                self._assign_color_by_id(part, saturation=0.8)
            return
        
        # Get volume range for normalization
        volumes = [p.geometry_data.volume for p in geom_parts]
        min_v, max_v = min(volumes), max(volumes)
        
        # Assign colors with volume-based saturation
        for part in parts:
            if part.geometry_data:
                # Normalize volume
                volume_norm = self._normalize(part.geometry_data.volume, min_v, max_v)
                # Get saturation based on volume
                saturation = self._saturation_from_volume(volume_norm)
            else:
                # No geometry data, use medium saturation
                saturation = 0.9
            
            # Generate hash-based hue using full hash for better distribution
            part_id = part.part_id or part.name or str(part.instance_id)
            hash_hex = hashlib.sha256(part_id.encode()).hexdigest()
            
            # Use full hash (not just first 8 chars) for better colorspace coverage
            # Convert entire hash to integer, then normalize to [0, 1)
            hash_int = int(hash_hex, 16)
            hash_normalized = (hash_int % 1000000) / 1000000.0  # [0, 1)
            
            # Map normalized value to hue, skipping purple range
            hue = self._map_normalized_to_hue(hash_normalized)
            
            color = self._hsv_color(
                hue=hue,
                saturation=saturation,
                value=self.VALUE
            )
            
            part.color = color
    
    @staticmethod
    def _map_normalized_to_hue(normalized: float) -> int:
        """
        Map a normalized value [0, 1) to hue space [0, 360),
        avoiding the purple range (290-330).
        
        This ensures even distribution across available hue space.
        """
        # Purple exclusion range
        purple_start = 290
        purple_end = 330
        purple_width = purple_end - purple_start
        available_hue_space = 360 - purple_width
        
        # Map [0, 1) to available hue space
        hue_in_available = normalized * available_hue_space
        
        # Convert back to full 360 space, skipping purple
        if hue_in_available < purple_start:
            hue = hue_in_available
        else:
            hue = hue_in_available + purple_width
        
        return int(hue) % 360
    
    def _assign_color_by_id(self, part: Part, saturation: float = 0.8):
        """Helper to assign color based on part ID with given saturation"""
        part_id = part.part_id or part.name or str(part.instance_id)
        hash_hex = hashlib.sha256(part_id.encode()).hexdigest()
        hash_int = int(hash_hex, 16)
        hash_normalized = (hash_int % 1000000) / 1000000.0
        
        hue = self._map_normalized_to_hue(hash_normalized)
        
        color = self._hsv_color(
            hue=hue,
            saturation=saturation,
            value=self.VALUE
        )
        
        part.color = color

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(value: float, vmin: float, vmax: float) -> float:
        if vmax <= vmin:
            return 0.5
        return (value - vmin) / (vmax - vmin)

    @staticmethod
    def _saturation_from_volume(volume_norm: float) -> float:
        """
        Small parts   → high saturation
        Medium parts  → medium saturation
        Large parts   → low saturation
        """
        if volume_norm < 0.10:
            return 1.0   # small
        elif volume_norm < 0.6:
            return 0.9   # medium
        else:
            return 0.6  # large

    def _generate_hue_slots(
        self,
        count: int,
        min_distance: int
    ) -> List[int]:
        """
        Generate evenly spaced hues with guaranteed minimum distance,
        without endless loops.
        """

        if count <= 0:
            return []

        forbidden_ranges = [
            (290, 330)  # purple block
        ]

        def is_forbidden(h: int) -> bool:
            return any(start <= h < end for start, end in forbidden_ranges)

        # Compute total available hue space (excluding forbidden ranges)
        allowed_space = 360 - sum(end - start for start, end in forbidden_ranges)
        max_hues_possible = allowed_space // min_distance

        if count > max_hues_possible:
            # Reduce min_distance to fit all hues
            min_distance = allowed_space / count

        # Evenly distribute hues across the allowed space
        hues = []
        step = allowed_space / count
        hue = 0

        for _ in range(count):
            # Skip forbidden ranges
            while is_forbidden(int(hue) % 360):
                hue += 1  # move forward until allowed
            hues.append(int(hue) % 360)
            hue += step

        return hues



    @staticmethod
    def _hsv_color(hue: float, saturation: float, value: float) -> Color:
        r, g, b = colorsys.hsv_to_rgb(hue / 360.0, saturation, value)
        return Color(
            r=int(r * 255),
            g=int(g * 255),
            b=int(b * 255)
        )

    # ------------------------------------------------------------------

    def get_highlight_color(self) -> Color:
        return Color(255, 50, 50)

    def get_dimmed_color(self, original_color: Color, alpha: float = 0.3) -> Color:
        return Color(
            r=int(original_color.r * alpha + 200 * (1 - alpha)),
            g=int(original_color.g * alpha + 200 * (1 - alpha)),
            b=int(original_color.b * alpha + 200 * (1 - alpha))
        )
