"""Evaluate unordered pairs once, with explicit errors and symmetric maps."""

from itertools import combinations
from math import isfinite, sqrt
import time

from .geometry import xyz


def classify_distance(distance: float, contact: float, proximity: float) -> str:
    if not isfinite(distance) or distance < 0:
        raise ValueError("Distance must be finite and nonnegative")
    if distance <= contact:
        return "contact_or_overlap"
    return "close" if distance <= proximity else "separated"


def compute_spatial_relations(instances, settings, progress=None) -> dict:
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape

    ids = [i.instance_id for i in instances]
    if len(set(ids)) != len(ids):
        raise ValueError("Spatial relations require unique instance IDs")
    result = {"status": "complete" if settings.enabled else "disabled", "unit": "mm",
              "coordinate_frame": "assembly", "method": "BRepExtrema_DistShapeShape",
              "contact_tolerance_mm": settings.contact_tolerance_mm,
              "proximity_threshold_mm": settings.proximity_threshold_mm,
              "distance_mode": settings.distance_mode, "multithread": settings.multithread,
              "statistics": {"total_pairs": len(ids) * (len(ids) - 1) // 2,
                             "exact_calculations": 0, "bbox_rejections": 0, "failed_pairs": 0},
              "pairs": [], "contact_map": {key: [] for key in ids},
              "close_map": {key: [] for key in ids}}
    if not settings.enabled:
        return result
    started = time.monotonic()
    boxes = {}
    if settings.distance_mode == "nearby_pairs":
        for instance in instances:
            try:
                boxes[instance.instance_id] = conservative_bounds(instance.shape)
            except Exception:
                # An unavailable bound must never eliminate a potential contact.
                boxes[instance.instance_id] = None
    total = len(ids) * (len(ids) - 1) // 2
    for left, right in combinations(instances, 2):
        pair = {"part_a": left.instance_id, "part_b": right.instance_id,
                "distance_mm": None, "classification": None, "status": "failed"}
        try:
            left_box, right_box = boxes.get(left.instance_id), boxes.get(right.instance_id)
            lower_bound = box_distance(left_box, right_box) if left_box is not None and right_box is not None else None
            if lower_bound is not None and lower_bound > settings.proximity_threshold_mm:
                pair.update(status="complete", classification="separated", distance_kind="lower_bound",
                            distance_lower_bound_mm=lower_bound, method="conservative_AABB_filter")
                result["statistics"]["bbox_rejections"] += 1
                result["pairs"].append(pair)
                if progress:
                    progress("spatial_relations", len(result["pairs"]), total)
                continue
            result["statistics"]["exact_calculations"] += 1
            # The two-shape constructor computes immediately; set parallel mode
            # before loading/Perform so it applies to the actual calculation.
            tool = BRepExtrema_DistShapeShape()
            tool.SetMultiThread(settings.multithread)
            tool.LoadS1(left.shape)
            tool.LoadS2(right.shape)
            tool.Perform()
            if not tool.IsDone() or tool.NbSolution() < 1:
                raise ValueError("OCC did not find a minimum-distance solution")
            distance = float(tool.Value())
            classification = classify_distance(distance, settings.contact_tolerance_mm,
                                                settings.proximity_threshold_mm)
            pair.update(status="complete", distance_mm=distance, classification=classification,
                        distance_kind="exact", method="BRepExtrema_DistShapeShape",
                        point_a=xyz(tool.PointOnShape1(1)), point_b=xyz(tool.PointOnShape2(1)),
                        inner_solution=bool(tool.InnerSolution()))
            mapping = result["contact_map"] if classification == "contact_or_overlap" else result["close_map"]
            if classification != "separated":
                mapping[left.instance_id].append(right.instance_id)
                mapping[right.instance_id].append(left.instance_id)
        except Exception as exc:
            pair["error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "partial"
            result["statistics"]["failed_pairs"] += 1
        result["pairs"].append(pair)
        if progress:
            progress("spatial_relations", len(result["pairs"]), total)
    result["statistics"]["elapsed_seconds"] = time.monotonic() - started
    return result


def conservative_bounds(shape):
    """World-space enclosing box including shape tolerances, no triangulation."""
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib

    box = Bnd_Box()
    brepbndlib.AddOptimal(shape, box, False, True)
    if box.IsVoid() or box.IsWhole():
        raise ValueError("No finite enclosing box")
    limits = tuple(map(float, box.Get()))
    if not all(isfinite(value) for value in limits):
        raise ValueError("Nonfinite enclosing box")
    return limits


def box_distance(left, right):
    gaps = [max(left[axis] - right[axis + 3], right[axis] - left[axis + 3], 0)
            for axis in range(3)]
    # Conservative numerical margin: a threshold-boundary pair stays a candidate.
    return max(0.0, sqrt(sum(gap * gap for gap in gaps)) - 1e-7)
