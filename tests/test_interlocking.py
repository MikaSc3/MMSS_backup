"""Acceptance check for sampled directional blocking."""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt

from assembly_automation.stepparser.analysis.interlocking import analyze_interlocking
from assembly_automation.stepparser.settings import InterlockingSettings


class InterlockingTests(unittest.TestCase):
    def test_touching_boxes_block_motion_toward_each_other(self):
        instances = [SimpleNamespace(instance_id="a", shape=BRepPrimAPI_MakeBox(10, 10, 10).Shape()),
                     SimpleNamespace(instance_id="b", shape=BRepPrimAPI_MakeBox(gp_Pnt(10, 0, 0), 10, 10, 10).Shape())]
        result = analyze_interlocking(instances, InterlockingSettings(
            mode="sampled_clearance", sample_count=4, minimum_travel_mm=10))
        self.assertEqual(result["status"], "complete")
        by_id = {item["instance_id"]: item for item in result["parts"]}
        a = {item["direction"]: item for item in by_id["a"]["blocked_directions"]}
        self.assertTrue(a["+X"]["blocked"])
        self.assertEqual(a["+X"]["blockers"], ["b"])
        self.assertFalse(a["-X"]["blocked"])
        edge = next(item for item in result["blocker_edges"]
                    if item["blocker"] == "b" and item["blocked_part"] == "a")
        self.assertIn("+X", edge["directions"])


if __name__ == "__main__":
    unittest.main()
