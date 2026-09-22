"""Check contact branches and exact selection from conservative bounds."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assembly_automation.stepparser.rendering.distance_diagram import build_distance_graph
from assembly_automation.stepparser.rendering.part_universe import build_part_universe, group_overlapping_markers, volume_marker_sizes


class DistanceDiagramTests(unittest.TestCase):
    def test_volume_normalization_respects_radius_limits(self):
        bom = {"parts": [{"part_id": key, "geometry": {"volume": volume}}
                         for key, volume in (("a", 10), ("b", 20), ("c", 30), ("d", None))],
               "instances": [{"instance_id": key, "part_id": key} for key in "abcd"]}
        sizes, scale = volume_marker_sizes(bom, 6, 36)
        self.assertEqual([sizes[key]["normalized_volume"] for key in "abcd"], [0, .5, 1, None])
        self.assertEqual(sizes["a"]["radius_px"], 6)
        self.assertEqual(sizes["c"]["radius_px"], 36)
        self.assertEqual(sizes["d"]["radius_px"], 6)
        self.assertAlmostEqual(sizes["b"]["radius_px"]**2, (6**2+36**2)/2)
        self.assertEqual(scale["mapping"], "min-max normalized volume to marker area")
        with self.assertRaises(ValueError):
            volume_marker_sizes(bom, 36, 6)

    def test_visually_overlapping_markers_group_without_collapsing_a_chain(self):
        points = {"a": [0, 0], "b": [.001, 0], "c": [17, 0], "d": [34, 0]}
        self.assertEqual(group_overlapping_markers(points), [["a", "b", "c"], ["d"]])
        self.assertEqual(points["b"], [.001, 0])

    def test_planar_universe_projection_preserves_every_pair_distance(self):
        from math import dist
        bom = {"instances": [{"instance_id": key, "part_id": key, "center_of_mass": point}
                             for key, point in (("a", [0, 0, 0]), ("b", [3, 4, 0]),
                                                ("c", [-3, 4, 0]), ("d", [0, 12, 0]))]}
        graph = build_part_universe(bom, {"geometry": {"center_of_mass": [0, 0, 0]}})
        projected = graph["projected_positions_mm"]
        for pair in graph["com_pairs"]:
            self.assertAlmostEqual(dist(projected[pair["part_a"]], projected[pair["part_b"]]), pair["distance_mm"])
        self.assertAlmostEqual(graph["projection_normalized_distance_error"], 0)
        self.assertEqual(projected["a"], [0, 0])
        for key, point in projected.items():
            for axis in range(2):
                self.assertAlmostEqual(graph["positions"][key][axis], point[axis]*graph["pixels_per_projected_mm"])

    def test_universe_uses_3d_distances_and_retains_copies(self):
        bom = {"instances": [{"instance_id": key, "part_id": "shared", "center_of_mass": point}
                             for key, point in (("a", [0, 0, 0]), ("b", [3, 4, 12]), ("c", [0, 0, 0]))]}
        graph = build_part_universe(bom, {"geometry": {"center_of_mass": [1, 0, 0]}})
        self.assertEqual(graph["start_instance"], "a")
        self.assertEqual(len(graph["com_pairs"]), 3)
        self.assertEqual([p["distance_mm"] for p in graph["com_pairs"]], [13, 0, 13])
        self.assertEqual(len(graph["positions"]), 3)
        self.assertEqual(graph["positions"]["a"], [0, 0])
        self.assertAlmostEqual(graph["positions"]["c"][0], 0)
        self.assertAlmostEqual(graph["positions"]["c"][1], 0)
        manual = build_part_universe(bom, {"geometry": {"center_of_mass": [1, 0, 0]}}, start_part="b")
        self.assertEqual(manual["start_instance"], "b")
        self.assertEqual(manual["reference_selection"], "manual")

    def test_branch_contacts_do_not_invent_contact_between_leaves(self):
        bom = {"instances": [{"instance_id": key, "part_id": key, "center_of_mass": [i, 0, 0]}
                             for i, key in enumerate(("a", "b", "c"))]}
        pairs = [{"part_a": a, "part_b": b, "status": "complete", "distance_mm": d}
                 for a, b, d in (("a", "b", 0), ("a", "c", 0), ("b", "c", 23))]
        graph = build_distance_graph(bom, {"geometry": {"center_of_mass": [1, 0, 0]}},
                                     {"contact_tolerance_mm": .01, "pairs": pairs})
        self.assertEqual(graph["start_instance"], "b")
        self.assertEqual(len(graph["contact_groups"]), 1)
        self.assertEqual(len(graph["contact_edges"]), 2)
        self.assertEqual(graph["distance_edges"], [])

    def test_lower_bound_is_not_used_as_exact_distance(self):
        bom = {"instances": [{"instance_id": key, "part_id": key} for key in ("a", "b", "c")]}
        pairs = [{"part_a": "a", "part_b": "b", "status": "complete", "distance_mm": 5},
                 {"part_a": "a", "part_b": "c", "status": "complete", "distance_mm": None,
                  "distance_lower_bound_mm": 1},
                 {"part_a": "b", "part_b": "c", "status": "complete", "distance_mm": 6}]
        calls = []
        def exact(a, b):
            calls.append((a, b))
            return 20
        graph = build_distance_graph(bom, {}, {"contact_tolerance_mm": .01, "pairs": pairs}, exact_distance=exact)
        self.assertEqual(calls, [("a", "c")])
        self.assertEqual([e["distance_mm"] for e in graph["distance_edges"]], [5, 6])
        self.assertEqual(graph["additional_exact_calculations"], 1)
        with self.assertRaisesRegex(ValueError, "Exact gap distances"):
            build_distance_graph(bom, {}, {"contact_tolerance_mm": .01, "pairs": pairs})


if __name__ == "__main__":
    unittest.main()
