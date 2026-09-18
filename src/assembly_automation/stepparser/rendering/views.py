"""Eye directions: X right, Y rear, Z up. ISO4 fixes the old duplicate camera.

legacy_iso4 preserves the old duplicated assembly camera explicitly.
"""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class CameraView:
    direction: tuple[float, float, float]
    up: tuple[float, float, float] = (0, 0, 1)


VIEWS = MappingProxyType({
    "iso1": CameraView((-1, 1, 1)),
    "iso2": CameraView((-1, 1, -1)),
    "iso3": CameraView((1, -1, -1)),
    "iso4": CameraView((1, -1, 1)),
    "legacy_iso4": CameraView((-1, 1, -1)),
    "front": CameraView((0, -1, 0)),
    "rear": CameraView((0, 1, 0)),
    "right": CameraView((1, 0, 0)),
    "left": CameraView((-1, 0, 0)),
    "top": CameraView((0, 0, 1), (0, 1, 0)),
    "bottom": CameraView((0, 0, -1), (0, -1, 0)),
})


def get_view(name: str) -> CameraView:
    try:
        return VIEWS[name]
    except KeyError:
        raise ValueError(f"Unknown view {name!r}; available: {', '.join(VIEWS)}") from None
