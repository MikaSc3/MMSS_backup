import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.bom_merge import run_bom_merge


class BomMergeTests(unittest.TestCase):
    def setUp(self):
        self.bom = {
            "units": {"length": "mm"},
            "parts": [
                {"part_id": "part_001", "name": "ring", "quantity": 2, "geometry": {"volume": 4}},
                {"part_id": "part_002", "name": "shaft", "quantity": 1, "geometry": {"volume": 9}},
            ],
            "instances": [
                {"instance_id": "part_001", "part_id": "part_001", "center_of_mass": [0, 0, 0]},
                {"instance_id": "part_001_002", "part_id": "part_001", "center_of_mass": [10, 0, 0]},
                {"instance_id": "part_002", "part_id": "part_002", "center_of_mass": [20, 0, 0]},
            ],
        }

    def test_enriches_definitions_once_and_preserves_instances(self):
        analyses = {
            "part_001": {"part_identification": "Retains", "part_name_guess": "Retaining ring"},
            "part_002": {"part_identification": "Transfers load", "part_name_guess": "Shaft"},
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bom_enriched.json"
            response = run_bom_merge(bom=self.bom, part_analyses=analyses, output_path=output)
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(response["status"], "complete")
        self.assertEqual(saved["parts"][0]["part_analysis"]["part_name_guess"], "Retaining ring")
        self.assertEqual(saved["parts"][0]["quantity"], 2)
        self.assertEqual(saved["instances"], self.bom["instances"])
        self.assertEqual(len(saved["parts"]), 2)

    def test_requires_complete_analysis_set_by_default(self):
        with self.assertRaisesRegex(ValueError, "part_002"):
            run_bom_merge(bom=self.bom,
                          part_analyses={"part_001": {"part_identification": "Retains", "part_name_guess": "Ring"}})

    def test_can_return_partial_bom_explicitly(self):
        response = run_bom_merge(
            bom=self.bom,
            part_analyses={"part_001": {"part_identification": "Retains", "part_name_guess": "Ring"}},
            settings={"require_all_parts": False},
        )
        self.assertEqual(response["status"], "partial")
        self.assertEqual(response["missing_part_ids"], ["part_002"])
        self.assertNotIn("part_analysis", response["result"]["parts"][1])


if __name__ == "__main__":
    unittest.main()
