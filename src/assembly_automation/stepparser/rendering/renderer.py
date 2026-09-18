"""Persistent offscreen OCC viewer; camera names live in views.py."""

from pathlib import Path

from .views import get_view


class Renderer:
    def __init__(self, settings):
        self.settings = settings
        self.display = None

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
        from OCC.Core.AIS import AIS_Shape, AIS_Shaded
        from OCC.Core.Aspect import Aspect_TOL_SOLID
        from OCC.Core.Prs3d import Prs3d_LineAspect
        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCC.Core.Graphic3d import (Graphic3d_BT_RGB, Graphic3d_MaterialAspect,
                                      Graphic3d_NOM_PLASTIC)
        from PIL import Image

        view = get_view(view_name)
        self._initialize()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.display.Context.RemoveAll(False)
        try:
            for shape, color in objects:
                ais = AIS_Shape(shape)
                # Control reflected highlights separately from the part color.
                material = Graphic3d_MaterialAspect(Graphic3d_NOM_PLASTIC)
                specular = self.settings.material_specular
                material.SetSpecularColor(Quantity_Color(specular, specular, specular, Quantity_TOC_RGB))
                material.SetShininess(self.settings.material_shininess)
                ais.SetMaterial(material)
                ais.SetColor(Quantity_Color(*(v / 255 for v in color), Quantity_TOC_RGB))
                ais.SetTransparency(transparency)
                drawer = ais.Attributes()
                drawer.SetFaceBoundaryDraw(True)
                drawer.SetFaceBoundaryAspect(Prs3d_LineAspect(
                    Quantity_Color(0., 0., 0., Quantity_TOC_RGB), Aspect_TOL_SOLID, self.settings.edge_width))
                self.display.Context.Display(ais, False)
                self.display.Context.SetDisplayMode(ais, AIS_Shaded, False)
            if self.settings.show_origin_axes and objects:
                self._display_origin_axes(objects)
            self.display.View.SetProj(*view.direction)
            self.display.View.SetUp(*view.up)
            self.display.View.FitAll(0.01, False)
            # Capture an exact-size offscreen buffer; native window borders must
            # not determine the PNG dimensions. OCC returns bottom-up RGB rows.
            width, height = self.settings.resolution
            buffer = self.display.GetImageData(width, height, Graphic3d_BT_RGB)
            if not buffer:
                raise RuntimeError(f"OCC image capture failed: {path}")
            image = Image.frombytes("RGB", (width, height), buffer)
            image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(path)
        finally:
            self.display.Context.RemoveAll(False)

    def _display_origin_axes(self, objects):
        from OCC.Core.AIS import AIS_Trihedron
        from OCC.Core.Geom import Geom_Axis2Placement
        from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCC.Core.Prs3d import Prs3d_DP_XAxis, Prs3d_DP_YAxis, Prs3d_DP_ZAxis
        from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCC.Core.Graphic3d import Graphic3d_ZLayerId_Topmost
        from ..analysis.geometry import bounding_box

        boxes = [bounding_box(shape) for shape, _ in objects]
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
        from OCC.Core.gp import gp_Trsf, gp_Vec
        from OCC.Core.TopLoc import TopLoc_Location
        from ..analysis.geometry import bounding_box

        records = []
        assembly_objects = [(i.shape, i.color) for i in loaded.instances]
        center = bounding_box(loaded.shape)["center"]
        exploded = []
        if self.settings.exploded_views:
            for instance in loaded.instances:
                local_center = bounding_box(instance.shape)["center"]
                shift = gp_Trsf()
                shift.SetTranslation(gp_Vec(*((v - c) * (self.settings.explosion_factor - 1)
                                             for v, c in zip(local_center, center))))
                exploded.append((instance.shape.Moved(TopLoc_Location(shift)), instance.color))

        def save(objects, name, relative, transparency, **metadata):
            self.capture(objects, name, output_dir / relative, transparency)
            records.append({"path": relative.as_posix(), "view": name, "transparency": transparency, **metadata})
            if progress:
                progress("rendering", len(records), None)

        for transparency in self.settings.transparency_values:
            suffix = str(float(transparency)).replace(".", "_")
            for name in self.settings.assembly_views:
                save(assembly_objects, name, Path(f"images/assembly/{name}_transp_{suffix}.png"), transparency,
                     category="assembly")
            for name in self.settings.exploded_views:
                save(exploded, name, Path(f"images/assembly/{name}_exploded_transp_{suffix}.png"), transparency,
                     category="exploded")
            # Canonical local geometry is rendered once; no duplicate PNG copies.
            for definition in loaded.definitions:
                for name in self.settings.part_views:
                    save([(definition.shape, definition.color)], name,
                         Path(f"images/parts/{definition.part_id}/{name}_transp_{suffix}.png"), transparency,
                         category="part", part_id=definition.part_id, coordinate_frame="part_local")
            if self.settings.highlighted_view:
                for instance in loaded.instances:
                    objects = [(other.shape, other.color if other.instance_id == instance.instance_id else [210, 210, 210])
                               for other in loaded.instances]
                    save(objects, self.settings.highlighted_view,
                         Path(f"images/parts/{instance.instance_id}/highlighted_transp_{suffix}.png"), transparency,
                         category="highlighted", instance_id=instance.instance_id)
        return records
