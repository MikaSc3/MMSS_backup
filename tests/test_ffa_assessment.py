from base64 import b64decode
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.ffa_assessment import run_ffa_assessment
from assembly_automation.workflows.nodes.ffa_assessment.inputs import prepare_ffa_inputs
from assembly_automation.workflows.nodes.ffa_assessment.structured_output import FFAAssessment

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


def assessment_value():
    return {
        "separation": {"nature_of_provision": "in magazine (defined position and orientation)",
                       "nature_of_provision_reasoning": "The pin can be presented in a tray.",
                       "automatable_reasoning": "Defined presentation supports automation.",
                       "evidence": ["The part is rigid and geometrically regular."]},
        "handling": {"part_rigidity": "rigid", "gripping_areas": "pronounced gripping area existing",
                     "orientation_features": "mechanical self-adjustement in gripper possible",
                     "surface_sensibility": "immune", "rigidity_reasoning": "CAD shows a solid pin.",
                     "gripping_reasoning": "The cylindrical body is accessible.",
                     "orientation_reasoning": "The rotationally symmetric body self-aligns.",
                     "surface_reasoning": "No sensitivity is established; this classification is provisional.",
                     "automatable_reasoning": "A standard parallel gripper is plausible.",
                     "evidence": ["Cylindrical joining-part geometry."]},
        "positioning": {"accuracy_of_target_position": "base part position defined / joining point position with tolerance",
                        "positioning_aids": "insertion chamfers", "additional_orientation_by_rotation": "not required",
                        "accessibility_to_joining_position": "visibility given / tool clearances given",
                        "positioning_motion": "linear joining motion", "positioning_tolerances": "+/- 0.x mm",
                        "stability_in_positioned_state": "holding during joining process required",
                        "accuracy_reasoning": "The bore constrains the final axis.",
                        "positioning_aids_reasoning": "The visible lead-in assists entry.",
                        "orientation_reasoning": "The pin is rotationally symmetric.",
                        "accessibility_reasoning": "The collage shows an open axial approach.",
                        "motion_reasoning": "A straight axial insertion is indicated.",
                        "tolerances_reasoning": "Exact drawings are absent; a submillimetre class is the closest option.",
                        "stability_reasoning": "The part needs support before fixing.",
                        "automatable_reasoning": "Standard guided insertion is plausible.",
                        "evidence": ["Contact pair and before/after CAD views."]},
        "joining": {"feeding_of_joining_element": "not necessary",
                    "fixing_of_mounted_part": "automatable with standard solution",
                    "feeding_reasoning": "No auxiliary joining element is specified.",
                    "fixing_reasoning": "The declared insertion can use standard equipment.",
                    "automatable_reasoning": "The motion and access are conventional.",
                    "evidence": ["Sequence declares Insert."]},
        "overall_ffa": [
            {"subprocess": name, "automation_potential": "High: standard equipment is plausible.",
             "risks": "Production specifications remain unverified."}
            for name in ("separation", "handling", "positioning", "joining")],
        "design_drawbacks_base_part": [{"part_id": "part_001", "drawbacks": [
            {"drawback_id": "base_1", "description": "Lead-in geometry is limited.",
             "improvement_measure": "Increase the bore lead-in chamfer."}]}],
        "design_drawbacks_joining_parts": [{"part_id": "part_002", "drawbacks": [
            {"drawback_id": "joining_1", "description": "The gripping length is short.",
             "improvement_measure": "Add a longer accessible gripping land."}]}],
        "design_drawbacks_assembly": [{"drawbacks": [
            {"drawback_id": "assembly_1", "description": "Insertion feedback is unspecified.",
             "improvement_measure": "Add force-displacement monitoring."}]}],
        "additional_information_required": ["Material, tolerances and production delivery method."],
    }


class FFAAssessmentTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        self.settings = config["nodes"]["ffa_assessment"]
        self.profiles = config["llms"]["profiles"]
        self.sequence = {"assembly_name": "Fixture", "steps": [
            {"step_id": 1, "step_description": "Place housing", "belongs_to": "Main",
             "base_part": None, "joining_part": "part_001", "joining_process": "Place"},
            {"step_id": 2, "step_description": "Insert pin", "belongs_to": "Main",
             "base_part": "part_001", "joining_part": "part_002", "joining_process": "Insert"}]}
        self.bom = {"parts": [
            {"part_id": "part_001", "name": "Housing", "geometry": {"size": {"x": 10, "y": 20, "z": 5}}},
            {"part_id": "part_002", "name": "Pin", "geometry": {"size": {"x": 2, "y": 2, "z": 8}}},
        ], "instances": [
            {"instance_id": "part_001", "part_id": "part_001"},
            {"instance_id": "part_002", "part_id": "part_002"}]}
        self.interaction = {"step": {"step_id": 2}, "interaction_analysis": {
            "geometric_interaction": ["The pin enters the housing bore."],
            "evidence_limitations": ["Fit tolerance is unavailable."]}}

    def _artifacts(self, root):
        renderings = root / "renderings"
        renderings.mkdir()
        (renderings / "collage_step_02.png").write_bytes(PNG_1X1)
        (renderings / "step_02_section_xy_before_transp_0_0.png").write_bytes(PNG_1X1)
        images = root / "images/parts/part_002"
        images.mkdir(parents=True)
        (images / "collage_part_002.png").write_bytes(PNG_1X1)
        return {"sequence": self.sequence, "bom_enriched": self.bom,
                "sequence_renderings": renderings, "images": root / "images",
                "interaction_step": self.interaction}

    def test_preserves_scoring_enum_strings(self):
        parsed = FFAAssessment(**assessment_value())
        self.assertEqual(parsed.positioning.positioning_tolerances.value, "+/- 0.x mm")
        self.assertEqual(parsed.handling.orientation_features.value,
                         "mechanical self-adjustement in gripper possible")

    def test_rejects_duplicate_overall_subprocess(self):
        value = assessment_value()
        value["overall_ffa"][-1]["subprocess"] = "positioning"
        with self.assertRaisesRegex(ValueError, "each subprocess"):
            FFAAssessment(**value)

    def test_interaction_artifact_must_match_step(self):
        with self.assertRaisesRegex(ValueError, "belongs to step 1"):
            prepare_ffa_inputs({"sequence": self.sequence, "bom_enriched": self.bom,
                                "interaction_step": {"step": {"step_id": 1},
                                "interaction_analysis": {}}}, 2)

    def test_node_uses_interaction_and_both_collages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "ffa/steps/step_002.json"
            response = run_ffa_assessment(step_id=2, artifacts=self._artifacts(root),
                settings=self.settings, llm_profiles=self.profiles,
                output_path=output, llm=_FakeLlm(assessment_value()))
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(response["status"], "complete")
        self.assertEqual(saved["step"]["step_id"], 2)
        self.assertEqual(saved["ffa_assessment"]["joining"]["feeding_of_joining_element"], "not necessary")
        self.assertIn("sequence_renderings/collage_step_02.png", response["run_record"]["images_used"])
        self.assertIn("images/parts/part_002/collage_part_002.png", response["run_record"]["images_used"])
        input_ids = {item["id"] for item in response["run_record"]["inputs"]}
        self.assertIn("interaction_analysis", input_ids)


if __name__ == "__main__":
    unittest.main()
