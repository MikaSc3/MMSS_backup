import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.stepparser import StepParserSettings
from assembly_automation.workflows.nodes.step_preprocessing import run_step_preprocessing


class StepPreprocessingNodeTests(unittest.TestCase):
    @patch("assembly_automation.workflows.nodes.step_preprocessing.node.StepProcessor")
    def test_delegates_once_and_returns_stable_artifact_paths(self, processor_class):
        processor = processor_class.return_value
        processor.process_step_file.return_value = {"status": "complete"}
        progress = Mock()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "assembly.step"
            output = root / "session" / "preprocessing"
            source.touch()

            result = run_step_preprocessing(
                source,
                output,
                {"rendering": {"enabled": False}},
                progress=progress,
            )

        settings = processor_class.call_args.args[0]
        self.assertIsInstance(settings, StepParserSettings)
        self.assertFalse(settings.rendering.enabled)
        processor.process_step_file.assert_called_once_with(
            source.resolve(), output.resolve(), progress=progress
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["step_file"], str(source.resolve()))
        self.assertEqual(result["output_dir"], str(output.resolve()))
        self.assertEqual(
            result["artifacts"],
            {
                "manifest": str(output.resolve() / "manifest.json"),
                "assembly": str(output.resolve() / "assembly.json"),
                "bom": str(output.resolve() / "bom.json"),
                "spatial_relations": str(output.resolve() / "spatial_relations.json"),
                "interlocking": str(output.resolve() / "interlocking.json"),
                "images": str(output.resolve() / "images"),
            },
        )

    @patch("assembly_automation.workflows.nodes.step_preprocessing.node.StepProcessor")
    def test_accepts_prevalidated_settings_without_rebuilding_them(self, processor_class):
        processor_class.return_value.process_step_file.return_value = {"status": "partial"}
        settings = StepParserSettings()

        result = run_step_preprocessing("input.step", "output", settings)

        processor_class.assert_called_once_with(settings)
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
