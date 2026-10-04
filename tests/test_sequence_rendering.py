import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.sequence_rendering.inputs import build_step_states, unwrap_sequence
from assembly_automation.workflows.nodes.sequence_rendering.collage import (
    create_sequence_overview,
    create_step_collages,
)
from assembly_automation.workflows.nodes.sequence_rendering.node import run_sequence_rendering
from assembly_automation.workflows.nodes.sequence_rendering.renderer import SequenceRenderer
from assembly_automation.workflows.nodes.sequence_rendering.settings import SequenceCollageSettings, SequenceRenderingSettings


class SequenceRenderingTests(unittest.TestCase):
    def setUp(self):
        self.bom = {
            "parts": [{"part_id": "part_001", "color": [1, 2, 3]},
                      {"part_id": "part_002", "color": [4, 5, 6]}],
            "instances": [{"instance_id": "part_001", "part_id": "part_001", "color": [1, 2, 3]},
                          {"instance_id": "part_002", "part_id": "part_002", "color": [4, 5, 6]}],
        }
        self.sequence = {
            "assembly_name": "Fixture", "assembly_description": "Fixture", "sequence_rationale": "Stable",
            "sequence_notation": "A+B", "steps": [
                {"step_id": 1, "step_description": "Place base", "belongs_to": "Main",
                 "base_part": None, "joining_part": "part_001", "joining_process": "Place"},
                {"step_id": 2, "step_description": "Add pin", "belongs_to": "Main",
                 "base_part": "part_001", "joining_part": "part_002", "joining_process": "Insert"},
            ]}

    def test_builds_global_incremental_states(self):
        states = build_step_states(self.sequence, {"part_001", "part_002"})
        self.assertEqual(states[0]["before"], [])
        self.assertEqual(states[0]["after"], ["part_001"])
        self.assertEqual(states[1]["before"], ["part_001"])
        self.assertEqual(states[1]["after"], ["part_001", "part_002"])

    def test_accepts_flat_sequence_product(self):
        self.assertEqual(unwrap_sequence(self.sequence), self.sequence)

    def test_section_scene_omits_shapes_removed_completely_by_cut(self):
        renderer = object.__new__(SequenceRenderer)
        renderer.instances = {
            "removed": Mock(color=[1, 2, 3]),
            "remaining": Mock(color=[4, 5, 6]),
        }
        remaining_shape = object()
        renderer._cut_shape = Mock(side_effect=[None, remaining_shape])

        objects = renderer._section_objects(["removed", "remaining"], "yz", 10.0)

        self.assertEqual(objects, [(remaining_shape, [4, 5, 6])])

    def test_settings_reject_unknown_views_and_keys(self):
        with self.assertRaisesRegex(ValueError, "Unknown view"):
            SequenceRenderingSettings(views=("diagonal_9",))
        with self.assertRaisesRegex(ValueError, "Unknown sequence_rendering"):
            SequenceRenderingSettings.from_mapping({"mystery": True})

    def test_production_sequence_config_owns_overview_settings(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))

        settings = SequenceRenderingSettings.from_mapping(config["nodes"]["sequence_rendering"])

        self.assertTrue(settings.collage.overview_enabled)
        self.assertEqual(settings.collage.overview_columns, 3)

    def test_collage_keeps_anchor_highlight_and_exploded_order(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            specifications = [
                ("iso1.png", "assembled", "iso1", "after"),
                ("iso2.png", "assembled", "iso2", "after"),
                ("xy.png", "section", "top", "after"),
                ("xz.png", "section", "front", "after"),
                ("highlight.png", "joining_highlight", "iso1", "after"),
                ("exploded.png", "exploded", "iso1", "after"),
            ]
            for index, (name, category, view, state) in enumerate(specifications):
                image = Image.new("RGB", (160, 100), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((10 + index * 3, 10, 70 + index * 8, 80),
                               fill=(30 + index * 25, 70, 180 - index * 15), outline="black")
                draw.line((5, 90 - index * 5, 150, 20 + index * 3), fill="black", width=2)
                image.save(root / name)
                records.append({"path": name, "step_id": 1, "category": category,
                                "view": view, "state": state, "transparency": 0.0})
            result = create_step_collages(records, root, SequenceCollageSettings())[0]
            selected = result["selected_images"]
            self.assertEqual(selected[0], "iso1.png")
            self.assertEqual(selected[-2:], ["highlight.png", "exploded.png"])
            self.assertEqual(len(selected), 5)
            self.assertTrue((root / "collage_step_01.png").exists())

    def test_sequence_overview_orders_one_assembled_iso_view_per_step(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for step_id, color in ((1, "red"), (2, "green"), (3, "blue")):
                name = f"step_{step_id:02d}_assembled_iso1.png"
                Image.new("RGB", (240, 140), color).save(root / name)
                records.append({"path": name, "step_id": step_id,
                                "category": "assembled", "view": "iso1",
                                "state": "after", "transparency": 0.0})
            result = create_sequence_overview(
                records, self.sequence | {"steps": [
                    *self.sequence["steps"],
                    {"step_id": 3, "step_description": "Secure ring",
                     "belongs_to": "Main", "base_part": "part_002",
                     "joining_part": "part_003", "joining_process": "Clip"},
                ]}, root, SequenceCollageSettings(
                    overview_columns=3, overview_tile_size=(260, 150)))

            self.assertEqual(result["step_ids"], [1, 2, 3])
            self.assertEqual(result["category"], "sequence_overview")
            self.assertEqual(result["selected_images"],
                             [record["path"] for record in records])
            with Image.open(root / "collage_sequence.png") as overview:
                self.assertGreater(overview.width, 500)
                self.assertGreater(overview.height, 300)

    @patch("assembly_automation.workflows.nodes.sequence_rendering.node.SequenceRenderer")
    @patch("assembly_automation.workflows.nodes.sequence_rendering.node.load_step")
    def test_node_uses_explicit_inputs_and_writes_summary(self, load_step_mock, renderer_class):
        instances = [Mock(instance_id="part_001", part_id="part_001", color=[1, 2, 3]),
                     Mock(instance_id="part_002", part_id="part_002", color=[4, 5, 6])]
        definitions = [Mock(part_id="part_001", color=[1, 2, 3]),
                       Mock(part_id="part_002", color=[4, 5, 6])]
        load_step_mock.return_value = Mock(instances=instances, definitions=definitions)
        renderer = renderer_class.return_value
        renderer.render.return_value = [{"path": "step_01_iso1_transp_0_0.png"}]
        renderer.section_fallbacks = []
        renderer.section_empty_cuts = []
        renderer.section_cache_entries = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step = root / "fixture.step"
            step.write_bytes(b"STEP")
            output = root / "renderings"
            result = run_sequence_rendering(step_file=step, sequence=self.sequence,
                                            bom=self.bom, output_dir=output,
                                            settings={"section_planes": [], "collage": {"enabled": False}})
            self.assertTrue((output / "rendering_summary.json").exists())
        self.assertEqual(result["rendered_steps"], 2)
        renderer.render.assert_called_once()


if __name__ == "__main__":
    unittest.main()
