"""Geometry acceptance checks; run in an environment with pythonOCC 7.9."""

from dataclasses import replace
import json
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.stepparser import StepParserSettings, StepProcessor
from assembly_automation.stepparser.analysis.geometry import measure_shape, validate_shape
from assembly_automation.stepparser.analysis.spatial_relations import compute_spatial_relations
from assembly_automation.stepparser.core.models import LoadedAssembly, PartDefinition, PartInstance
from assembly_automation.stepparser.io.step_loader import load_step, make_compound, transform_matrix
from assembly_automation.stepparser.rendering.color_generator import assign_colors
from assembly_automation.stepparser.rendering.views import get_view
from assembly_automation.stepparser.settings import RenderingSettings, SpatialSettings

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere
from OCC.Core.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Interface import Interface_Static
from OCC.Core.STEPCAFControl import STEPCAFControl_Writer
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool


def translated(x=0, y=0, z=0):
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(transform)


def instance(identifier, shape):
    return PartInstance(identifier, identifier, identifier, "assy_001", [], TopLoc_Location(), shape)


class ConfigurationTests(unittest.TestCase):
    def test_invalid_settings_fail_before_viewer_creation(self):
        for mapping in ({"typo": True}, {"rendering": {"part_views": ["typo"]}},
                        {"spatial_relations": {"contact_tolerance_mm": 4, "proximity_threshold_mm": 3}},
                        {"rendering": {"resolution": [0, 1080]}},
                        {"rendering": {"transparency_values": [float("nan")]}}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                StepParserSettings.from_mapping(mapping)

    def test_named_views_and_disable_selections(self):
        self.assertNotEqual(get_view("iso2"), get_view("iso4"))
        self.assertEqual(get_view("iso2"), get_view("legacy_iso4"))
        settings = StepParserSettings.from_mapping({"rendering": {"assembly_views": [], "part_views": []}})
        self.assertFalse(settings.rendering.part_views)


class GeometryTests(unittest.TestCase):
    def test_box_measurements_and_embedded_surfaces(self):
        shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        self.assertTrue(validate_shape(shape)["is_valid"])
        geometry = measure_shape(shape)
        self.assertAlmostEqual(geometry["volume"], 6000)
        self.assertAlmostEqual(geometry["surface_area"], 2200)
        self.assertEqual(geometry["topology"]["edges"], 12)
        self.assertEqual(len(geometry["surface_details"]), 6)
        for actual, expected in zip(sorted(geometry["oriented_bounding_box"]["dimensions"]), [10, 20, 30]):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_null_shape_is_invalid(self):
        self.assertFalse(validate_shape(TopoDS_Shape())["is_valid"])

    def test_contacts_gaps_overlaps_and_failed_pairs(self):
        base = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
        settings = SpatialSettings(contact_tolerance_mm=0.01, proximity_threshold_mm=3)
        for offset, distance, classification in ((10, 0, "contact_or_overlap"),
                                                  (12, 2, "close"), (14, 4, "separated"),
                                                  (5, 0, "contact_or_overlap")):
            with self.subTest(offset=offset):
                result = compute_spatial_relations([instance("a", base), instance("b", base.Moved(translated(offset)))], settings)
                self.assertEqual(len(result["pairs"]), 1)
                pair = result["pairs"][0]
                self.assertAlmostEqual(pair["distance_mm"], distance)
                self.assertEqual(pair["classification"], classification)
                if classification == "contact_or_overlap":
                    self.assertEqual(result["contact_map"], {"a": ["b"], "b": ["a"]})
        result = compute_spatial_relations([instance("a", base), instance("b", TopoDS_Shape())], settings)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["pairs"][0]["distance_mm"])

    def test_overlapping_boxes_do_not_imply_brep_contact(self):
        left = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 0), 1).Shape()
        right = BRepPrimAPI_MakeSphere(gp_Pnt(1.5, 1.5, 0), 1).Shape()
        result = compute_spatial_relations([instance("a", left), instance("b", right)], SpatialSettings())
        pair = result["pairs"][0]
        self.assertAlmostEqual(pair["distance_mm"], math.sqrt(4.5) - 2, places=6)
        self.assertEqual(pair["classification"], "close")

    def test_containment_is_recorded(self):
        outer = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
        inner = BRepPrimAPI_MakeBox(gp_Pnt(2, 2, 2), 1, 1, 1).Shape()
        result = compute_spatial_relations([instance("outer", outer), instance("inner", inner)], SpatialSettings())
        self.assertTrue(result["pairs"][0]["inner_solution"])

    def test_colors_are_deterministic_without_global_random_changes(self):
        definitions = [PartDefinition("small", "small", "a", None, geometry={"volume": 1}),
                       PartDefinition("large", "large", "b", None, geometry={"volume": 100})]
        instances = [instance("small", None), instance("large", None)]
        before = random.getstate()
        assign_colors(definitions, instances)
        colors = [list(d.color) for d in definitions]
        self.assertEqual(before, random.getstate())
        assign_colors(definitions, instances)
        self.assertEqual(colors, [d.color for d in definitions])


class ImportAndExportTests(unittest.TestCase):
    def test_inch_source_is_normalized_to_millimeters(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "inch.stp"
            writer = STEPControl_Writer()
            original_unit = Interface_Static.CVal("write.step.unit")
            try:
                self.assertTrue(Interface_Static.SetCVal("write.step.unit", "INCH"))
                writer.Transfer(BRepPrimAPI_MakeBox(25.4, 50.8, 76.2).Shape(), STEPControl_AsIs)
                self.assertEqual(writer.Write(str(source)), IFSelect_RetDone)
            finally:
                Interface_Static.SetCVal("write.step.unit", original_unit)
            self.assertIn("CONVERSION_BASED_UNIT('INCH'", source.read_text(encoding="ascii"))
            loaded = load_step(source)
            geometry = measure_shape(loaded.definitions[0].shape)
            for actual, expected in zip(geometry["bounding_box"]["dimensions"], [25.4, 50.8, 76.2]):
                self.assertAlmostEqual(actual, expected, places=5)

    def test_multiple_free_roots_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            document = TDocStd_Document("test")
            tool = XCAFDoc_DocumentTool.ShapeTool(document.Main())
            tool.AddShape(BRepPrimAPI_MakeBox(1, 2, 3).Shape(), False)
            tool.AddShape(BRepPrimAPI_MakeBox(gp_Pnt(10, 0, 0), 2, 3, 4).Shape(), False)
            writer = STEPCAFControl_Writer()
            self.assertTrue(writer.Transfer(document, STEPControl_AsIs))
            path = Path(directory) / "multiple.stp"
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            loaded = load_step(path)
            self.assertEqual(len(loaded.instances), 2)
            self.assertEqual(len(loaded.definitions), 2)

    def test_invalid_geometry_stops_before_analysis_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.stp"
            source.write_text("test input", encoding="ascii")
            definition = PartDefinition("part_001", "invalid", "a", TopoDS_Shape())
            loaded = LoadedAssembly("invalid", [definition], [], [], TopoDS_Shape(), {})
            output = Path(directory) / "output"
            with patch("assembly_automation.stepparser.processor.load_step", return_value=loaded), \
                 patch("assembly_automation.stepparser.processor.measure_shape") as measure:
                with self.assertRaises(ValueError):
                    StepProcessor().process_step_file(source, output)
                measure.assert_not_called()
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stages"]["validation"], "failed")
            self.assertFalse((output / "bom.json").exists())

    def test_nested_placements_and_repeated_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            document = TDocStd_Document("test")
            tool = XCAFDoc_DocumentTool.ShapeTool(document.Main())
            definition = tool.AddShape(BRepPrimAPI_MakeBox(1, 2, 3).Shape(), False)
            child = tool.AddShape(make_compound([]), True)
            tool.AddComponent(child, definition, translated(5))
            root = tool.AddShape(make_compound([]), True)
            rotation = gp_Trsf()
            rotation.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.pi / 2)
            placement = translated(10).Multiplied(TopLoc_Location(rotation))
            tool.AddComponent(root, child, placement)
            tool.AddComponent(root, definition, translated(30))
            tool.UpdateAssemblies()
            writer = STEPCAFControl_Writer()
            self.assertTrue(writer.Transfer(document, STEPControl_AsIs))
            path = Path(directory) / "nested.STEP"
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            loaded = load_step(path)
            self.assertEqual(len(loaded.definitions), 1)
            self.assertEqual(len(loaded.instances), 2)
            locations = [transform_matrix(i.location) for i in loaded.instances]
            self.assertAlmostEqual(locations[0][0][3], 10)
            self.assertAlmostEqual(locations[0][1][3], 5)
            self.assertAlmostEqual(locations[1][0][3], 30)

    def test_single_solid_contract_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "box.stp"
            writer = STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeBox(10, 20, 30).Shape(), STEPControl_AsIs)
            self.assertEqual(writer.Write(str(source)), IFSelect_RetDone)
            output = Path(directory) / "output"
            settings = StepParserSettings(rendering=RenderingSettings(enabled=False))
            processor = StepProcessor(settings)
            result = processor.process_step_file(source, output)
            self.assertEqual(result["status"], "complete")
            self.assertEqual({p.name for p in output.iterdir()}, {"assembly.json", "bom.json", "manifest.json"})
            bom = json.loads((output / "bom.json").read_text(encoding="utf-8"))
            self.assertEqual(bom["parts"][0]["quantity"], 1)
            self.assertEqual(len(bom["parts"][0]["geometry"]["surface_details"]), 6)
            with self.assertRaises(FileExistsError):
                processor.process_step_file(source, output)


if __name__ == "__main__":
    unittest.main()
