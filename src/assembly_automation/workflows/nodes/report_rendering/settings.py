"""Validated settings for deterministic report rendering."""

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Mapping


def _color(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"report_rendering.style.{name} must be a #RRGGBB color")
    try:
        int(value[1:], 16)
    except ValueError as exc:
        raise ValueError(f"report_rendering.style.{name} must be a #RRGGBB color") from exc


@dataclass(frozen=True)
class ReportProfileSettings:
    enabled: bool = True
    include_steps: bool = False
    include_parts: bool = False
    max_findings: int = 5
    max_recommendations: int = 5

    def __post_init__(self):
        for name in ("enabled", "include_steps", "include_parts"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"report profile {name} must be boolean")
        for name in ("max_findings", "max_recommendations"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"report profile {name} must be a positive integer")


@dataclass(frozen=True)
class ReportStyleSettings:
    primary: str = "#125B57"
    accent: str = "#2E8B57"
    risk: str = "#B23A48"
    muted: str = "#66737A"
    background: str = "#F4F7F6"
    font_family: str = "DejaVu Sans"

    def __post_init__(self):
        for name in ("primary", "accent", "risk", "muted", "background"):
            _color(getattr(self, name), name)
        if not isinstance(self.font_family, str) or not self.font_family.strip():
            raise ValueError("report_rendering.style.font_family must be nonempty")


def _default_profiles() -> dict[str, ReportProfileSettings]:
    return {
        "executive": ReportProfileSettings(),
        "engineering": ReportProfileSettings(include_steps=True, include_parts=True,
                                               max_findings=12, max_recommendations=12),
    }


@dataclass(frozen=True)
class ReportRenderingSettings:
    enabled: bool = True
    formats: tuple[str, ...] = ("html",)
    profiles: Mapping[str, ReportProfileSettings] = field(default_factory=_default_profiles)
    page_size: tuple[float, float] = (11.69, 8.27)
    dpi: int = 160
    style: ReportStyleSettings = field(default_factory=ReportStyleSettings)

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("report_rendering.enabled must be boolean")
        if (not isinstance(self.formats, (list, tuple)) or tuple(self.formats) != ("html",)):
            raise ValueError("report_rendering.formats currently supports only [html]")
        if set(self.profiles) != {"executive", "engineering"}:
            raise ValueError("report_rendering.profiles requires executive and engineering")
        if not any(item.enabled for item in self.profiles.values()):
            raise ValueError("At least one report rendering profile must be enabled")
        if (not isinstance(self.page_size, (list, tuple)) or len(self.page_size) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
                       for value in self.page_size)):
            raise ValueError("report_rendering.page_size requires two positive numbers")
        if type(self.dpi) is not int or not 72 <= self.dpi <= 600:
            raise ValueError("report_rendering.dpi must be an integer from 72 to 600")
        object.__setattr__(self, "formats", tuple(self.formats))
        object.__setattr__(self, "page_size", tuple(float(value) for value in self.page_size))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ReportRenderingSettings":
        value = dict(value or {})
        unknown = set(value) - {item.name for item in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown report_rendering settings: {sorted(unknown)}")
        raw_profiles = value.get("profiles", {})
        if not isinstance(raw_profiles, Mapping):
            raise ValueError("report_rendering.profiles must be a mapping")
        defaults = _default_profiles()
        unknown_profiles = set(raw_profiles) - set(defaults)
        if unknown_profiles:
            raise ValueError(f"Unknown report profiles: {sorted(unknown_profiles)}")
        profiles = {}
        for name, default in defaults.items():
            raw = raw_profiles.get(name, {})
            if not isinstance(raw, Mapping):
                raise ValueError(f"report_rendering.profiles.{name} must be a mapping")
            unknown_keys = set(raw) - {item.name for item in fields(ReportProfileSettings)}
            if unknown_keys:
                raise ValueError(f"Unknown {name} report settings: {sorted(unknown_keys)}")
            profiles[name] = ReportProfileSettings(**{**asdict(default), **dict(raw)})
        raw_style = value.get("style", {})
        if not isinstance(raw_style, Mapping):
            raise ValueError("report_rendering.style must be a mapping")
        unknown_style = set(raw_style) - {item.name for item in fields(ReportStyleSettings)}
        if unknown_style:
            raise ValueError(f"Unknown report style settings: {sorted(unknown_style)}")
        value["profiles"] = profiles
        value["style"] = ReportStyleSettings(**dict(raw_style))
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
