from pathlib import Path
import json
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
        requested="assembly_context", artifact="assembly_overview", revision_id=None,
        label="assembly overview", path=Path("assembly_overview.json"),
        current={"assembly_name_guess": ["Old name"],
                 "assembly_description": ["Old description"]},
        expected_sha256="abc",
    )


class ArtifactChangePlannerTests(unittest.TestCase):
    def test_returns_complete_rewritten_artifact(self):
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "artifact_json": json.dumps({"assembly_name_guess": ["New name"],
                                         "assembly_description": ["Updated description"]}),
            "changed_locations": ["assembly_name_guess", "assembly_description"],
            "summary": "Updated the assembly identity.",
        }))
        result = planner.rewrite(target(), "Use the corrected assembly name.")
        self.assertEqual(result["artifact"]["assembly_name_guess"], ["New name"])
        self.assertEqual(result["input"]["CURRENT_ARTIFACT"], target().current)
        self.assertEqual(
            result["input"]["NODE_STRUCTURED_OUTPUT_CONTRACT"]["source_model"],
            "AssemblyAnalysis")

    def test_rejects_missing_complete_artifact(self):
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "artifact_json": "{}", "changed_locations": ["assembly_name_guess"],
            "summary": "Returned no artifact.",
        }))
        with self.assertRaisesRegex(ValueError, "no complete artifact"):
            planner.rewrite(target(), "Use the corrected name.")

    def test_rejects_unchanged_artifact(self):
        resolved = target()
        planner = ArtifactChangePlanner(SETTINGS, {}, llm=_FakeLlm({
            "artifact_json": json.dumps(resolved.current),
            "changed_locations": ["assembly_name_guess"],
            "summary": "No effective change.",
        }))
        with self.assertRaisesRegex(ValueError, "unchanged"):
            planner.rewrite(resolved, "Keep it the same.")


if __name__ == "__main__":
    unittest.main()
