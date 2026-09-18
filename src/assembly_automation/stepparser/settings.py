"""Validated preprocessing settings independent of OCC."""

from dataclasses import asdict, dataclass, fields
from math import isfinite
from typing import Any

from .rendering.views import get_view


def _number(value: Any, name: str, minimum: float = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")


@dataclass(frozen=True)
class RenderingSettings:
    enabled: bool = True
    assembly_views: tuple[str, ...] = ("iso1", "iso4", "front", "top", "right")
    part_views: tuple[str, ...] = ("iso1", "iso4")
    exploded_views: tuple[str, ...] = ("iso1",)
    highlighted_view: str | None = None
    transparency_values: tuple[float, ...] = (0.0,)
    resolution: tuple[int, int] = (1920, 1080)
    explosion_factor: float = 2.5
    edge_width: float = 1.0
    material_specular: float = 0.0
    material_shininess: float = 0.1
    show_origin_axes: bool = True
    origin_axes_size_ratio: float = 0.2

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("rendering.enabled must be boolean")
        if not isinstance(self.show_origin_axes, bool):
            raise ValueError("show_origin_axes must be boolean")
        _number(self.origin_axes_size_ratio, "origin_axes_size_ratio", 0.001)
        for names in (self.assembly_views, self.part_views, self.exploded_views):
            if not isinstance(names, (list, tuple)) or any(not isinstance(n, str) for n in names):
                raise ValueError("View selections must be lists of names")
            if len(set(names)) != len(names):
                raise ValueError("Duplicate view selections are not allowed")
            for name in names:
                get_view(name)
        if self.highlighted_view is not None:
            get_view(self.highlighted_view)
        if not isinstance(self.resolution, (list, tuple)) or len(self.resolution) != 2:
            raise ValueError("resolution must contain width and height")
        if any(type(v) is not int or v <= 0 for v in self.resolution):
            raise ValueError("resolution dimensions must be positive integers")
        if not isinstance(self.transparency_values, (list, tuple)) or not self.transparency_values:
            raise ValueError("transparency_values must be a nonempty list")
        for value in self.transparency_values:
            _number(value, "transparency")
            if value >= 1:
                raise ValueError("transparency must be < 1")
        _number(self.explosion_factor, "explosion_factor", 1)
        _number(self.edge_width, "edge_width", 0.01)
        for name in ("material_specular", "material_shininess"):
            _number(getattr(self, name), name)
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be <= 1")
        for name in ("assembly_views", "part_views", "exploded_views",
                     "transparency_values", "resolution"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class SpatialSettings:
    enabled: bool = True
    contact_tolerance_mm: float = 0.01
    proximity_threshold_mm: float = 3.0
    distance_mode: str = "all_pairs"

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("spatial_relations.enabled must be boolean")
        _number(self.contact_tolerance_mm, "contact_tolerance_mm")
        _number(self.proximity_threshold_mm, "proximity_threshold_mm")
        if self.proximity_threshold_mm < self.contact_tolerance_mm:
            raise ValueError("proximity_threshold_mm must be >= contact_tolerance_mm")
        if self.distance_mode != "all_pairs":
            raise ValueError("Only all_pairs distance mode is implemented")


@dataclass(frozen=True)
class SamSettings:
    enabled: bool = False
    model_type: str = "vit_b"
    checkpoint: str = "data/models/sam/sam_vit_b_01ec64.pth"
    device: str = "auto"
    points_per_side: int = 32
    points_per_batch: int = 16
    pred_iou_thresh: float = 0.88
    stability_score_thresh: float = 0.95
    min_mask_region_area: int = 100
    overlay_alpha: float = 0.55

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("sam.enabled must be boolean")
        if self.model_type not in ("vit_b", "vit_l", "vit_h"):
            raise ValueError("sam.model_type must be vit_b, vit_l or vit_h")
        if not isinstance(self.checkpoint, str) or not self.checkpoint.strip():
            raise ValueError("sam.checkpoint must be a nonempty path")
        if self.device not in ("auto", "cpu", "cuda"):
            raise ValueError("sam.device must be auto, cpu or cuda")
        for name in ("points_per_side", "points_per_batch", "min_mask_region_area"):
            minimum = 0 if name == "min_mask_region_area" else 1
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"sam.{name} must be an integer >= {minimum}")
        for name in ("pred_iou_thresh", "stability_score_thresh", "overlay_alpha"):
            _number(getattr(self, name), f"sam.{name}")
            if getattr(self, name) > 1:
                raise ValueError(f"sam.{name} must be <= 1")


@dataclass(frozen=True)
class ImageSelectionSettings:
    enabled: bool = True
    include_exploded: bool = False
    analysis_size: int = 128
    tile_size: tuple[int, int] = (960, 540)
    assembly_entropy_weight: float = 0.15

    def __post_init__(self):
        for name in ("enabled", "include_exploded"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"automaticimageselection.{name} must be boolean")
        if type(self.analysis_size) is not int or not 32 <= self.analysis_size <= 512:
            raise ValueError("analysis_size must be an integer from 32 to 512")
        if not isinstance(self.tile_size, (tuple, list)) or len(self.tile_size) != 2 or any(type(v) is not int or v < 1 for v in self.tile_size):
            raise ValueError("tile_size must contain two positive integers")
        object.__setattr__(self, "tile_size", tuple(self.tile_size))
        _number(self.assembly_entropy_weight, "assembly_entropy_weight")
        if self.assembly_entropy_weight > 1:
            raise ValueError("assembly_entropy_weight must be <= 1")


def _construct(cls, value: dict):
    if not isinstance(value, dict):
        raise ValueError(f"{cls.__name__} settings must be a mapping")
    unknown = set(value) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} settings: {sorted(unknown)}")
    return cls(**value)


@dataclass(frozen=True)
class StepParserSettings:
    color_mode: str = "geometry"
    rendering: RenderingSettings = RenderingSettings()
    spatial_relations: SpatialSettings = SpatialSettings()
    sam: SamSettings = SamSettings()
    automaticimageselection: ImageSelectionSettings = ImageSelectionSettings()

    def __post_init__(self):
        if self.color_mode not in ("geometry", "different"):
            raise ValueError("color_mode must be geometry or different")

    @classmethod
    def from_mapping(cls, value: dict) -> "StepParserSettings":
        if not isinstance(value, dict):
            raise ValueError("step_preprocessing settings must be a mapping")
        unknown = set(value) - {"color_mode", "rendering", "spatial_relations", "sam", "automaticimageselection"}
        if unknown:
            raise ValueError(f"Unknown preprocessing settings: {sorted(unknown)}")
        return cls(color_mode=value.get("color_mode", "geometry"),
                   rendering=_construct(RenderingSettings, value.get("rendering", {})),
                   spatial_relations=_construct(SpatialSettings, value.get("spatial_relations", {})),
                   sam=_construct(SamSettings, value.get("sam", {})),
                   automaticimageselection=_construct(ImageSelectionSettings, value.get("automaticimageselection", {})))

    def to_dict(self) -> dict:
        return asdict(self)
