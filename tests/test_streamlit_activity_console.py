from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.app.streamlit.activity_console import console_lines, event_line


class ActivityConsoleTests(unittest.TestCase):
    def event(self, kind, **values):
        return {"type": kind, "timestamp": "2026-09-24T08:10:11+00:00", **values}

    def test_progress_uses_terminal_style_stage_item_and_counter(self):
        line = event_line(self.event(
            "workflow.stage.progress", stage="step_preprocessing",
            item="geometry", completed=1, total=9))
        self.assertIn("[step_preprocessing] geometry 1/9", line)

    def test_failures_are_visible_and_noise_is_ignored(self):
        failure = event_line(self.event("agent.turn.failed", error="ValueError: bad input"))
        self.assertIn("[error] ValueError: bad input", failure)
        self.assertIsNone(event_line(self.event("artifact.updated")))

    def test_console_keeps_only_latest_relevant_lines(self):
        events = [self.event("workflow.stage.started", stage=f"stage_{index}")
                  for index in range(5)]
        self.assertEqual(len(console_lines(events, limit=2)), 2)
        self.assertIn("stage_4", console_lines(events, limit=2)[-1])

    def test_console_defaults_to_two_activity_lines(self):
        events = [self.event("workflow.stage.started", stage=f"stage_{index}")
                  for index in range(5)]
        self.assertEqual(len(console_lines(events)), 2)


if __name__ == "__main__":
    unittest.main()
