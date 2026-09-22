"""Sample translational removal paths and report obstructing part instances."""

from math import sqrt

from .spatial_relations import conservative_bounds


def _overlap(a, b):
    return all(a[i] <= b[i+3] and b[i] <= a[i+3] for i in range(3))


def _translated(shape, vector, distance):
    from OCC.Core.gp import gp_Trsf, gp_Vec
    from OCC.Core.TopLoc import TopLoc_Location
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(*(value*distance for value in vector)))
    return shape.Moved(TopLoc_Location(transform))


def _translated_bounds(bounds, vector, distance):
    shift = [value*distance for value in vector]
    return tuple(bounds[index] + shift[index % 3] for index in range(6))


def _interferes(left, right, tolerance):
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
    tool = BRepExtrema_DistShapeShape()
    tool.SetMultiThread(True)
    tool.LoadS1(left)
    tool.LoadS2(right)
    tool.Perform()
    if not tool.IsDone() or tool.NbSolution() < 1:
        raise ValueError("OCC minimum-clearance calculation did not complete")
    return float(tool.Value()) <= tolerance


def _contact_direction_proxy(instances, settings, relations):
    ids = [item.instance_id for item in instances]
    centres = {}
    for item in instances:
        if getattr(item, "center_of_mass", None) is not None:
            centres[item.instance_id] = item.center_of_mass
        else:
            box = conservative_bounds(item.shape)
            centres[item.instance_id] = [(box[i]+box[i+3])/2 for i in range(3)]
    directions = [("+X", (1., 0., 0.)), ("-X", (-1., 0., 0.)),
                  ("+Y", (0., 1., 0.)), ("-Y", (0., -1., 0.)),
                  ("+Z", (0., 0., 1.)), ("-Z", (0., 0., -1.))]
    contacts = [(pair["part_a"], pair["part_b"]) for pair in relations.get("pairs", [])
                if pair.get("status") == "complete" and pair.get("classification") == "contact_or_overlap"]
    blockers = {key: {name: set() for name, _ in directions} for key in ids}
    for left, right in contacts:
        delta = [centres[right][i]-centres[left][i] for i in range(3)]
        length = sqrt(sum(value*value for value in delta))
        if length <= 1e-12:
            continue
        unit = [value/length for value in delta]
        for name, vector in directions:
            dot = sum(unit[i]*vector[i] for i in range(3))
            if dot >= settings.directional_cosine_threshold:
                blockers[left][name].add(right)
            if dot <= -settings.directional_cosine_threshold:
                blockers[right][name].add(left)
    edge_directions, parts = {}, []
    for key in ids:
        records = []
        for name, vector in directions:
            values = sorted(blockers[key][name])
            records.append({"direction": name, "vector": list(vector), "blocked": bool(values),
                            "blockers": values, "status": "complete"})
            for blocker in values:
                edge_directions.setdefault((blocker, key), []).append(name)
        blocked = [record for record in records if record["blocked"]]
        parts.append({"instance_id": key, "blocked_direction_count": len(blocked),
                      "tested_direction_count": 6, "interlock_score": len(blocked)/6,
                      "free_directions": [record["direction"] for record in records if not record["blocked"]],
                      "blocked_directions": records})
    edges = [{"blocker": a, "blocked_part": b, "directions": sorted(values),
              "strength": len(set(values))/6} for (a, b), values in sorted(edge_directions.items())]
    return {"status": "complete", "unit": "mm", "coordinate_frame": "assembly",
            "method": "contact_direction_proxy_from_exact_contact_and_relative_centres",
            "directions": [{"id": name, "vector": list(vector)} for name, vector in directions],
            "parts": parts, "blocker_edges": edges, "interlocked_groups": _groups(ids, edges),
            "directional_cosine_threshold": settings.directional_cosine_threshold,
            "limitations": ["This is a potential-blocking proxy, not a collision-free motion proof.",
                            "Direction uses the vector between part centres, not the contact normal.",
                            "Rotation, deformation, fasteners and removal of groups are not tested."]}


def _groups(ids, edges):
    adjacency = {key: set() for key in ids}
    for edge in edges:
        adjacency[edge["blocker"]].add(edge["blocked_part"])
        adjacency[edge["blocked_part"]].add(edge["blocker"])
    remaining, groups = set(ids), []
    while remaining:
        todo = [remaining.pop()]
        group = set(todo)
        while todo:
            for neighbour in adjacency[todo.pop()] - group:
                group.add(neighbour); remaining.discard(neighbour); todo.append(neighbour)
        if len(group) > 1:
            groups.append(sorted(group))
    return sorted(groups)


def analyze_interlocking(instances, settings, relations=None, *, progress=None):
    """Test discrete positions along candidate removal directions.

    A direction is blocked when a translated position loses the configured
    minimum clearance to another part. Bboxes only eliminate impossible pairs.
    """
    ids = [item.instance_id for item in instances]
    result = {"status": "complete" if settings.enabled else "disabled", "unit": "mm",
              "coordinate_frame": "assembly", "method": "sampled_translational_minimum_clearance",
              "sample_count": settings.sample_count, "directions": [], "parts": [],
              "blocker_edges": [], "interlocked_groups": [],
              "limitations": ["Discrete path samples can miss thin transient collisions.",
                              "Zero-clearance sliding contact is classified as blocked.",
                              "Rotation, deformation, fasteners and disassembly of groups are not tested."]}
    if not settings.enabled:
        return result
    if settings.mode == "contact_direction_proxy":
        return _contact_direction_proxy(instances, settings, relations or {})
    boxes = {item.instance_id: conservative_bounds(item.shape) for item in instances}
    assembly_bounds = (min(box[0] for box in boxes.values()), min(box[1] for box in boxes.values()),
                       min(box[2] for box in boxes.values()), max(box[3] for box in boxes.values()),
                       max(box[4] for box in boxes.values()), max(box[5] for box in boxes.values()))
    span = sqrt(sum((assembly_bounds[i+3]-assembly_bounds[i])**2 for i in range(3)))
    directions = [("+X", (1., 0., 0.)), ("-X", (-1., 0., 0.)),
                  ("+Y", (0., 1., 0.)), ("-Y", (0., -1., 0.)),
                  ("+Z", (0., 0., 1.)), ("-Z", (0., 0., -1.))]
    result["directions"] = [{"id": name, "vector": list(vector)} for name, vector in directions]
    edge_directions = {}
    total = len(instances)*len(directions)
    completed = 0
    for moving in instances:
        box = boxes[moving.instance_id]
        part_span = sqrt(sum((box[i+3]-box[i])**2 for i in range(3)))
        travel = max(span+part_span, settings.minimum_travel_mm)
        records = []
        for direction_name, vector in directions:
            record = {"direction": direction_name, "vector": list(vector), "travel_mm": travel,
                      "blocked": False, "blockers": [], "first_collision_mm": None, "status": "complete"}
            try:
                # Quadratic spacing concentrates checks near the assembled pose.
                for sample in range(1, settings.sample_count+1):
                    distance = travel*(sample/settings.sample_count)**2
                    moved_box = _translated_bounds(box, vector, distance)
                    candidates = [other for other in instances if other.instance_id != moving.instance_id
                                  and _overlap(moved_box, boxes[other.instance_id])]
                    blockers = []
                    if candidates:
                        moved = _translated(moving.shape, vector, distance)
                    for other in candidates:
                        if _interferes(moved, other.shape, settings.interference_tolerance_mm):
                            blockers.append(other.instance_id)
                    if blockers:
                        record.update(blocked=True, blockers=sorted(blockers), first_collision_mm=distance)
                        for blocker in blockers:
                            edge_directions.setdefault((blocker, moving.instance_id), []).append(direction_name)
                        break
            except Exception as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                result["status"] = "partial"
            records.append(record)
            completed += 1
            if progress:
                progress("interlocking", completed, total)
        blocked = [item for item in records if item["status"] == "complete" and item["blocked"]]
        tested = [item for item in records if item["status"] == "complete"]
        result["parts"].append({"instance_id": moving.instance_id,
                                "blocked_direction_count": len(blocked),
                                "tested_direction_count": len(tested),
                                "interlock_score": len(blocked)/len(tested) if tested else None,
                                "free_directions": [item["direction"] for item in tested if not item["blocked"]],
                                "blocked_directions": records})
    result["blocker_edges"] = [{"blocker": a, "blocked_part": b, "directions": sorted(values),
                                "strength": len(set(values))/len(directions)}
                               for (a, b), values in sorted(edge_directions.items())]
    # Connected blocker components summarize mutually related regions without
    # claiming every edge is bidirectional.
    result["interlocked_groups"] = _groups(ids, result["blocker_edges"])
    return result
