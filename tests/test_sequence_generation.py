from base64 import b64decode
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.sequence_generation import run_sequence_generation
from assembly_automation.workflows.nodes.sequence_generation.validation import validate_sequence

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


class SequenceGenerationTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((workspace / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        self.settings = config["nodes"]["sequence_generation"]
        self.profiles = config["llms"]["profiles"]
        self.bom = {
            "parts": [{"part_id": "part_001", "quantity": 2, "part_analysis": {}}],
            "instances": [{"instance_id": "part_001", "part_id": "part_001"},
                          {"instance_id": "part_001_002", "part_id": "part_001"}],
        }
        self.sequence = {
            "assembly_name": "Fixture",
            "assembly_description": "Two-part fixture.",
            "sequence_rationale": "Place the base, then add its copy.",
            "sequence_notation": "assembly[part_001,part_001_002]",
            "steps": [
                {"step_id": 1, "step_description": "Place the first instance.",
                 "belongs_to": "Main assembly", "base_part": None,
                 "joining_part": "part_001", "joining_process": "Place"},
                {"step_id": 2, "step_description": "Add the second instance.",
                 "belongs_to": "Main assembly", "base_part": "part_001",
                 "joining_part": "part_001_002", "joining_process": "Insert"},
            ],
        }

    def _artifacts(self, root):
        images = root / "images/assembly"
        images.mkdir(parents=True)
        (images / "collage_assembly.png").write_bytes(PNG_1X1)
        return {
            "assembly": {"name": "Fixture", "total_parts": 2, "unique_parts": 1,
                         "geometry": {"size": {"x": 1, "y": 2, "z": 3}}, "hierarchy": []},
            "assembly_overview": {
                "assembly_name_guess": "Fixture",
                "primary_function": "Test function",
                "assembly_description": "Test assembly",
                "partslist": ["part001"],
            },
            "bom_enriched": self.bom,
            "images": root / "images",
        }

    def test_generate_writes_valid_initial_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "sequence/revisions/rev_001/assembly_sequence.json"
            response = run_sequence_generation(
                mode="generate", artifacts=self._artifacts(root), settings=self.settings,
                llm_profiles=self.profiles, output_path=output, llm=_FakeLlm(self.sequence))
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(response["status"], "complete")
        self.assertEqual(response["run_record"]["execution"]["mode"], "generate")
        self.assertEqual(saved["steps"][1]["joining_part"], "part_001_002")

    def test_revise_requires_initial_sequence_and_summarized_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = self._artifacts(Path(directory))
            with self.assertRaisesRegex(ValueError, "initially generated"):
                run_sequence_generation(mode="revise", artifacts=artifacts, settings=self.settings,
                                        llm_profiles=self.profiles, context={"user_feedback_summary": "Reverse it."},
                                        llm=_FakeLlm(self.sequence))
            artifacts["initial_sequence"] = self.sequence
            with self.assertRaisesRegex(ValueError, "summarized user feedback"):
                run_sequence_generation(mode="revise", artifacts=artifacts, settings=self.settings,
                                        llm_profiles=self.profiles, llm=_FakeLlm(self.sequence))

    def test_revise_includes_required_inputs_and_records_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = self._artifacts(root)
            artifacts["initial_sequence"] = self.sequence
            response = run_sequence_generation(
                mode="revise", artifacts=artifacts, settings=self.settings,
                llm_profiles=self.profiles,
                context={"user_feedback_summary": "Keep the first placement and clarify step two."},
                llm=_FakeLlm(self.sequence))
        ids = [item["id"] for item in response["run_record"]["inputs"]]
        self.assertIn("initially_generated_sequence", ids)
        self.assertIn("summarized_user_feedback", ids)
        self.assertEqual(response["run_record"]["execution"]["mode"], "revise")

    def test_validation_rejects_missing_or_repeated_instances(self):
        invalid = {**self.sequence, "steps": [self.sequence["steps"][0]]}
        with self.assertRaisesRegex(ValueError, "part_001_002"):
            validate_sequence(invalid, self.bom)
        repeated = {**self.sequence, "steps": [self.sequence["steps"][0],
                    {**self.sequence["steps"][1], "joining_part": "part_001"}]}
        with self.assertRaisesRegex(ValueError, "more than one step"):
            validate_sequence(repeated, self.bom)


if __name__ == "__main__":
    unittest.main()
