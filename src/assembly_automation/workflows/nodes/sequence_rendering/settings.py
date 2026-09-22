"""Validated settings for deterministic assembly-sequence rendering."""

from dataclasses import asdict, dataclass, field, fields
from math import isfinite
from typing import Any, Mapping

from assembly_automation.stepparser.rendering.views import get_view


def _number(value: Any, name: str, minimum: float, maximum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < minimum or (maximum is not None and value > maximum):
        interval = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise ValueError(f"{name} must be {interval}")


@dataclass(frozen=True)
class SequenceCollageSettings:
    enabled: bool = True
    additional_views: int = 2
    include_highlight: bool = True
    include_exploded: bool = True
    analysis_size: int = 128
    tile_size: tuple[int, int] = (960, 540)
    entropy_weight: float = 0.15
    crop_whitespace: bool = True
    crop_padding_px: int = 12

    def __post_init__(self):
        for name in ("enabled", "include_highlight", "include_exploded", "crop_whitespace"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"sequence_rendering.collage.{name} must be boolean")
        if type(self.additional_views) is not int or self.additional_views < 0:
            raise ValueError("collage.additional_views must be a nonnegative integer")
        if type(self.analysis_size) is not int or not 32 <= self.analysis_size <= 512:
            raise ValueError("collage.analysis_size must be an integer from 32 to 512")
        if (not isinstance(self.tile_size, (list, tuple)) or len(self.tile_size) != 2
                or any(type(value) is not int or value <= 0 for value in self.tile_size)):
            raise ValueError("collage.tile_size must contain two positive integers")
        if type(self.crop_padding_px) is not int or self.crop_padding_px < 0:
            raise ValueError("collage.crop_padding_px must be a nonnegative integer")
        _number(self.entropy_weight, "collage.entropy_weight", 0, 1)
        object.__setattr__(self, "tile_size", tuple(self.tile_size))


@dataclass(frozen=True)
class SequenceRenderingSettings:
    enabled: bool = True
    views: tuple[str, ...] = ("iso1", "iso2")
    transparency_values: tuple[float, ...] = (0.0,)
    exploded_views: tuple[str, ...] = ("iso1", "iso2")
    explosion_factor: float = 2.5
    section_planes: tuple[str, ...] = ("xy", "xz", "yz")
    render_before_sections: bool = True
    highlight_joining_parts: bool = True
    highlight_view: str | None = "iso1"
    highlight_color: tuple[int, int, int] = (255, 0, 255)
    context_color: tuple[int, int, int] = (150, 150, 150)
    context_transparency: float = 0.8
    boolean_parallel: bool = True
    color_mode: str = "geometry"
    resolution: tuple[int, int] = (1920, 1080)
    crop_whitespace: bool = True
    crop_padding_px: int = 16
    edge_width: float = 1.0
    material_specular: float = 0.0
    material_shininess: float = 0.1
    show_origin_axes: bool = True
    origin_axes_size_ratio: float = 0.2
    collage: SequenceCollageSettings = field(default_factory=SequenceCollageSettings)

    def __post_init__(self):
        for name in ("enabled", "render_before_sections", "highlight_joining_parts",
                     "boolean_parallel", "crop_whitespace", "show_origin_axes"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"sequence_rendering.{name} must be boolean")
        for names in (self.views, self.exploded_views):
            if not isinstance(names, (list, tuple)) or len(set(names)) != len(names):
                raise ValueError("Sequence camera views must be a duplicate-free list")
            for name in names:
                get_view(name)
        if self.highlight_view is not None:
            get_view(self.highlight_view)
        if (not isinstance(self.section_planes, (list, tuple))
                or any(name not in {"xy", "xz", "yz"} for name in self.section_planes)
                or len(set(self.section_planes)) != len(self.section_planes)):
            raise ValueError("section_planes may contain xy, xz and yz once each")
        if not isinstance(self.transparency_values, (list, tuple)) or not self.transparency_values:
            raise ValueError("transparency_values must be a nonempty list")
        for value in self.transparency_values:
            _number(value, "transparency", 0, 0.999999)
        if not isinstance(self.resolution, (list, tuple)) or len(self.resolution) != 2:
            raise ValueError("resolution must contain width and height")
        if any(type(value) is not int or value <= 0 for value in self.resolution):
            raise ValueError("resolution dimensions must be positive integers")
        for name in ("highlight_color", "context_color"):
            value = getattr(self, name)
            if (not isinstance(value, (list, tuple)) or len(value) != 3
                    or any(type(channel) is not int or not 0 <= channel <= 255 for channel in value)):
                raise ValueError(f"{name} must contain three integer RGB channels")
        if type(self.crop_padding_px) is not int or self.crop_padding_px < 0:
            raise ValueError("crop_padding_px must be a nonnegative integer")
        _number(self.explosion_factor, "explosion_factor", 1)
        _number(self.context_transparency, "context_transparency", 0, 0.999999)
        _number(self.edge_width, "edge_width", 0.01)
        _number(self.material_specular, "material_specular", 0, 1)
        _number(self.material_shininess, "material_shininess", 0, 1)
        _number(self.origin_axes_size_ratio, "origin_axes_size_ratio", 0.001)
        if self.color_mode not in {"geometry", "different"}:
            raise ValueError("color_mode must be geometry or different")
        if not isinstance(self.collage, SequenceCollageSettings):
            raise ValueError("sequence_rendering.collage must be SequenceCollageSettings")
        for name in ("views", "transparency_values", "exploded_views", "section_planes",
                     "resolution", "highlight_color", "context_color"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "SequenceRenderingSettings":
        value = dict(value or {})
        unknown = set(value) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown sequence_rendering settings: {sorted(unknown)}")
        collage = value.get("collage", {})
        if not isinstance(collage, Mapping):
            raise ValueError("sequence_rendering.collage must be a mapping")
        unknown_collage = set(collage) - {item.name for item in fields(SequenceCollageSettings)}
        if unknown_collage:
            raise ValueError(f"Unknown sequence collage settings: {sorted(unknown_collage)}")
        value["collage"] = SequenceCollageSettings(**dict(collage))
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
