import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.app.streamlit.events import normalize_workflow_event
from assembly_automation.app.streamlit.controller import SessionController
from assembly_automation.app.streamlit.image_catalog import build_image_catalog
from assembly_automation.app.streamlit.session_view import load_session_snapshot, safe_artifact_path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class DurableSessionViewTests(unittest.TestCase):
    def test_snapshot_uses_manifest_paths_and_agent_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "manifest.json", {
                "session_id": "session-1", "status": "running", "active_sequence_revision": "r001",
                "stages": {"bom_merge": {"status": "complete"}},
                "artifacts": {"enriched_bom": "04_monoparts/revisions/r001/bom.json"},
                "updated_at": "now",
            })
            write_json(root / "04_monoparts/revisions/r001/bom.json", {"parts": [{"part_id": "p1"}]})
            write_json(root / "09_user_agent/state.json", {
                "active_sequence_revision": "r002", "approved_sequence_revision": None,
                "stale": {"sequence": False},
            })
            write_json(root / "09_user_agent/conversation.json", [
                {"role": "user", "content": "hello"}, {"role": "assistant", "content": "ready"}
            ])

            snapshot = load_session_snapshot(root)

            self.assertEqual(snapshot.active_revision, "r002")
            self.assertEqual(snapshot.checkpoint, "awaiting_sequence_approval")
            self.assertEqual(snapshot.messages[1]["content"], "ready")
            self.assertEqual(snapshot.artifact("enriched_bom").data["parts"][0]["part_id"], "p1")

    def test_manifest_cannot_escape_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertIsNone(safe_artifact_path(root, "../secret.json"))
            self.assertIsNone(safe_artifact_path(root, str(root.parent / "secret.json")))
            inside = root / "artifact.json"
            self.assertEqual(safe_artifact_path(root, str(inside)), inside.resolve())

    def test_snapshot_merges_planning_artifacts_for_json_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "manifest.json", {
                "session_id": "s", "status": "complete", "artifacts": {}, "stages": {},
            })
            write_json(root / "08_planning/01_ideas/idea_r001/planning_brief.json",
                       {"objective": "Automate handling"})
            write_json(root / "08_planning/planning_manifest.json", {
                "status": "awaiting_idea_review", "active_idea_revision": "idea_r001",
                "artifacts": {
                    "automation_idea": "08_planning/01_ideas/idea_r001/planning_brief.json"
                },
            })

            snapshot = load_session_snapshot(root)

            self.assertEqual(snapshot.checkpoint, "awaiting_idea_review")
            self.assertEqual(snapshot.artifact("automation_idea").data["objective"],
                             "Automate handling")

    def test_catalog_only_indexes_known_roots_and_active_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "manifest.json", {
                "session_id": "s", "status": "running", "active_sequence_revision": "r002",
                "artifacts": {}, "stages": {},
            })
            (root / "02_preprocessing/images/assembly").mkdir(parents=True)
            (root / "02_preprocessing/images/assembly/iso1.png").write_bytes(b"png")
            (root / "02_preprocessing/images/parts/p1").mkdir(parents=True)
            (root / "02_preprocessing/images/parts/p1/collage_p1.png").write_bytes(b"png")
            (root / "05_sequence/revisions/r001/renderings").mkdir(parents=True)
            (root / "05_sequence/revisions/r001/renderings/old.png").write_bytes(b"png")
            active = root / "05_sequence/revisions/r002/renderings"
            active.mkdir(parents=True)
            (active / "step_01.png").write_bytes(b"png")

            entries = build_image_catalog(load_session_snapshot(root))
            names = {entry.path.name for entry in entries}

            self.assertEqual(names, {"iso1.png", "collage_p1.png", "step_01.png"})
            self.assertNotIn("old.png", names)

    def test_events_have_stable_product_envelope(self):
        event = normalize_workflow_event({"type": "stage_completed", "stage": "rendering"},
                                         session_id="s1", correlation_id="c1")
        self.assertEqual(event["type"], "workflow.stage.completed")
        self.assertEqual(event["session_id"], "s1")
        self.assertEqual(event["correlation_id"], "c1")
        self.assertTrue(event["event_id"])
        self.assertTrue(event["timestamp"])

    def test_sequence_overview_is_first_active_revision_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "manifest.json", {
                "session_id": "s", "status": "complete", "active_sequence_revision": "r001",
                "artifacts": {}, "stages": {},
            })
            rendering = root / "05_sequence/revisions/r001/renderings"
            rendering.mkdir(parents=True)
            for name in ("collage_sequence.png", "collage_step_01.png", "raw.png"):
                (rendering / name).write_bytes(b"png")
            overview = {"path": "collage_sequence.png", "category": "sequence_overview",
                        "view": "ordered_steps", "status": "complete"}
            write_json(rendering / "rendering_summary.json", {
                "sequence_overview": overview,
                "collages": [overview, {"path": "collage_step_01.png", "step_id": 1,
                                         "category": "step_collage", "view": "overview"}],
                "images": [{"path": "raw.png", "step_id": 1, "category": "assembled",
                            "view": "iso1"}],
            })

            sequence_entries = [item for item in build_image_catalog(load_session_snapshot(root))
                                if item.group.startswith("Sequence")]
            self.assertEqual(sequence_entries[0].path.name, "collage_sequence.png")
            self.assertEqual(sequence_entries[0].label, "Assembly sequence overview")
            self.assertEqual(sequence_entries[0].group, "Sequence overview · r001")
            self.assertEqual({item.group for item in sequence_entries},
                             {"Sequence overview · r001", "Sequence steps · r001",
                              "Sequence evidence · r001"})


class _RecordingController(SessionController):
    def __init__(self, **kwargs):
        self.handled = []
        super().__init__(**kwargs)

    def _start(self, **payload):
        self.handled.append(("start", payload["step_name"]))

    def _initialize_runtime(self, root, *, step_path, supporting_files):
        # These tests exercise controller queue/draft lifetime only. Production
        # construction now creates the real credential-backed agent at startup.
        self.session_root = root


class SessionControllerTests(unittest.TestCase):
    def test_controller_creates_and_discards_lightweight_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = _RecordingController(workspace_root=folder)
            draft = controller.draft_root
            self.assertTrue((draft / "manifest.json").is_file())
            self.assertTrue((draft / "draft.json").is_file())

            controller.stop()

            self.assertFalse(draft.exists())

    def test_worker_serializes_commands_and_emits_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = _RecordingController(workspace_root=folder)
            try:
                first = controller.start_session(step_name="one.step", step_bytes=b"one")
                second = controller.start_session(step_name="two.step", step_bytes=b"two")
                completed = []
                deadline = time.monotonic() + 2
                while len(completed) < 2 and time.monotonic() < deadline:
                    try:
                        event = controller.events.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if event["type"] == "agent.turn.completed":
                        completed.append(event["correlation_id"])
            finally:
                controller.stop()

        self.assertEqual(controller.handled, [("start", "one.step"), ("start", "two.step")])
        self.assertEqual(completed, [first, second])


if __name__ == "__main__":
    unittest.main()
