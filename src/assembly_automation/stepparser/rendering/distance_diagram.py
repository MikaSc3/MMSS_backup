"""Schematic contact groups joined by minimum surface-distance connections."""

import heapq
from math import dist, isfinite


def build_distance_graph(bom, assembly, relations, *, start_part=None, exact_distance=None):
    """Keep every contact edge and use Kruskal's algorithm for gap connections.

    Lower bounds are evaluated lazily: an exact edge is selected only once no
    unresolved candidate has a smaller bound. Missing distances are never zero.
    """
    nodes = {item["instance_id"]: item for item in bom["instances"]}
    if not nodes:
        raise ValueError("BOM contains no placed instances")
    if relations.get("status") == "disabled":
        raise ValueError("Spatial relations were disabled; regenerate them first")
    if start_part is None:
        com = assembly.get("geometry", {}).get("center_of_mass")
        available = [key for key, item in nodes.items() if item.get("center_of_mass") is not None]
        start_part = min(available, key=lambda key: (dist(com, nodes[key]["center_of_mass"]), key)) if com is not None and available else min(nodes)
    if start_part not in nodes:
        raise ValueError(f"Unknown starting instance: {start_part}")
    parent = {key: key for key in nodes}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def join(a, b):
        a, b = find(a), find(b)
        if a == b:
            return False
        parent[b] = a
        return True

    tolerance = relations["contact_tolerance_mm"]
    contacts, heap, seen = [], [], set()
    for pair in relations["pairs"]:
        a, b = pair["part_a"], pair["part_b"]
        if a not in nodes or b not in nodes or a == b:
            raise ValueError("Spatial pair references invalid BOM instances")
        key = tuple(sorted((a, b)))
        if key in seen:
            raise ValueError(f"Duplicate spatial pair: {key}")
        seen.add(key)
        value = pair.get("distance_mm")
        exact = value is not None and pair.get("status") == "complete" and pair.get("distance_kind", "exact") == "exact"
        if exact and (not isfinite(value) or value < 0):
            raise ValueError(f"Invalid distance: {key}")
        if exact and value <= tolerance:
            contacts.append({"part_a": a, "part_b": b, "distance_mm": value})
            join(a, b)
        else:
            bound = value if exact else pair.get("distance_lower_bound_mm", 0.0)
            if not isfinite(bound) or bound < 0:
                raise ValueError(f"Invalid distance bound: {key}")
            heapq.heappush(heap, (bound, a, b, exact))
    if len(seen) != len(nodes) * (len(nodes) - 1) // 2:
        raise ValueError("Spatial relations must contain every unordered instance pair")
    # Freeze contact groups before gap connections merge the union-find sets.
    groups = {}
    for key in nodes:
        groups.setdefault(find(key), []).append(key)
    if relations.get("status") == "partial":
        raise ValueError("Some contact checks failed; regenerate spatial relations before drawing")
    gaps, calculations = [], 0
    remaining = len(groups) - 1
    while remaining and heap:
        value, a, b, exact = heapq.heappop(heap)
        if find(a) == find(b):
            continue
        if not exact:
            if exact_distance is None:
                raise ValueError("Exact gap distances are missing. Supply the original STEP file or regenerate using all_pairs.")
            distance = float(exact_distance(a, b))
            if not isfinite(distance) or distance <= tolerance:
                raise ValueError(f"Exact distance contradicts saved contact checks for {a}, {b}; regenerate spatial relations")
            if distance + 1e-6 < value:
                raise ValueError("Exact distance contradicts saved lower bound")
            calculations += 1
            heapq.heappush(heap, (distance, a, b, True))
            continue
        join(a, b)
        gaps.append({"part_a": a, "part_b": b, "distance_mm": value})
        remaining -= 1
    ordered = sorted((sorted(items) for items in groups.values()), key=lambda items: (start_part not in items, items))
    for items in ordered:
        if start_part in items:
            items.remove(start_part)
            items.insert(0, start_part)
    return {"start_instance": start_part, "contact_groups": ordered, "contact_edges": contacts,
            "distance_edges": gaps, "additional_exact_calculations": calculations,
            "contact_tolerance_mm": tolerance, "layout": "schematic; spacing is not to scale"}


def draw_distance_graph(graph, bom, output, *, part_images=None):
    """Draw compact contact-group stacks and labelled gap connections."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from .image_layout import crop_to_content

    try:
        font = ImageFont.truetype("arial.ttf", 18)
        small = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=15)
    nodes = {item["instance_id"]: item for item in bom["instances"]}
    box_width, box_height = (250, 180) if part_images is not None else (190, 50)
    row_height = box_height + 8
    anchor = box_height / 2
    thumbnails = {}
    if part_images is not None:
        for part_id, path in part_images.items():
            with Image.open(path) as source:
                thumbnails[part_id] = ImageOps.contain(crop_to_content(source, padding=6),
                                                     (box_width-24, box_height-62), Image.Resampling.LANCZOS)
    groups = graph["contact_groups"]
    positions = {}
    x = 55
    for group in groups:
        box_x = x
        for row, key in enumerate(group):
            positions[key] = (box_x, 125 + row * row_height)
        x = box_x + box_width + 150
    bottom = 125 + max(map(len, groups)) * row_height
    image = Image.new("RGB", (max(650, x), bottom + 85 + 38 * len(graph["distance_edges"])), "white")
    draw = ImageDraw.Draw(image)
    draw.text((25, 20), "Part contacts and minimum surface distances", fill="#172334", font=font)
    draw.text((25, 50), f"Start: {graph['start_instance']} | Stacks: connected contact groups (tolerance {graph['contact_tolerance_mm']:g} mm)", fill="#47596a", font=small)
    draw.text((25, 74), "Orange: shortest connections between contact groups | Schematic, not to scale", fill="#864000", font=small)
    for index, edge in enumerate(graph["distance_edges"]):
        a, b = positions[edge["part_a"]], positions[edge["part_b"]]
        if a[0] > b[0]:
            a, b = b, a
        left, right = a[0]+box_width, b[0]
        # Adjacent stacks have an unobstructed gap: route through its centre.
        # Connections across intervening stacks retain an outside route.
        adjacent = not any(left < position[0] < right for position in positions.values())
        if adjacent:
            mid = (left + right) / 2 + index * 4
            y = (a[1] + b[1]) / 2 + anchor
            points = [(left, a[1]+anchor), (mid, a[1]+anchor),
                      (mid, b[1]+anchor), (right, b[1]+anchor)]
        else:
            y = bottom + 25 + index * 38
            left, right = left + 20 + index*3, right - 8 - index*3
            mid = (left + right) / 2
            points = [(a[0]+box_width, a[1]+anchor), (left, a[1]+anchor),
                      (left, y), (right, y), (right, b[1]+anchor), (b[0], b[1]+anchor)]
        draw.line(points, fill="#cf711e", width=3, joint="curve")
        for px, py in (points[0], points[-1]):
            draw.ellipse((px-4, py-4, px+4, py+4), fill="#cf711e")
        label = f"{edge['distance_mm']:.2f} mm"
        width = draw.textlength(label, font=small)
        draw.rectangle((mid-width/2-5, y-12, mid+width/2+5, y+12), fill="white")
        draw.text((mid-width/2, y-10), label, fill="#864000", font=small)
    for key, (x, y) in positions.items():
        draw.rounded_rectangle((x, y, x+box_width, y+box_height), radius=7, fill="#fff0c9" if key == graph["start_instance"] else "#eef3f7", outline="#47596a", width=2)
        draw.text((x+12, y+5), key, fill="#172334", font=font)
        draw.text((x+12, y+29), f"Definition: {nodes[key]['part_id']}", fill="#47596a", font=small)
        if part_images is not None:
            preview = thumbnails.get(nodes[key]["part_id"])
            draw.rectangle((x+12, y+52, x+box_width-12, y+box_height-10), fill="white")
            if preview is not None:
                image.paste(preview, (int(x+(box_width-preview.width)/2), int(y+52+(box_height-62-preview.height)/2)))
            else:
                draw.text((x+24, y+90), "ISO1 image unavailable", fill="#75808b", font=small)
    image.save(output)


def create_distance_diagram(session, *, step_file=None, start_part=None, workspace_root, layout="universe",
                            min_dot_radius=6, max_dot_radius=36):
    """Create diagram artifacts for a saved run, resolving missing exact gaps."""
    import hashlib
    import json
    from pathlib import Path
    from ..io.metadata_manager import write_json

    session = Path(session)
    workspace_root = Path(workspace_root)
    def read(name):
        return json.loads((session / name).read_text(encoding="utf-8-sig"))
    bom, assembly = read("bom.json"), read("assembly.json")
    relations = read("spatial_relations.json")
    interlocking = read("interlocking.json") if (session / "interlocking.json").is_file() else None
    manifest = read("manifest.json")
    loaded = None

    def exact_distance(a, b):
        nonlocal loaded
        if loaded is None:
            source = step_file
            expected = manifest.get("input", {}).get("sha256")
            if source is None:
                name = manifest.get("input", {}).get("name")
                candidates = list((workspace_root / "data/input").rglob(name)) if name else []
                source = next((p for p in candidates if p.is_file() and expected and hashlib.sha256(p.read_bytes()).hexdigest() == expected), None)
            if source is None:
                raise ValueError("Original STEP not found in data/input. Supply --step-file for exact gap distances.")
            if not expected or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError("STEP does not match this run's input hash")
            print(f"Loading original STEP for missing distances: {source}", flush=True)
            from assembly_automation.stepparser.io.step_loader import load_step
            loaded = {i.instance_id: i for i in load_step(source).instances}
            if set(loaded) != {i["instance_id"] for i in bom["instances"]}:
                raise ValueError("Reloaded STEP instances differ from saved BOM; regenerate the parser run")
        from assembly_automation.stepparser.analysis.spatial_relations import compute_spatial_relations
        from assembly_automation.stepparser.settings import SpatialSettings
        print(f"Exact distance: {a} <-> {b}", flush=True)
        result = compute_spatial_relations([loaded[a], loaded[b]], SpatialSettings(
            distance_mode="all_pairs", multithread=relations.get("multithread", True),
            contact_tolerance_mm=relations["contact_tolerance_mm"],
            proximity_threshold_mm=max(relations["contact_tolerance_mm"], relations.get("proximity_threshold_mm", 3))))
        pair = result["pairs"][0]
        if pair["status"] != "complete":
            raise ValueError(pair.get("error", "Exact distance calculation failed"))
        return pair["distance_mm"]

    print(f"Session: {session}", flush=True)
    if layout == "universe":
        from .part_universe import build_part_universe, draw_part_universe
        graph = build_part_universe(bom, assembly, start_part=start_part)
    elif layout == "contacts":
        graph = build_distance_graph(bom, assembly, relations, start_part=start_part, exact_distance=exact_distance)
    else:
        raise ValueError(f"Unknown diagram layout: {layout}")
    image = session / "parts_distance_diagram.png"
    iso_views = {}
    for record in manifest.get("images", []):
        if record.get("category") == "part" and record.get("view") == "iso1" and record.get("transparency", 0) == 0:
            path = session / record["path"]
            if path.is_file():
                iso_views.setdefault(record["part_id"], path)
    graph["iso_views"] = {key: path.relative_to(session).as_posix() for key, path in iso_views.items()}
    missing = sorted({i["part_id"] for i in bom["instances"]} - iso_views.keys())
    if missing:
        print(f"ISO1 images unavailable for: {', '.join(missing)}", flush=True)
    if layout == "universe":
        draw_part_universe(graph, bom, image, part_images=iso_views,
                           relations=relations, interlocking=interlocking,
                           min_dot_radius=min_dot_radius, max_dot_radius=max_dot_radius)
    else:
        draw_distance_graph(graph, bom, image, part_images=iso_views)
    write_json(session / "parts_distance_diagram.json", graph)
    print(f"Saved: {image}")
    if layout == "universe":
        print(f"Reference: {graph['start_instance']}; COM pairs: {len(graph['com_pairs'])}")
    else:
        print(f"Contact groups: {len(graph['contact_groups'])}; additional exact calculations: {graph['additional_exact_calculations']}")
    manifest.setdefault("stages", {})["distance_diagram"] = "complete"
    artifacts = ["parts_distance_diagram.png", "parts_distance_diagram.json"]
    if layout == "universe":
        artifacts.extend([graph["legend_file"], graph["relationship_maps"]["contact_file"],
                          graph["relationship_maps"]["interlock_file"]])
        print(f"Legend: {session / graph['legend_file']}")
    for artifact in artifacts:
        if artifact not in manifest.setdefault("artifacts", []):
            manifest["artifacts"].append(artifact)
    write_json(session / "manifest.json", manifest)
    return graph
