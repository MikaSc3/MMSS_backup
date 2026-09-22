"""Fast distances between placed part centres in assembly coordinates."""

from itertools import combinations
from math import dist, isfinite


def com_distances(instances):
    pairs = []
    for a, b in combinations(instances, 2):
        left, right = a.get("center_of_mass"), b.get("center_of_mass")
        distance = dist(left, right) if left is not None and right is not None else None
        if distance is not None and not isfinite(distance):
            raise ValueError("Nonfinite instance centre of mass")
        pairs.append({"part_a": a["instance_id"], "part_b": b["instance_id"], "distance_mm": distance})
    return pairs
