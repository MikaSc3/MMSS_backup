from base64 import b64decode
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.report_rendering import run_report_rendering
from assembly_automation.workflows.nodes.report_rendering.model import load_report
from assembly_automation.workflows.nodes.report_rendering.settings import ReportRenderingSettings

PNG_1X1 = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def report():
    subprocesses = {name: {"score": score, "automation_potential": "Feasible with controls.",
                               "risks": "Alignment requires verification.", "source_ref": f"ref.{name}"}
                    for name, score in zip(("separation", "handling", "positioning", "joining"),
                                           (0.8, 0.7, 0.4, 0.6))}
    return {
        "assembly_overview": {"assembly_name": "Fixture", "assembly_name_guess": "Pin fixture",
                              "assembly_description": "A pin enters a housing.",
                              "primary_function": "Locate the pin.", "total_parts": 2, "unique_parts": 2},
        "executive_summary": [{"summary_id": "S-001", "statement": "Insertion is feasible with alignment controls.",
                               "validation_status": "unreviewed"}],
        "scorecard": {"aggregate": {"mean_total_ffa": 0.625, "mean_separation_score": 0.8,
            "mean_handling_score": 0.7, "mean_positioning_score": 0.4,
            "mean_joining_score": 0.6}, "steps": [], "mapping": {"id": "ffa_scoring_v1"}},
        "key_findings": [{"finding_id": "F-001", "title": "Pin entry", "statement": "Pilot geometry is limited.",
            "severity": "high", "confidence": "high", "step_ids": [1], "part_ids": ["part_002"],
            "subprocesses": ["positioning"], "source_refs": ["assessment.pin"],
            "validation_status": "unreviewed"}],
        "recommendations": [{"recommendation_id": "R-001", "title": "Add pilot", "action": "Add a pin pilot chamfer.",
            "expected_effect": "Reduces edge catching.", "priority": "high", "origin": "source_derived",
            "addresses_findings": ["F-001"], "source_refs": ["assessment.pin"], "assumptions": [],
            "validation_status": "unreviewed"}],
        "steps": [{"step_id": 1, "step_description": "Insert pin", "base_part": "part_001",
            "joining_part": "part_002", "joining_process": "Insert", "total_ffa": 0.625,
            "subprocesses": subprocesses, "image_refs": ["sequence_renderings/collage_step_01.png"]}],
        "parts": [{"part_id": "part_002", "name": "Pin", "quantity": 1,
            "size": {"x": 2, "y": 2, "z": 12}, "volume": 30.0, "surface_area": 80.0,
            "part_identification": "Joins the housing.", "intrinsic_summary": "Rigid cylindrical pin.",
            "geometric_characteristics": "Axisymmetric shaft.", "finding_ids": ["F-001"],
            "recommendation_ids": ["R-001"]}],
        "assumptions_and_unknowns": [{"statement": "Confirm production tolerances.",
                                      "validation_status": "unreviewed"}],
        "provenance": {"source_artifacts": ["ffa_scores"]},
    }


class ReportRenderingTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((root / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        self.settings = config["nodes"]["report_rendering"]

    def test_rejects_invalid_report_links(self):
        invalid = report()
        invalid["recommendations"][0]["addresses_findings"] = ["F-999"]
        with self.assertRaisesRegex(ValueError, "unknown findings"):
            load_report(invalid)

    def test_rejects_unknown_settings(self):
        with self.assertRaisesRegex(ValueError, "Unknown report_rendering"):
            ReportRenderingSettings.from_mapping({"mystery": True})
        with self.assertRaisesRegex(ValueError, r"only \[html\]"):
            ReportRenderingSettings.from_mapping({"formats": ["pdf"]})

    def test_renders_both_profiles_to_self_contained_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preprocessing = root / "images"
            (preprocessing / "assembly").mkdir(parents=True)
            (preprocessing / "parts/part_002").mkdir(parents=True)
            (preprocessing / "assembly/collage_assembly.png").write_bytes(PNG_1X1)
            (preprocessing / "parts/part_002/collage_part_002.png").write_bytes(PNG_1X1)
            sequence = root / "renderings"; sequence.mkdir()
            (sequence / "collage_step_01.png").write_bytes(PNG_1X1)
            response = run_report_rendering(report=report(), output_dir=root / "reports",
                settings=self.settings, image_roots={"preprocessing_images": preprocessing,
                                                     "sequence_renderings": sequence})
            executive_html = Path(response["artifacts"]["executive"]["html"])
            manifest = json.loads(Path(response["manifest"]).read_text(encoding="utf-8"))
            html = executive_html.read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64", html)
            self.assertEqual(manifest["profiles"]["executive"]["steps_rendered"], 0)
            self.assertEqual(manifest["profiles"]["engineering"]["steps_rendered"], 1)
            self.assertNotIn("pdf", response["artifacts"]["executive"])


if __name__ == "__main__":
    unittest.main()
