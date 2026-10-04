from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.app.streamlit.components.visuals import _view_index, images_for_selection
from assembly_automation.app.streamlit.image_catalog import ImageEntry
from assembly_automation.app.streamlit.selection import (
    SelectionContext, available_output_scopes, entity_selections)


class VisualStateTests(unittest.TestCase):
    def test_view_index_normalizes_legacy_and_invalid_widget_values(self):
        self.assertEqual(_view_index(2, 3), 2)
        self.assertEqual(_view_index("2", 3), 2)
        self.assertEqual(_view_index("front.png", 3), 0)
        self.assertEqual(_view_index(3, 3), 0)
        self.assertEqual(_view_index(None, 3), 0)

    def test_visuals_follow_artifact_part_and_step_selection(self):
        entries = [
            ImageEntry(Path("assembly.png"), "Assembly", "Assembly", "assembly"),
            ImageEntry(Path("p1.png"), "Part 1", "P1", "part", part_id="part_001"),
            ImageEntry(Path("p2.png"), "Part 2", "P2", "part", part_id="part_002"),
            ImageEntry(Path("overview.png"), "Sequence", "Overview", "sequence_overview"),
            ImageEntry(Path("step1.png"), "Sequence", "Step 1 collage", "step_collage",
                       step_id="1"),
            ImageEntry(Path("step1_iso.png"), "Sequence", "Step 1 ISO", "assembled",
                       step_id="1"),
            ImageEntry(Path("step2.png"), "Sequence", "Step 2 collage", "step_collage",
                       step_id="2"),
        ]
        self.assertEqual(
            [item.path.name for item in images_for_selection(
                entries, SelectionContext("part", entity_id="part_001"))], ["p1.png"])
        self.assertEqual(
            [item.path.name for item in images_for_selection(
                entries, SelectionContext("interaction", step_id=1))],
            ["step1.png", "step1_iso.png"])
        self.assertEqual(
            [item.path.name for item in images_for_selection(
                entries, SelectionContext("sequence"))][0], "overview.png")


class ArtifactNavigationTests(unittest.TestCase):
    class Snapshot:
        active_revision = "r007"

        def __init__(self):
            self.artifacts = {
                "assembly_overview": SimpleNamespace(exists=True, data={"assembly_name_guess": "A"}),
                "enriched_bom": SimpleNamespace(exists=True, data={"parts": [
                    {"part_id": "part_001", "part_analysis": {"part_name_guess": "Housing"}},
                    {"part_id": "part_002", "part_analysis": {"part_name_guess": "Shaft"}},
                ]}),
                "assembly_sequence": SimpleNamespace(exists=True, data={"steps": []}),
                "interaction_analysis": SimpleNamespace(exists=True, data={"steps": [
                    {"step": {"step_id": 1, "step_description": "Place housing"}},
                    {"step": {"step_id": 2, "step_description": "Insert shaft"}},
                ]}),
                "ffa_assessment": SimpleNamespace(exists=True, data={"steps": [
                    {"step": {"step_id": 1, "step_description": "Place housing"}},
                ]}),
            }

        def artifact(self, artifact_id):
            return self.artifacts.get(artifact_id)

    def test_master_navigation_exposes_outputs_and_contextual_subselectors(self):
        snapshot = self.Snapshot()
        self.assertEqual(available_output_scopes(snapshot),
                         ["assembly", "part", "sequence", "interaction", "ffa"])
        parts = entity_selections(snapshot, "part")
        self.assertEqual([label for label, _selection in parts],
                         ["part_001 · Housing", "part_002 · Shaft"])
        interactions = entity_selections(snapshot, "interaction")
        self.assertEqual([selection.step_id for _label, selection in interactions], [1, 2])
        self.assertEqual(interactions[0][1].revision_id, "r007")


if __name__ == "__main__":
    unittest.main()
