from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.app.streamlit.progress import PHASES, phase_states, render_progress


class MarkdownCapture:
    def __init__(self):
        self.body = ""

    def markdown(self, body, **kwargs):
        self.body = body


class ProgressStateTests(unittest.TestCase):
    def snapshot(self, stages, checkpoint="preparing", **overrides):
        values = {
            "stages": stages,
            "checkpoint": checkpoint,
            "active_revision": None,
            "approved_revision": None,
            "workflow_status": "running",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_multi_stage_phases_require_every_configured_stage(self):
        states = phase_states(self.snapshot({
            "monopart_analysis:part_001": {"status": "complete"},
            "bom_merge": {"status": "complete"},
            "report_synthesis": {"status": "complete"},
        }))
        self.assertEqual(states["parts"], "complete")
        self.assertEqual(states["report"], "queued")

    def test_sequence_review_waits_for_explicit_approval(self):
        states = phase_states(self.snapshot(
            {"sequence_generation:r001": {"status": "complete"}},
            checkpoint="awaiting_sequence_approval", active_revision="r001"))
        self.assertEqual(states["sequence"], "complete")
        self.assertEqual(states["sequence_review"], "waiting")

    def test_render_uses_numbered_dot_track_and_active_stage(self):
        target = MarkdownCapture()
        snapshot = self.snapshot({"step_preprocessing": {"status": "running"}})
        events = [{"type": "workflow.stage.started", "stage": "step_preprocessing"}]

        render_progress(target, snapshot, events, busy=True)

        self.assertEqual(target.body.count('class="workflow-node"'), 2)
        self.assertNotIn('class="workflow-label"></div>', target.body)
        self.assertIn('class="workflow-phase active"', target.body)
        self.assertIn("STEP preprocessing", target.body)

    def test_preprocessing_subprogress_stays_within_the_product_phase(self):
        target = MarkdownCapture()
        snapshot = self.snapshot({"step_preprocessing": {"status": "running"}})
        events = [{"type": "workflow.stage.progress", "stage": "step_preprocessing",
                   "item": "geometry", "completed": 2, "total": 4}]

        render_progress(target, snapshot, events, busy=True)

        self.assertIn('class="workflow-phase active"', target.body)
        self.assertIn("STEP preprocessing", target.body)
        self.assertNotIn("Geometry extraction from STEP", target.body)
        self.assertIn("2 / 4", target.body)

    def test_rendering_subprogress_does_not_create_a_product_phase(self):
        target = MarkdownCapture()
        snapshot = self.snapshot({"step_preprocessing": {"status": "running"}})
        events = [{"type": "workflow.stage.progress", "stage": "step_preprocessing",
                   "item": "rendering", "completed": 1, "total": 3}]

        render_progress(target, snapshot, events, busy=True)

        self.assertIn("STEP preprocessing", target.body)
        self.assertNotIn("STEP rendering", target.body)

    def test_progress_is_visible_before_a_session_exists(self):
        target = MarkdownCapture()

        render_progress(target, None, [], busy=False)

        self.assertEqual(target.body.count('class="workflow-node"'), 1)
        self.assertNotIn('class="workflow-label"></div>', target.body)
        self.assertIn("Session setup", target.body)

    def test_draft_session_waits_at_setup(self):
        draft = self.snapshot({}, checkpoint="awaiting_upload", workflow_status="draft")

        states = phase_states(draft)

        self.assertEqual(states["setup"], "waiting")
        self.assertTrue(all(value == "queued" for key, value in states.items() if key != "setup"))

        target = MarkdownCapture()
        render_progress(target, draft, [], busy=False)
        self.assertIn("Session setup", target.body)

    def test_concept_planning_checkpoints_advance_new_phases(self):
        concept = phase_states(self.snapshot({}, checkpoint="awaiting_concept_review",
                                             workflow_status="complete"))
        self.assertEqual(concept["automation_idea"], "complete")
        self.assertEqual(concept["detailed_planning"], "complete")
        self.assertEqual(concept["concept"], "waiting")
        self.assertEqual(concept["layout"], "queued")

        cost = phase_states(self.snapshot({}, checkpoint="awaiting_cost_review",
                                          workflow_status="complete"))
        self.assertEqual(cost["layout"], "complete")
        self.assertEqual(cost["costing"], "waiting")

    def test_planning_tool_event_selects_matching_active_phase(self):
        target = MarkdownCapture()
        snapshot = self.snapshot({}, checkpoint="awaiting_layout_review",
                                 workflow_status="complete")
        events = [{"type": "tool.started", "tool": "layout_planner"}]

        render_progress(target, snapshot, events, busy=True)

        self.assertIn("Layout planning", target.body)
        self.assertIn('class="workflow-phase active"', target.body)


if __name__ == "__main__":
    unittest.main()
