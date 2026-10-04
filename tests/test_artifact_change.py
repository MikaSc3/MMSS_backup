from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.user_agent.artifact_change.planner import ArtifactChangePlanner
from assembly_automation.user_agent.artifact_change.target_resolver import ResolvedTarget


class _StructuredCall:
    def __init__(self, schema, value):
        self.schema, self.value = schema, value

    def invoke(self, messages):
        return {"parsed": self.schema(**self.value), "raw": None}


class _FakeLlm:
    def __init__(self, value):
        self.value = value

    def with_structured_output(self, schema, include_raw=True):
        return _StructuredCall(schema, self.value)


SETTINGS = {
    "enabled": True,
    "llm": {"profile": "test", "temperature": 0},
    "prompts": {"system": "system_v1", "human": "human_v1"},
    "structured_output": "artifact_change_v1",
}


def target():
    return ResolvedTarget(
        requested="part001", artifact="bom", entity_id="part_001", revision_id=None,
        label="part part_001",
        current={"nature_of_provision_guess": "Provided upright.",
                 "handling_implications": "Grip from above."},
        editable_fields=("nature_of_provision_guess", "handling_implications"),
        expected_sha256="abc",
    )


class ArtifactChangePlannerTests(unittest.TestCase):
    def test_returns_minimal_validated_changes(self):
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "edits": [{"field": "nature_of_provision_guess",
                       "new_value": "Provided face down.",
                       "reason": "The user specified the orientation."}],
            "summary": "Updated provision orientation.",
        }))
        result = planner.plan(target(), "The part is provisioned face down.")
        self.assertEqual(result["changes"],
                         {"nature_of_provision_guess": "Provided face down."})
        self.assertEqual(result["input"]["editable_fields"],
                         ["nature_of_provision_guess", "handling_implications"])

    def test_rejects_model_attempt_to_change_read_only_field(self):
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "edits": [{"field": "part_color", "new_value": "red",
                       "reason": "Unsupported inferred change."}],
            "summary": "Changed color.",
        }))
        with self.assertRaisesRegex(ValueError, "read-only or unknown"):
            planner.plan(target(), "Make it red.")

    def test_rejects_unchanged_field(self):
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "edits": [{"field": "nature_of_provision_guess",
                       "new_value": "Provided upright.", "reason": "No change."}],
            "summary": "No effective change.",
        }))
        with self.assertRaisesRegex(ValueError, "unchanged field"):
            planner.plan(target(), "Keep it the same.")


if __name__ == "__main__":
    unittest.main()
