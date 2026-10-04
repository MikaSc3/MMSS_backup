from base64 import b64decode
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.interaction_analysis import run_interaction_analysis
from assembly_automation.workflows.nodes.interaction_analysis.inputs import prepare_step_inputs

PNG_1X1 = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class _StructuredCall:
    def __init__(self, schema, value):
        self.schema = schema
        self.value = value

    def invoke(self, messages):
        return {"parsed": self.schema(**self.value), "raw": None}


class _FakeLlm:
    def __init__(self, value):
        self.value = value

    def with_structured_output(self, schema, include_raw=True):
        return _StructuredCall(schema, self.value)


class InteractionAnalysisTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        self.settings = config["nodes"]["interaction_analysis"]
        self.profiles = config["llms"]["profiles"]
        self.sequence = {"assembly_name": "Fixture", "steps": [
            {"step_id": 1, "step_description": "Place housing", "belongs_to": "Main",
             "base_part": None, "joining_part": "part_001", "joining_process": "Place"},
            {"step_id": 2, "step_description": "Insert second pin", "belongs_to": "Main",
             "base_part": "part_001", "joining_part": "part_002_copy1", "joining_process": "Insert"},
        ]}
        self.bom = {
            "parts": [
                {"part_id": "part_001", "name": "Housing", "geometry": {"size": {"x": 10, "y": 20, "z": 5}}},
                {"part_id": "part_002", "name": "Pin", "geometry": {"size": {"x": 2, "y": 2, "z": 8}}},
            ],
            "instances": [
                {"instance_id": "part_001", "part_id": "part_001", "center_of_mass": [0, 0, 0]},
                {"instance_id": "part_002_copy1", "part_id": "part_002", "center_of_mass": [1, 0, 0]},
                {"instance_id": "part_999", "part_id": "part_002", "center_of_mass": [50, 0, 0]},
            ],
        }
        self.spatial = {"unit": "mm", "pairs": [
            {"part_a": "part_001", "part_b": "part_002_copy1", "distance_mm": 0, "classification": "contact_or_overlap"},
            {"part_a": "part_001", "part_b": "part_999", "distance_mm": 40, "classification": "separated"},
        ]}
        self.interlocking = {"method": "proxy", "parts": [
            {"instance_id": "part_002_copy1", "free_directions": ["+Z"]},
            {"instance_id": "part_999", "free_directions": ["-Z"]},
        ], "blocker_edges": [
            {"blocker": "part_001", "blocked_part": "part_002_copy1", "directions": ["-Z"]},
            {"blocker": "part_999", "blocked_part": "part_002_copy1", "directions": ["+X"]},
        ], "limitations": ["proxy only"]}
        self.analysis = {name: [f"Evidence for {name}."] for name in (
            "geometric_interaction", "positioning_possibilities", "accuracy_of_target_position",
            "positioning_aids", "additional_orientation_by_rotation", "joining_tolerances",
            "accessibility_to_joining_position", "joining_motion", "stability_in_positioned_state",
            "feeding_of_joining_element", "fixing_of_mounted_part", "evidence_limitations")}

    def _artifacts(self, root):
        renderings = root / "renderings"
        renderings.mkdir()
        (renderings / "collage_step_02.png").write_bytes(PNG_1X1)
        (renderings / "step_02_section_xy_before_transp_0_0.png").write_bytes(PNG_1X1)
        return {"sequence": self.sequence, "bom_enriched": self.bom,
                "spatial_relations": self.spatial, "interlocking": self.interlocking,
                "sequence_renderings": renderings}

    def test_preparation_resolves_copy_and_filters_operation_evidence(self):
        prepared, context = prepare_step_inputs({"sequence": self.sequence,
            "bom_enriched": self.bom, "spatial_relations": self.spatial,
            "interlocking": self.interlocking}, 2)
        self.assertEqual(prepared["joining_parts"][0]["part"]["part_id"], "part_002")
        self.assertEqual(context["joining_part_id"], "part_002")
        self.assertEqual(len(prepared["step_spatial_relations"]["relevant_pairs"]), 1)
        self.assertEqual(len(prepared["step_interlocking"]["relevant_blocker_edges"]), 1)

    def test_first_step_has_explicit_initial_placement_base(self):
        prepared, context = prepare_step_inputs({"sequence": self.sequence,
            "bom_enriched": self.bom}, 1)
        self.assertEqual(prepared["base_part"]["status"], "initial_placement")
        self.assertEqual(context["base_instance_id"], "none (initial placement)")

    def test_single_step_node_uses_collage_and_writes_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "interaction/steps/step_002.json"
            response = run_interaction_analysis(
                step_id=2, artifacts=self._artifacts(root), settings=self.settings,
                llm_profiles=self.profiles, output_path=output, llm=_FakeLlm(self.analysis))
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(response["status"], "complete")
        self.assertEqual(saved["step"]["step_id"], 2)
        self.assertEqual(saved["interaction_analysis"]["joining_motion"], ["Evidence for joining_motion."])
        self.assertIn("sequence_renderings/collage_step_02.png", response["run_record"]["images_used"])
        self.assertIn("sequence_renderings/step_02_section_xy_before_transp_0_0.png", response["run_record"]["images_used"])

    def test_fanout_settings_are_validated_but_not_executed_by_node(self):
        invalid = {**self.settings, "fanout": {"parallel": True, "max_workers": 0}}
        with self.assertRaisesRegex(ValueError, "positive integer"):
            run_interaction_analysis(step_id=1, artifacts={}, settings=invalid,
                                     llm_profiles=self.profiles, llm=_FakeLlm(self.analysis))


if __name__ == "__main__":
    unittest.main()
