"""Persistent offscreen OCC viewer; camera names live in views.py."""

from pathlib import Path
from contextlib import contextmanager
import time

from .views import get_view


class Renderer:
    def __init__(self, settings):
        self.settings = settings
        self.display = None
        self._bounds_cache = {}

    def _initialize(self):
        if self.display is not None:
            return
        from OCC.Display.OCCViewer import Viewer3d
        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

        viewer = Viewer3d()
        viewer.Create(display_glinfo=False)
        viewer.SetSize(*self.settings.resolution)
        viewer.View.SetBackgroundColor(Quantity_Color(1., 1., 1., Quantity_TOC_RGB))
        window = viewer.View.Window()
        if window is not None:
            window.Unmap()
        self.display = viewer

    def capture(self, objects, view_name: str, path: Path, transparency=0.0):
        get_view(view_name)
        with self._scene(objects, transparency):
            self._capture_loaded(view_name, path)

    def capture_views(self, objects, views, path_for_view, transparency=0.0):
        """Prepare one OCC scene and capture several named camera views.

        This is the shared rendering primitive used by preprocessing and by
        sequence rendering. ``path_for_view`` receives a view name and returns
        its output path.
        """
        names = tuple(views)
        for name in names:
            get_view(name)
        results = []
        if not names or not objects:
            return results
        started = time.perf_counter()
        with self._scene(objects, transparency):
            preparation = time.perf_counter() - started
            for index, name in enumerate(names):
                path = Path(path_for_view(name))
                capture_started = time.perf_counter()
                image_size = self._capture_loaded(name, path)
                results.append({
                    "path": str(path),
                    "view": name,
                    "transparency": transparency,
                    "image_size": list(image_size),
                    "capture_seconds": time.perf_counter() - capture_started,
                    "scene_preparation_seconds": preparation if index == 0 else 0,
                })
        return results

    @contextmanager
    def _scene(self, objects, transparency):
        from OCC.Core.AIS import AIS_Shape, AIS_Shaded
        from OCC.Core.Aspect import Aspect_TOL_SOLID
        from OCC.Core.Prs3d import Prs3d_LineAspect
        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCC.Core.Graphic3d import (Graphic3d_MaterialAspect,
                                      Graphic3d_NOM_PLASTIC)
        self._initialize()
        self.display.Context.RemoveAll(False)
        try:
            for item in objects:
                shape, color = item[:2]
                object_transparency = item[2] if len(item) > 2 else transparency
                ais = AIS_Shape(shape)
                # Control reflected highlights separately from the part color.
                material = Graphic3d_MaterialAspect(Graphic3d_NOM_PLASTIC)
                specular = self.settings.material_specular
                material.SetSpecularColor(Quantity_Color(specular, specular, specular, Quantity_TOC_RGB))
                material.SetShininess(self.settings.material_shininess)
                ais.SetMaterial(material)
                ais.SetColor(Quantity_Color(*(v / 255 for v in color), Quantity_TOC_RGB))
                ais.SetTransparency(object_transparency)
                drawer = ais.Attributes()
                drawer.SetFaceBoundaryDraw(True)
                drawer.SetFaceBoundaryAspect(Prs3d_LineAspect(
                    Quantity_Color(0., 0., 0., Quantity_TOC_RGB), Aspect_TOL_SOLID, self.settings.edge_width))
                # Select shading before display to avoid building wireframe first.
                ais.SetDisplayMode(AIS_Shaded)
                self.display.Context.Display(ais, False)
            if self.settings.show_origin_axes and objects:
                self._display_origin_axes(objects)
            yield
        finally:
            self.display.Context.RemoveAll(False)

    def _capture_loaded(self, view_name, path):
        from OCC.Core.Graphic3d import Graphic3d_BT_RGB
        from PIL import Image

        view = get_view(view_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.display.View.SetProj(*view.direction)
        self.display.View.SetUp(*view.up)
        self.display.View.FitAll(0.01, False)
        width, height = self.settings.resolution
        buffer = self.display.GetImageData(width, height, Graphic3d_BT_RGB)
        if not buffer:
            raise RuntimeError(f"OCC image capture failed: {path}")
        image = Image.frombytes("RGB", (width, height), buffer)
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if self.settings.crop_whitespace:
            from .image_layout import crop_to_content
            image = crop_to_content(image, self.settings.crop_padding_px)
        image.save(path)
        return image.size

    def _bounds(self, shape):
        from ..analysis.geometry import bounding_box

        key = id(shape)
        if key not in self._bounds_cache:
            # Retain the wrapper so its id cannot be reused during the render.
            self._bounds_cache[key] = (shape, bounding_box(shape))
        return self._bounds_cache[key][1]

    def _display_origin_axes(self, objects):
        from OCC.Core.AIS import AIS_Trihedron
        from OCC.Core.Geom import Geom_Axis2Placement
        from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCC.Core.Prs3d import Prs3d_DP_XAxis, Prs3d_DP_YAxis, Prs3d_DP_ZAxis
        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCC.Core.Graphic3d import Graphic3d_ZLayerId_Topmost
        boxes = [self._bounds(item[0]) for item in objects]
        span = max(max(box["max"][axis] for box in boxes)
                   - min(box["min"][axis] for box in boxes) for axis in range(3))
        axes = AIS_Trihedron(Geom_Axis2Placement(
            gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))))
        axes.SetSize(max(span * self.settings.origin_axes_size_ratio, 0.001))
        axes.SetDrawArrows(True)
        for part, rgb in ((Prs3d_DP_XAxis, (0.85, 0.1, 0.1)),
                          (Prs3d_DP_YAxis, (0.1, 0.6, 0.1)),
                          (Prs3d_DP_ZAxis, (0.1, 0.25, 0.9))):
            axes.SetDatumPartColor(part, Quantity_Color(*rgb, Quantity_TOC_RGB))
        axes.SetTextColor(Quantity_Color(0.1, 0.1, 0.1, Quantity_TOC_RGB))
        # Keep the origin marker readable even when inside an opaque part.
        axes.SetZLayer(Graphic3d_ZLayerId_Topmost)
        self.display.Context.Display(axes, False)

    def render(self, loaded, output_dir: Path, progress=None) -> list[dict]:
        self._bounds_cache.clear()
        try:
            return self._render(loaded, output_dir, progress)
        finally:
            self._bounds_cache.clear()

    def _render(self, loaded, output_dir: Path, progress=None) -> list[dict]:
        from OCC.Core.gp import gp_Trsf, gp_Vec
        from OCC.Core.TopLoc import TopLoc_Location

        records = []
        assembly_objects = [(i.shape, i.color) for i in loaded.instances]
        center = self._bounds(loaded.shape)["center"] if self.settings.exploded_views else None
        exploded = []
        if self.settings.exploded_views:
            for instance in loaded.instances:
                local_center = self._bounds(instance.shape)["center"]
                shift = gp_Trsf()
                shift.SetTranslation(gp_Vec(*((v - c) * (self.settings.explosion_factor - 1)
                                             for v, c in zip(local_center, center))))
                exploded.append((instance.shape.Moved(TopLoc_Location(shift)), instance.color))

        def save_views(objects, names, path_for_view, transparency, **metadata):
            if not names:
                return
            captured = self.capture_views(
                objects, names, lambda name: output_dir / path_for_view(name), transparency)
            for record in captured:
                relative = Path(record["path"]).relative_to(output_dir)
                record.update({"path": relative.as_posix(), **metadata})
                records.append(record)
                if progress:
                    progress("rendering", len(records), None)

        for transparency in self.settings.transparency_values:
            suffix = str(float(transparency)).replace(".", "_")
            save_views(assembly_objects, self.settings.assembly_views,
                       lambda name: Path(f"images/assembly/{name}_transp_{suffix}.png"),
                       transparency, category="assembly")
            save_views(exploded, self.settings.exploded_views,
                       lambda name: Path(f"images/assembly/{name}_exploded_transp_{suffix}.png"),
                       transparency, category="exploded")
            # Canonical local geometry is rendered once; no duplicate PNG copies.
            for definition in loaded.definitions:
                save_views([(definition.shape, definition.color)], self.settings.part_views,
                           lambda name: Path(f"images/parts/{definition.part_id}/{name}_transp_{suffix}.png"),
                           transparency, category="part", part_id=definition.part_id, coordinate_frame="part_local")
            if self.settings.highlighted_view:
                for definition in loaded.definitions:
                    members = [item for item in loaded.instances if item.part_id == definition.part_id]
                    if not members:
                        continue
                    instance = members[0]
                    objects = [(other.shape,
                                [255, 0, 255] if other.part_id == instance.part_id else [150, 150, 150],
                                0.0 if other.part_id == instance.part_id else 0.8)
                               for other in loaded.instances]
                    save_views(objects, (self.settings.highlighted_view,),
                               lambda name: Path(f"images/parts/{instance.instance_id}/highlighted_transp_{suffix}.png"),
                               transparency, category="highlighted", instance_id=instance.instance_id,
                               part_id=instance.part_id, coordinate_frame="assembly",
                               highlighted_instance_ids=[item.instance_id for item in members])
        return records
