import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.report_synthesis import run_report_synthesis
from assembly_automation.workflows.nodes.report_synthesis.report_data import prepare_report_data


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


def artifacts():
    step = {"step_id": 1, "step_description": "Insert pin", "base_part": "part_001",
            "joining_part": "part_002", "joining_process": "Insert"}
    assessment = {
        "overall_ffa": [
            {"subprocess": name, "automation_potential": "Moderate potential.",
             "risks": "Alignment remains sensitive."}
            for name in ("separation", "handling", "positioning", "joining")],
        "design_drawbacks_base_part": [{"part_id": "part_001", "drawbacks": [{
            "drawback_id": "base_1", "description": "The bore has little lead-in.",
            "improvement_measure": "Increase the bore lead-in chamfer."}]}],
        "design_drawbacks_joining_parts": [{"part_id": "part_002", "drawbacks": [{
            "drawback_id": "pin_1", "description": "The pin has no pilot nose.",
            "improvement_measure": "Add a pilot chamfer."}]}],
        "design_drawbacks_assembly": [{"drawbacks": [{
            "drawback_id": "assy_1", "description": "Insertion feedback is unspecified.",
            "improvement_measure": "Monitor force and displacement."}]}],
        "additional_information_required": ["Confirm bore and pin tolerances."],
    }
    details = {name: {} for name in ("separation", "handling", "positioning", "joining")}
    return {
        "assembly_overview": {"assembly_name": "Fixture", "total_parts": 2, "unique_parts": 2,
            "assembly_name_guess": "Pin fixture", "assembly_description": "A pin enters a housing.",
            "primary_function": "Locate the pin."},
        "bom_enriched": {"parts": [
            {"part_id": "part_001", "geometry": {"size": {"x": 10, "y": 8, "z": 5}},
             "part_analysis": {"part_name_guess": "Housing", "part_color": "blue",
                "part_identification": "Locates the pin.",
                "intrinsic_summary": "Rigid prismatic housing.",
                "geometric_characteristics": "Prismatic body with a bore."}},
            {"part_id": "part_002", "geometry": {"size": {"x": 2, "y": 2, "z": 12}},
             "part_analysis": {"part_name_guess": "Pin", "part_color": "red",
                "part_identification": "Joins the housing.",
                "intrinsic_summary": "Rigid cylindrical pin.",
                "geometric_characteristics": "Axisymmetric shaft."}}],
            "instances": [{"instance_id": "part_001", "part_id": "part_001"},
                          {"instance_id": "part_002", "part_id": "part_002"}]},
        "sequence": {"assembly_name": "Fixture", "steps": [step]},
        "ffa_assessments": [{"step": step, "ffa_assessment": assessment}],
        "ffa_scores": {"mapping": {"id": "ffa_scoring_v1", "sha256": "abc"},
            "steps": [{"step_id": 1, "subprocess_scores": {
                "separation": 0.8, "handling": 0.7, "positioning": 0.4, "joining": 0.6},
                "total_ffa": 0.625, "coverage": {"scored_criteria": 14}, "details": details}],
            "aggregate": {"mean_total_ffa": 0.625, "std_total_ffa": 0.0, "num_steps": 1}},
    }


def insights(source_ref="ffa_assessment.step_001.drawbacks.joining_part.part_002.pin_1"):
    return {
        "executive_summary": ["Pin insertion is automatable but alignment needs improvement."],
        "findings": [{"finding_key": "pin_entry", "scope": "part", "title": "Pin entry",
            "statement": "The pin lacks pilot geometry for robust bore entry.", "severity": "high",
            "confidence": "high", "step_ids": [1], "part_ids": ["part_002"],
            "subprocesses": ["positioning"], "source_refs": [source_ref]}],
        "recommendations": [{"title": "Add pilot chamfer", "action": "Add a pilot chamfer to the pin end.",
            "expected_effect": "Reduces catching during bore entry.", "priority": "high",
            "origin": "source_derived", "addresses_findings": ["pin_entry"],
            "source_refs": [source_ref], "assumptions": []}],
    }


class ReportSynthesisTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        config = yaml.safe_load((root / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
        self.settings = config["nodes"]["report_synthesis"]
        self.profiles = config["llms"]["profiles"]

    def test_prepares_compact_traceable_evidence(self):
        prepared = prepare_report_data(artifacts())
        self.assertEqual(prepared["assembly_overview"]["unique_parts"], 2)
        self.assertEqual(len(prepared["drawback_candidates"]), 3)
        self.assertEqual(prepared["risk_candidates"][0]["source_ref"],
                         "ffa_assessment.step_001.overall_ffa.separation")
        self.assertEqual(prepared["parts"][1]["quantity"], 1)

    def test_compiles_authoritative_report_and_writes_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports/report.json"
            response = run_report_synthesis(
                artifacts=artifacts(), settings=self.settings, llm_profiles=self.profiles,
                context={"user_context": "Focus on robust insertion."}, output_path=output,
                llm=_FakeLlm(insights()))
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(response["status"], "complete")
        self.assertEqual(saved["scorecard"]["aggregate"]["mean_total_ffa"], 0.625)
        self.assertEqual(saved["key_findings"][0]["finding_id"], "F-001")
        self.assertEqual(saved["recommendations"][0]["addresses_findings"], ["F-001"])
        self.assertEqual(saved["parts"][1]["finding_ids"], ["F-001"])
        self.assertEqual(saved["steps"][0]["subprocesses"]["positioning"]["score"], 0.4)
        self.assertEqual(saved["key_findings"][0]["validation_status"], "unreviewed")
        self.assertFalse(saved["key_findings"][0]["statement"].endswith("[]"))

    def test_rejects_fabricated_source_reference(self):
        with self.assertRaisesRegex(ValueError, "unknown sources"):
            run_report_synthesis(artifacts=artifacts(), settings=self.settings,
                llm_profiles=self.profiles, llm=_FakeLlm(insights("invented.reference")))

    def test_canonicalizes_instance_ids_in_report_findings(self):
        values = artifacts()
        values["bom_enriched"]["instances"].append(
            {"instance_id": "part_002_copy1", "part_id": "part_002"})
        values["sequence"]["steps"][0]["joining_part"] = "part_002_copy1"
        values["ffa_assessments"][0]["step"]["joining_part"] = "part_002_copy1"
        generated = insights()
        generated["findings"][0]["part_ids"] = ["part_002", "part_002_copy1"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            run_report_synthesis(
                artifacts=values, settings=self.settings, llm_profiles=self.profiles,
                output_path=output, llm=_FakeLlm(generated))
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["key_findings"][0]["part_ids"], ["part_002"])
        self.assertEqual(report["parts"][1]["finding_ids"], ["F-001"])


if __name__ == "__main__":
    unittest.main()
