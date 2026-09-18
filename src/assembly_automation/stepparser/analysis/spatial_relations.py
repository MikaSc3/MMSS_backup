"""Evaluate unordered pairs once, with explicit errors and symmetric maps."""

from itertools import combinations
from math import isfinite

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
              "pairs": [], "contact_map": {key: [] for key in ids},
              "close_map": {key: [] for key in ids}}
    if not settings.enabled:
        return result
    total = len(ids) * (len(ids) - 1) // 2
    for left, right in combinations(instances, 2):
        pair = {"part_a": left.instance_id, "part_b": right.instance_id,
                "distance_mm": None, "classification": None, "status": "failed"}
        try:
            tool = BRepExtrema_DistShapeShape(left.shape, right.shape)
            if not tool.IsDone() or tool.NbSolution() < 1:
                raise ValueError("OCC did not find a minimum-distance solution")
            distance = float(tool.Value())
            classification = classify_distance(distance, settings.contact_tolerance_mm,
                                                settings.proximity_threshold_mm)
            pair.update(status="complete", distance_mm=distance, classification=classification,
                        point_a=xyz(tool.PointOnShape1(1)), point_b=xyz(tool.PointOnShape2(1)),
                        inner_solution=bool(tool.InnerSolution()))
            mapping = result["contact_map"] if classification == "contact_or_overlap" else result["close_map"]
            if classification != "separated":
                mapping[left.instance_id].append(right.instance_id)
                mapping[right.instance_id].append(left.instance_id)
        except Exception as exc:
            pair["error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "partial"
        result["pairs"].append(pair)
        if progress:
            progress("spatial_relations", len(result["pairs"]), total)
    return result
