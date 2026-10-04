import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.workflows.nodes.ffa_scoring import run_ffa_scoring
from assembly_automation.workflows.nodes.ffa_scoring.mapping import FIELD_ENUMS, load_mapping


def assessment(step_id, *, rigidity="rigid"):
    return {"step": {"step_id": step_id, "step_description": f"Step {step_id}"},
            "ffa_assessment": {
        "separation": {"nature_of_provision": "in magazine (defined position and orientation)"},
        "handling": {"part_rigidity": rigidity,
                     "gripping_areas": "pronounced gripping area existing",
                     "orientation_features": "mechanical self-adjustement in gripper possible",
                     "surface_sensibility": "immune"},
        "positioning": {"accuracy_of_target_position": "base part position defined / joining point position defined",
                        "positioning_aids": "insertion chamfers and stopping edge",
                        "additional_orientation_by_rotation": "not required",
                        "accessibility_to_joining_position": "visibility given / tool clearances given",
                        "positioning_motion": "linear joining motion",
                        "positioning_tolerances": "+/- x mm",
                        "stability_in_positioned_state": "stable, self-holding"},
        "joining": {"feeding_of_joining_element": "not necessary",
                    "fixing_of_mounted_part": "automatable with standard solution"}}}


class FFAScoringTests(unittest.TestCase):
    def test_mapping_exactly_matches_all_structured_enums(self):
        mapping, provenance = load_mapping()
        self.assertEqual(provenance["id"], "ffa_scoring_v1")
        self.assertEqual(set(mapping["criteria"]), set(FIELD_ENUMS))
        for field, enum in FIELD_ENUMS.items():
            self.assertEqual(set(mapping["criteria"][field]["scores"]),
                             {item.value for item in enum})
            self.assertEqual(set(mapping["criteria"][field]["scores_by_id"]),
                             set(range(1, len(enum) + 1)))

    def test_best_classifications_score_one(self):
        result = run_ffa_scoring(assessments=[assessment(1)])
        step = result["result"]["steps"][0]
        self.assertEqual(step["total_ffa"], 1.0)
        self.assertEqual(step["coverage"]["scored_criteria"], 14)
        self.assertEqual(result["result"]["aggregate"]["mean_total_ffa"], 1.0)

    def test_aggregate_uses_population_standard_deviation(self):
        result = run_ffa_scoring(assessments=[assessment(2, rigidity="flexible"), assessment(1)])
        self.assertEqual([item["step_id"] for item in result["result"]["steps"]], [1, 2])
        scores = [item["total_ffa"] for item in result["result"]["steps"]]
        expected = round(abs(scores[0] - scores[1]) / 2, 4)
        self.assertEqual(result["result"]["aggregate"]["std_total_ffa"], expected)

    def test_strict_mode_rejects_unknown_or_missing_classification(self):
        invalid = assessment(1)
        invalid["ffa_assessment"]["handling"]["part_rigidity"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unscorable"):
            run_ffa_scoring(assessments=invalid)

    def test_writes_mapping_provenance_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scores/ffa_scores.json"
            response = run_ffa_scoring(assessments=assessment(1), output_path=output,
                                       settings={"mapping": "ffa_scoring_v1", "strict": True})
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(response["status"], "complete")
        self.assertEqual(saved["mapping"]["status"], "authoritative_historical_baseline")
        self.assertEqual(len(saved["mapping"]["sha256"]), 64)

    def test_integer_annotation_ids_are_supported(self):
        integer_assessment = assessment(1)
        for section in integer_assessment["ffa_assessment"].values():
            for field in section:
                section[field] = 1
        result = run_ffa_scoring(assessments=integer_assessment)
        self.assertEqual(result["result"]["steps"][0]["total_ffa"], 1.0)

    def test_historical_mixed_assessment_scores(self):
        integer_assessment = assessment(1)
        option_ids = {
            "nature_of_provision": 2, "part_rigidity": 3, "gripping_areas": 2,
            "orientation_features": 4, "surface_sensibility": 2,
            "accuracy_of_target_position": 4, "positioning_aids": 3,
            "additional_orientation_by_rotation": 3,
            "accessibility_to_joining_position": 4, "positioning_motion": 2,
            "positioning_tolerances": 3, "stability_in_positioned_state": 2,
            "feeding_of_joining_element": 4, "fixing_of_mounted_part": 2,
        }
        for section in integer_assessment["ffa_assessment"].values():
            for field in section:
                section[field] = option_ids[field]
        step = run_ffa_scoring(assessments=integer_assessment)["result"]["steps"][0]
        self.assertEqual(step["subprocess_scores"], {
            "separation": 0.5, "handling": 0.12,
            "positioning": 0.15, "joining": 0.3,
        })
        self.assertEqual(step["total_ffa"], 0.2675)

    def test_numerical_parity_with_legacy_scorer_when_source_is_available(self):
        legacy_mapping = Path(__file__).resolve().parents[1] / (
            "data/ground_truth/mapping/ffa_scoring_mapping.json")
        if not legacy_mapping.exists():
            self.skipTest("ignored legacy source mapping is unavailable")
        from research.evaluation import ffa_scoring as legacy

        legacy._MAPPING = None
        flat = {}
        nested = assessment(1)
        for section in nested["ffa_assessment"].values():
            flat.update(section)
        old = legacy.compute_step_ffa_score(flat)
        new = run_ffa_scoring(assessments=nested)["result"]["steps"][0]
        for subprocess in ("separation", "handling", "positioning", "joining"):
            self.assertEqual(new["subprocess_scores"][subprocess],
                             old[f"{subprocess}_score"])
        self.assertEqual(new["total_ffa"], old["total_ffa"])


if __name__ == "__main__":
    unittest.main()
