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
        with self.assertRaises(ValueError):
            get_view("legacy_iso4")
        settings = StepParserSettings.from_mapping({"rendering": {"assembly_views": [], "part_views": []}})
        self.assertFalse(settings.rendering.part_views)


class GeometryTests(unittest.TestCase):
    def test_box_measurements_and_embedded_surfaces(self):
        shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        self.assertTrue(validate_shape(shape)["is_valid"])
        geometry = measure_shape(shape, detailed=True, include_oriented_box=True)
        self.assertAlmostEqual(geometry["volume"], 6000)
        self.assertAlmostEqual(geometry["surface_area"], 2200)
        self.assertNotIn("topology", geometry)
        self.assertEqual(len(geometry["surface_details"]), 6)
        for actual, expected in zip(sorted(geometry["oriented_bounding_box"]["dimensions"]), [10, 20, 30]):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_null_shape_is_invalid(self):
        self.assertFalse(validate_shape(TopoDS_Shape())["is_valid"])

    def test_default_geometry_skips_face_breakdown(self):
        shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        with patch("assembly_automation.stepparser.analysis.geometry.surface_details") as details:
            geometry = measure_shape(shape)
        details.assert_not_called()
        self.assertNotIn("surface_details", geometry)
        self.assertNotIn("surface_type_counts", geometry)
        self.assertEqual(geometry["surface_details_status"], "disabled")
        self.assertAlmostEqual(geometry["volume"], 6000)
        self.assertAlmostEqual(geometry["surface_area"], 2200)

    def test_no_topology_counts_or_default_oriented_box(self):
        shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        with patch("assembly_automation.stepparser.analysis.geometry.oriented_box") as obb, \
             patch("assembly_automation.stepparser.analysis.geometry.bounding_box") as aabb:
            geometry = measure_shape(shape, include_size=False)
        obb.assert_not_called()
        aabb.assert_not_called()
        self.assertNotIn("bounding_box", geometry)
        self.assertEqual(geometry["bounding_box_status"], "disabled")
        self.assertNotIn("topology", geometry)
        self.assertNotIn("oriented_bounding_box", geometry)
        self.assertEqual(geometry["oriented_bounding_box_status"], "disabled")
        self.assertAlmostEqual(geometry["volume"], 6000)
        from OCC.Core.TopAbs import TopAbs_FACE
        from OCC.Core.TopExp import TopExp_Explorer
        face = TopExp_Explorer(shape, TopAbs_FACE).Current()
        geometry = measure_shape(face)
        self.assertIsNone(geometry["volume"])
        self.assertEqual(geometry["volume_status"], "not_a_solid")

    def test_axis_aligned_box_can_be_explicitly_enabled(self):
        geometry = measure_shape(BRepPrimAPI_MakeBox(10, 20, 30).Shape(), include_axis_aligned_box=True)
        self.assertEqual(geometry["bounding_box_status"], "complete")
        for actual, expected in zip(geometry["bounding_box"]["dimensions"], (10, 20, 30)):
            self.assertAlmostEqual(actual, expected)

    def test_size_contains_xyz_dimensions_without_exported_box(self):
        geometry = measure_shape(BRepPrimAPI_MakeBox(10, 20, 30).Shape())
        self.assertNotIn("bounding_box", geometry)
        for name, expected in zip(("x", "y", "z"), (10, 20, 30)):
            self.assertAlmostEqual(geometry["size"][name], expected)

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

    def test_nearby_filter_preserves_maps_and_threshold_boundary(self):
        base = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
        parts = [instance(str(offset), base.Moved(translated(offset)))
                 for offset in (0, 10, 12, 13, 100)]
        exact = compute_spatial_relations(parts, SpatialSettings(multithread=False))
        nearby = compute_spatial_relations(parts, SpatialSettings(distance_mode="nearby_pairs"))
        self.assertEqual(exact["contact_map"], nearby["contact_map"])
        self.assertEqual(exact["close_map"], nearby["close_map"])
        self.assertEqual(nearby["statistics"]["bbox_rejections"], 4)
        self.assertEqual(nearby["statistics"]["exact_calculations"], 6)
        boundary = next(pair for pair in nearby["pairs"] if pair["part_a"] == "0" and pair["part_b"] == "13")
        self.assertEqual(boundary["distance_kind"], "exact")
        self.assertAlmostEqual(boundary["distance_mm"], 3)
        far = next(pair for pair in nearby["pairs"] if pair["part_b"] == "100")
        self.assertIsNone(far["distance_mm"])
        self.assertEqual(far["classification"], "separated")
        self.assertEqual(far["distance_kind"], "lower_bound")
        self.assertGreater(far["distance_lower_bound_mm"], 3)

    def test_parallel_mode_is_set_before_distance_perform(self):
        from unittest.mock import Mock
        base = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
        tool = Mock()
        tool.IsDone.return_value = True
        tool.NbSolution.return_value = 1
        tool.Value.return_value = 0
        tool.PointOnShape1.return_value = gp_Pnt(0, 0, 0)
        tool.PointOnShape2.return_value = gp_Pnt(0, 0, 0)
        tool.InnerSolution.return_value = False
        with patch("OCC.Core.BRepExtrema.BRepExtrema_DistShapeShape", return_value=tool) as factory:
            result = compute_spatial_relations([instance("a", base), instance("b", base)], SpatialSettings())
        factory.assert_called_once_with()
        self.assertEqual(result["status"], "complete")
        self.assertEqual([call[0] for call in tool.mock_calls[:4]],
                         ["SetMultiThread", "LoadS1", "LoadS2", "Perform"])
        tool.SetMultiThread.assert_called_once_with(True)

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
            geometry = measure_shape(loaded.definitions[0].shape, include_axis_aligned_box=True)
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
            self.assertEqual(loaded.hierarchy, [])
            self.assertTrue(all(item.assembly_id is None for item in loaded.instances))

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
            self.assertEqual(len(loaded.hierarchy), 2)
            self.assertEqual(loaded.hierarchy[0]["assembly_id"], "assy_001")
            self.assertIsNone(loaded.hierarchy[0]["parent_id"])
            self.assertEqual(loaded.hierarchy[0]["assembly_ids"], ["assy_002"])
            self.assertEqual(loaded.hierarchy[1]["parent_id"], "assy_001")
            self.assertEqual([item.assembly_id for item in loaded.instances], ["assy_002", "assy_001"])
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
            self.assertEqual({p.name for p in output.iterdir()},
                             {"assembly.json", "bom.json", "spatial_relations.json",
                              "interlocking.json", "manifest.json"})
            assembly = json.loads((output / "assembly.json").read_text(encoding="utf-8"))
            self.assertNotIn("schema_version", assembly)
            self.assertNotIn("validity", assembly)
            self.assertNotIn("normalization", assembly["units"])
            self.assertFalse(any(key.endswith("_status") or key == "status" for key in assembly["geometry"]))
            self.assertIsNone(assembly["assembly_id"])
            self.assertEqual(assembly["hierarchy"], [])
            self.assertEqual(assembly["root_instance_ids"], ["part_001"])
            self.assertNotIn("spatial_relations", assembly)
            self.assertEqual(assembly["spatial_relations_file"], "spatial_relations.json")
            relations = json.loads((output / assembly["spatial_relations_file"]).read_text(encoding="utf-8"))
            self.assertEqual(relations["assembly_id"], assembly["assembly_id"])
            self.assertEqual(relations["contact_map"], {"part_001": []})
            self.assertIn("spatial_relations.json", result["artifacts"])
            self.assertIn("interlocking.json", result["artifacts"])
            interlocking = json.loads((output / "interlocking.json").read_text(encoding="utf-8"))
            self.assertEqual(interlocking["parts"][0]["free_directions"],
                             ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
            self.assertEqual(result["assembly_validity"]["status"], "valid")
            bom = json.loads((output / "bom.json").read_text(encoding="utf-8"))
            self.assertEqual(bom["parts"][0]["quantity"], 1)
            self.assertNotIn("surface_details", bom["parts"][0]["geometry"])
            self.assertNotIn("validity", bom["parts"][0])
            def assert_no_status(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        self.assertFalse(key == "status" or key.endswith("_status"), key)
                        assert_no_status(item)
                elif isinstance(value, list):
                    for item in value:
                        assert_no_status(item)
            assert_no_status(bom)
            self.assertAlmostEqual(bom["parts"][0]["geometry"]["volume"], 6000)
            self.assertEqual(bom["parts"][0]["geometry"]["size"], {"x": 10, "y": 20, "z": 30})
            self.assertEqual(result["part_geometry_status"][bom["parts"][0]["part_id"]]["surface_details_status"], "disabled")
            with self.assertRaises(FileExistsError):
                processor.process_step_file(source, output)


if __name__ == "__main__":
    unittest.main()
