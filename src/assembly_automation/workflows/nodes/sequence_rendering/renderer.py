"""Incremental sequence visualization built on the shared OCC renderer."""

from pathlib import Path
import time
from typing import Any, Callable

from assembly_automation.stepparser.analysis.geometry import bounding_box
from assembly_automation.stepparser.rendering.renderer import Renderer

from .settings import SequenceRenderingSettings


_SECTION_CAMERAS = {"xy": "top", "xz": "front", "yz": "right"}
_SECTION_AXES = {"xy": 2, "xz": 1, "yz": 0}


def _transparency_suffix(value: float) -> str:
    return str(float(value)).replace(".", "_")


def _image_entropy(path: Path) -> float:
    from PIL import Image

    with Image.open(path) as image:
        return float(image.convert("L").entropy())


class SequenceRenderer:
    """Render all steps while retaining one viewer and cached cut geometry."""

    def __init__(self, loaded, settings: SequenceRenderingSettings):
        self.loaded = loaded
        self.settings = settings
        self.renderer = Renderer(settings)
        self.instances = {item.instance_id: item for item in loaded.instances}
        self._bounds = {item.instance_id: bounding_box(item.shape) for item in loaded.instances}
        self._assembly_bounds = bounding_box(loaded.shape)
        self._section_cache: dict[tuple[str, str, float], Any] = {}
        self.section_fallbacks: list[dict[str, Any]] = []
        self.section_empty_cuts: list[dict[str, Any]] = []

    def _objects(self, instance_ids: list[str]):
        return [(self.instances[item].shape, self.instances[item].color) for item in instance_ids]

    def _exploded(self, instance_ids: list[str]):
        from OCC.Core.gp import gp_Trsf, gp_Vec
        from OCC.Core.TopLoc import TopLoc_Location

        center = self._assembly_bounds["center"]
        objects = []
        for instance_id in instance_ids:
            instance = self.instances[instance_id]
            local_center = self._bounds[instance_id]["center"]
            vector = [(value - origin) * (self.settings.explosion_factor - 1)
                      for value, origin in zip(local_center, center)]
            transform = gp_Trsf()
            transform.SetTranslation(gp_Vec(*vector))
            objects.append((instance.shape.Moved(TopLoc_Location(transform)), instance.color))
        return objects

    def _section_coordinate(self, plane: str, joining_ids: list[str]) -> float:
        axis = _SECTION_AXES[plane]
        low = min(self._bounds[item]["min"][axis] for item in joining_ids)
        high = max(self._bounds[item]["max"][axis] for item in joining_ids)
        return (low + high) / 2

    def _cut_box(self, plane: str, coordinate: float):
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCC.Core.gp import gp_Pnt

        low = list(self._assembly_bounds["min"])
        high = list(self._assembly_bounds["max"])
        diagonal = sum((upper - lower) ** 2 for lower, upper in zip(low, high)) ** 0.5
        margin = max(diagonal * 0.5, 10.0)
        start = [value - margin for value in low]
        dimensions = [(upper - lower) + 2 * margin for lower, upper in zip(low, high)]
        axis = _SECTION_AXES[plane]
        start[axis] = coordinate
        dimensions[axis] = max(high[axis] + margin - coordinate, 1e-6)
        return BRepPrimAPI_MakeBox(gp_Pnt(*start), *dimensions).Shape(), diagonal

    def _cut_shape(self, instance_id: str, plane: str, coordinate: float):
        key = (instance_id, plane, round(coordinate, 9))
        if key in self._section_cache:
            return self._section_cache[key]
        from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut

        original = self.instances[instance_id].shape
        cut_box, diagonal = self._cut_box(plane, coordinate)
        try:
            operation = BRepAlgoAPI_Cut()
            operation.SetArguments(_shape_list(original))
            operation.SetTools(_shape_list(cut_box))
            operation.SetFuzzyValue(max(1e-6, min(diagonal * 1e-5, 1e-3)))
            operation.SetRunParallel(self.settings.boolean_parallel)
            operation.Build()
            successful = operation.IsDone() and not operation.HasErrors()
            result = operation.Shape() if successful else original
            if not successful or result.IsNull():
                result = original
                self.section_fallbacks.append({"instance_id": instance_id, "plane": plane,
                                               "coordinate": coordinate,
                                               "error": "OCC boolean cut did not produce a valid shape"})
            else:
                try:
                    bounding_box(result)
                except ValueError:
                    # A successful cut can legitimately remove an entire part.
                    # Keep it out of the scene instead of passing an empty OCC
                    # shape to camera fitting and origin-axis sizing.
                    result = None
                    self.section_empty_cuts.append({"instance_id": instance_id,
                                                    "plane": plane,
                                                    "coordinate": coordinate})
        except Exception as exc:
            result = original
            self.section_fallbacks.append({"instance_id": instance_id, "plane": plane,
                                           "coordinate": coordinate, "error": str(exc)})
        self._section_cache[key] = result
        return result

    @property
    def section_cache_entries(self) -> int:
        return len(self._section_cache)

    def _section_objects(self, instance_ids: list[str], plane: str, coordinate: float):
        objects = []
        for item in instance_ids:
            shape = self._cut_shape(item, plane, coordinate)
            if shape is not None:
                objects.append((shape, self.instances[item].color))
        return objects

    def render(self, states: list[dict[str, Any]], output_dir: Path,
               progress: Callable[[str, int, int | None], None] | None = None) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []

        def capture(objects, views, filename, *, step_id, category, transparency=0.0, **extra):
            captured = self.renderer.capture_views(
                objects, views, lambda view: output_dir / filename(view), transparency)
            for record in captured:
                path = Path(record["path"])
                record.update({"path": path.relative_to(output_dir).as_posix(),
                               "step_id": step_id, "category": category, **extra})
                records.append(record)
                if progress:
                    progress("sequence_rendering", len(records), None)

        for state in states:
            step = state["step"]
            step_id = step["step_id"]
            prefix = f"step_{step_id:02d}"
            after_objects = self._objects(state["after"])
            for transparency in self.settings.transparency_values:
                suffix = _transparency_suffix(transparency)
                capture(after_objects, self.settings.views,
                        lambda view, p=prefix, s=suffix: f"{p}_{view}_transp_{s}.png",
                        step_id=step_id, category="assembled", transparency=transparency,
                        state="after")

            capture(self._exploded(state["after"]), self.settings.exploded_views,
                    lambda view, p=prefix: f"{p}_{view}_exp_transp_0_0.png",
                    step_id=step_id, category="exploded", state="after")

            if self.settings.highlight_joining_parts and self.settings.highlight_view:
                joining = set(state["joining"])
                highlighted = [
                    (self.instances[item].shape,
                     self.settings.highlight_color if item in joining else self.settings.context_color,
                     0.0 if item in joining else self.settings.context_transparency)
                    for item in state["after"]
                ]
                capture(highlighted, (self.settings.highlight_view,),
                        lambda view, p=prefix: f"{p}_{view}_joining_highlight_transp_0_0.png",
                        step_id=step_id, category="joining_highlight", state="after",
                        highlighted_instance_ids=state["joining"])

            for plane in self.settings.section_planes:
                coordinate = self._section_coordinate(plane, state["joining"])
                camera = _SECTION_CAMERAS[plane]
                section_states = [("after", state["after"])]
                if self.settings.render_before_sections and state["before"]:
                    section_states.insert(0, ("before", state["before"]))
                for label, instance_ids in section_states:
                    capture(self._section_objects(instance_ids, plane, coordinate), (camera,),
                            lambda _view, p=prefix, pl=plane, lab=label:
                                f"{p}_section_{pl}_{lab}_transp_0_0.png",
                            step_id=step_id, category="section", state=label,
                            section_plane=plane, section_coordinate=coordinate)
                    path = output_dir / f"{prefix}_section_{plane}_{label}_transp_0_0.png"
                    if path.exists():
                        records[-1]["entropy"] = _image_entropy(path)
        return records


def _shape_list(shape):
    from OCC.Core.TopTools import TopTools_ListOfShape

    shapes = TopTools_ListOfShape()
    shapes.Append(shape)
    return shapes
