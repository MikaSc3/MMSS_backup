"""Orbit diagram driven by COM distances, with separate boxes for copies."""

from math import atan2, cos, dist, isfinite, pi, sin
from ..analysis.center_of_mass import com_distances


def volume_marker_sizes(bom, min_radius=6, max_radius=36):
    """Min-max normalize volume, then interpolate marker area within bounds."""
    if not isfinite(min_radius) or not isfinite(max_radius) or not 0 < min_radius <= max_radius:
        raise ValueError("Dot radii must be finite and 0 < minimum <= maximum")
    definitions = {part["part_id"]: part for part in bom.get("parts", [])}
    volumes = {node["instance_id"]: definitions.get(node["part_id"], {}).get("geometry", {}).get("volume")
               for node in bom["instances"]}
    available = [v for v in volumes.values() if v is not None and isfinite(v) and v >= 0]
    low, high = (min(available), max(available)) if available else (None, None)
    sizes = {}
    for key, volume in volumes.items():
        valid = volume is not None and isfinite(volume) and volume >= 0
        normalized = ((volume-low)/(high-low) if high > low else .5) if valid else None
        radius = (min_radius**2 + (normalized or 0)*(max_radius**2-min_radius**2)) ** .5
        sizes[key] = {"volume_mm3": volume, "normalized_volume": normalized, "radius_px": radius}
    return sizes, {"minimum_volume_mm3": low, "maximum_volume_mm3": high,
                   "minimum_radius_px": min_radius, "maximum_radius_px": max_radius,
                   "mapping": "min-max normalized volume to marker area", "equal_volume_normalized_value": .5,
                   "missing_volume": "minimum radius"}


def group_overlapping_markers(positions, threshold_px=18, *, radii=None):
    """Group visually overlapping points, including numerical near-coincidence.

    Limit every group's diameter so a chain of neighbours cannot collapse a
    large region into one marker. Original measurement coordinates stay intact.
    """
    groups = []
    for key, point in sorted(positions.items()):
        for group in groups:
            if all(dist(point, positions[member]) <= (radii[key]+radii[member]+2 if radii else threshold_px) for member in group):
                group.append(key)
                break
        else:
            groups.append([key])
    return groups


def build_part_universe(bom, assembly, *, start_part=None):
    nodes = {i["instance_id"]: i for i in bom["instances"]}
    if not nodes:
        raise ValueError("No instances in BOM")
    for key, item in nodes.items():
        point = item.get("center_of_mass")
        if point is None or len(point) != 3 or not all(isfinite(v) for v in point):
            raise ValueError(f"No finite assembly-coordinate COM for {key}")
    seed = assembly.get("geometry", {}).get("center_of_mass")
    if seed is None or len(seed) != 3 or not all(isfinite(v) for v in seed):
        raise ValueError("Assembly COM unavailable")
    reference = start_part or min(nodes, key=lambda key: (dist(seed, nodes[key]["center_of_mass"]), key))
    if reference not in nodes:
        raise ValueError(f"Unknown starting instance: {reference}")
    origin = nodes[reference]["center_of_mass"]
    from ..core.native_libraries import prepare_conda_libraries
    prepare_conda_libraries()
    import numpy as np

    keys = sorted(nodes)
    pairs = com_distances([nodes[key] for key in keys])
    indices = {key: i for i, key in enumerate(keys)}
    distances = np.zeros((len(keys), len(keys)))
    for pair in pairs:
        a, b = indices[pair["part_a"]], indices[pair["part_b"]]
        distances[a, b] = distances[b, a] = pair["distance_mm"]
    # Classical multidimensional scaling uses the entire distance matrix.
    squared = distances ** 2
    gram = -.5 * (squared - squared.mean(axis=0)[None, :]
                  - squared.mean(axis=1)[:, None] + squared.mean())
    values, vectors = np.linalg.eigh(gram)
    dimensions = min(2, len(keys))
    projected = np.zeros((len(keys), 2))
    projected[:, :dimensions] = vectors[:, -dimensions:] * np.sqrt(np.maximum(values[-dimensions:], 0))
    projected = projected[:, ::-1]
    for axis in range(2):
        if projected[np.argmax(np.abs(projected[:, axis])), axis] < 0:
            projected[:, axis] *= -1
    projected -= projected[indices[reference]].copy()
    extent = np.max(np.abs(projected), axis=0)
    limits = [500 / extent[0] if extent[0] > 1e-9 else float("inf"),
              300 / extent[1] if extent[1] > 1e-9 else float("inf")]
    scale = min(limits)
    if not isfinite(scale):
        scale = 1.
    # One scale for both axes, with no collision displacement of COM markers.
    positions = {key: (projected[indices[key]] * scale).tolist() for key in keys}
    orbits = []
    for key, position in positions.items():
        if key == reference:
            continue
        orbits.append({"instance_id": key, "com_distance_to_reference_mm": dist(origin, nodes[key]["center_of_mass"]),
                       "com_distance_to_assembly_mm": dist(seed, nodes[key]["center_of_mass"]),
                       "radius_px": dist([0, 0], position), "angle_radians": atan2(position[1], position[0])})
    projected_distances = np.linalg.norm(projected[:, None, :] - projected[None, :, :], axis=2)
    denominator = float(np.sum(distances**2))
    stress = float(np.sqrt(np.sum((projected_distances-distances)**2) / denominator)) if denominator else 0.
    return {"layout": "part_universe", "unit": "mm", "coordinate_frame": "assembly",
            "start_instance": reference, "reference_selection": "manual" if start_part else "nearest_assembly_com", "assembly_com": seed, "reference_com": origin,
            "reference_distance_to_assembly_com_mm": dist(seed, origin),
            "placement_method": "classical_MDS_all_pair_COM_distances_uniform_scale",
            "projected_positions_mm": {key: projected[indices[key]].tolist() for key in keys},
            "projection_normalized_distance_error": stress, "pixels_per_projected_mm": scale,
            "positions": positions, "orbits": orbits, "com_pairs": pairs,
            "layout_note": "COM markers use one linear scale with no offsets. ISO cards are a separate numbered gallery. Projection can shorten 3D distances; labels retain exact 3D values."}


def draw_part_universe(graph, bom, output, *, part_images, relations=None, interlocking=None,
                       min_dot_radius=6, max_dot_radius=36):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from .image_layout import crop_to_content

    try:
        font = ImageFont.truetype("arial.ttf", 18)
        small = ImageFont.truetype("arial.ttf", 14)
        inside_font = ImageFont.truetype("arial.ttf", 12)
    except OSError:
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=14)
        inside_font = ImageFont.load_default(size=12)
    nodes = {i["instance_id"]: i for i in bom["instances"]}
    sizes, size_scale = volume_marker_sizes(bom, min_dot_radius, max_dot_radius)
    dot_radii = {key: item["radius_px"] for key, item in sizes.items()}
    graph["marker_sizes"] = sizes
    graph["marker_size_scale"] = size_scale
    from math import ceil, floor, log10
    positions = graph["positions"]
    reference_key = graph["start_instance"]
    keys = [reference_key] + sorted(key for key in nodes if key != reference_key)
    numbers = {key: index for index, key in enumerate(keys, 1)}
    width, map_bottom = 1200, 760
    columns, card_width, card_height = 5, 220, 198
    gallery_y = 55
    rows = ceil(len(keys) / columns)
    image = Image.new("RGB", (width, map_bottom+15), "white")
    draw = ImageDraw.Draw(image)
    cx, cy = 600, 365
    scale = graph["pixels_per_projected_mm"]
    radii = sorted(set(round(o["radius_px"], 5) for o in graph["orbits"] if o["radius_px"] > 1e-5))
    for radius in radii:
        # Keep orbit decoration inside the map panel; marker positions stay exact.
        if radius <= 340:
            draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline="#e5eaf0", width=1)
    clusters = {tuple(positions[members[0]]): members for members in group_overlapping_markers(positions, radii=dot_radii)}
    graph["marker_groups"] = [{"instance_ids": members, "display_anchor_px": list(position)}
                              for position, members in clusters.items()]
    graph["marker_grouping"] = "pairwise marker radii plus 2 pixels"
    definitions = {part["part_id"]: part for part in bom.get("parts", [])}
    colors = {}
    for key, node in nodes.items():
        rgb = node.get("color") or definitions.get(node["part_id"], {}).get("color") or [54, 103, 134]
        colors[key] = tuple(int(max(0, min(255, value))) for value in rgb)

    def marker(px, py, members, target=None):
        painter = target or draw
        radius = max(dot_radii[key] for key in members)
        bounds = (px-radius, py-radius, px+radius, py+radius)
        if len(members) == 1:
            painter.ellipse(bounds, fill=colors[members[0]], outline="#47596a", width=1)
        else:
            for index, key in enumerate(members):
                painter.pieslice(bounds, 360*index/len(members), 360*(index+1)/len(members), fill=colors[key], outline="white", width=1)
            painter.ellipse(bounds, outline="#47596a", width=1)

    labels = []
    label_placements = []
    marker_bounds = []
    for position, members in clusters.items():
        r = max(dot_radii[key] for key in members)
        px, py = cx+position[0], cy+position[1]
        marker_bounds.append((px-r, py-r, px+r, py+r))
        draw.line((cx, cy, px, py), fill="#ecd7b8", width=1)
    # Draw all markers above connection lines and below labels.
    for position, members in clusters.items():
        marker(cx+position[0], cy+position[1], members)
    for position, members in sorted(clusters.items()):
        px, py = cx+position[0], cy+position[1]
        ordered = sorted(members, key=lambda key: numbers[key])
        lines = [", ".join(ordered[index:index+2]) for index in range(0, len(ordered), 2)]
        label = "\n".join(lines)
        text_width = max(draw.textlength(line, font=small) for line in lines)
        label_height = len(lines)*18+6
        marker_radius = max(dot_radii[key] for key in members)
        inside_box = draw.multiline_textbbox((0, 0), label, font=inside_font, spacing=2)
        inside_width = inside_box[2]-inside_box[0]+6
        inside_height = inside_box[3]-inside_box[1]+6
        # The four box corners must remain inside the circle. Combined labels
        # are allowed too, provided the complete compact multiline box fits.
        fits_inside = ((inside_width/2)**2 + (inside_height/2)**2) ** .5 <= marker_radius-3
        if fits_inside:
            lx, ly = px-inside_width/2, py-inside_height/2
            bounds = (lx, ly, lx+inside_width, ly+inside_height)
            labels.append(bounds)
            draw.rounded_rectangle(bounds, radius=4, fill="#f8fafc", outline="#75899a")
            draw.multiline_text((lx+3-inside_box[0], ly+3-inside_box[1]), label,
                                font=inside_font, fill="#172334", spacing=2)
            label_placements.append({"instance_ids": ordered, "placement": "inside_marker",
                                     "label": label, "bounds": list(bounds),
                                     "text_position": [lx+3-inside_box[0], ly+3-inside_box[1]]})
            continue
        gap = marker_radius + 6
        lx, ly = px+gap, py-12
        lx = max(10, min(lx, width-text_width-20))
        ly = max(20, min(ly, map_bottom-label_height-50))
        # Labels can move with leader lines; COM markers never move.
        step = 0
        while any(lx < right+3 and lx+text_width+10 > left-3 and ly < bottom+3 and ly+label_height > top-3 for left, top, right, bottom in labels+marker_bounds):
            step += 1
            if step > 400:
                # Bounded search avoids getting trapped at clamped panel edges.
                available = [(gx, gy) for gy in range(25, int(map_bottom-label_height-50), int(label_height+12))
                             for gx in range(10, int(width-text_width-20), 20)
                             if not any(gx < right+6 and gx+text_width+10 > left-6
                                        and gy < bottom+5 and gy+label_height > top-5
                                        for left, top, right, bottom in labels+marker_bounds)]
                if available:
                    lx, ly = min(available, key=lambda point: dist(point, [px, py]))
                break
            angle = step * pi * (3-5**.5)
            offset = 12 * step**.5
            lx, ly = px+gap+offset*cos(angle), py-12+offset*sin(angle)
            lx = max(10, min(lx, width-text_width-20))
            ly = max(20, min(ly, map_bottom-label_height-50))
        labels.append((lx, ly, lx+text_width+10, ly+label_height))
        draw.line((px, py, lx, ly+12), fill="#9daebb", width=1)
        draw.rounded_rectangle(labels[-1], radius=4, fill="#eef3f7", outline="#bac6d0")
        draw.multiline_text((lx+5, ly+3), label, font=small, fill="#172334", spacing=3)
        label_placements.append({"instance_ids": ordered, "placement": "external",
                                 "label": label, "bounds": list(labels[-1]),
                                 "text_position": [lx+5, ly+3]})
    graph["label_placements"] = label_placements
    # A 1/2/5 scale bar in projected millimetres.
    nominal = 120 / scale
    magnitude = 10 ** floor(log10(nominal))
    bar_mm = min((factor*magnitude for factor in (1, 2, 5, 10)), key=lambda value: abs(value-nominal))
    bar_px = bar_mm*scale
    y = map_bottom-25
    draw.line((35, y, 35+bar_px, y), fill="#172334", width=3)
    draw.line((35, y-5, 35, y+5), fill="#172334", width=2)
    draw.line((35+bar_px, y-5, 35+bar_px, y+5), fill="#172334", width=2)
    draw.text((35, y-24), f"{bar_mm:g} mm (2D projection)", font=small, fill="#172334")
    map_image = crop_to_content(image, padding=25)

    def relationship_map(kind):
        layer = Image.new("RGB", (width, map_bottom+15), "white")
        pen = ImageDraw.Draw(layer)
        if kind == "contacts":
            edges = [(pair["part_a"], pair["part_b"], None) for pair in (relations or {}).get("pairs", [])
                     if pair.get("status") == "complete" and pair.get("classification") == "contact_or_overlap"]
            color = "#7b8793"
        else:
            edges = [(edge["blocker"], edge["blocked_part"], edge) for edge in (interlocking or {}).get("blocker_edges", [])]
            color = "#7437a8"
        for left, right, metadata in edges:
            if left not in positions or right not in positions:
                continue
            x1, y1 = cx+positions[left][0], cy+positions[left][1]
            x2, y2 = cx+positions[right][0], cy+positions[right][1]
            width_px = 2 if metadata is None else max(2, round(2+4*metadata.get("strength", 0)))
            pen.line((x1, y1, x2, y2), fill=color, width=width_px)
            if metadata is not None:
                angle = atan2(y2-y1, x2-x1)
                radius = dot_radii[right]+3
                tip = (x2-radius*cos(angle), y2-radius*sin(angle))
                side = 8+width_px
                pen.polygon([tip,
                             (tip[0]-side*cos(angle-pi/6), tip[1]-side*sin(angle-pi/6)),
                             (tip[0]-side*cos(angle+pi/6), tip[1]-side*sin(angle+pi/6))], fill=color)
        for position, members in clusters.items():
            marker(cx+position[0], cy+position[1], members, pen)
        for placement in label_placements:
            bounds = placement["bounds"]
            pen.rounded_rectangle(bounds, radius=4, fill="#f8fafc", outline="#75899a")
            pen.multiline_text(placement["text_position"], placement["label"],
                               font=inside_font if placement["placement"] == "inside_marker" else small,
                               fill="#172334", spacing=2 if placement["placement"] == "inside_marker" else 3)
        pen.line((35, map_bottom-25, 35+bar_px, map_bottom-25), fill="#172334", width=3)
        pen.text((35, map_bottom-49), f"{bar_mm:g} mm", font=small, fill="#172334")
        return crop_to_content(layer, padding=25), len(edges)

    contact_map, contact_count = relationship_map("contacts")
    interlock_map, interlock_count = relationship_map("interlocks")
    graph["relationship_maps"] = {"contact_edges": contact_count, "blocking_edges": interlock_count,
                                  "contact_file": "part_contact_map.png",
                                  "interlock_file": "part_interlock_map.png"}
    image = Image.new("RGB", (width, gallery_y+rows*(card_height+12)+25), "white")
    draw = ImageDraw.Draw(image)
    draw.text((25, 20), "ISO1 part legend | Labels show exact 3D COM distance to the reference", font=font, fill="#172334")
    distances = {o["instance_id"]: o["com_distance_to_reference_mm"] for o in graph["orbits"]}
    previews = {}
    for part_id, path in part_images.items():
        with Image.open(path) as source:
            previews[part_id] = ImageOps.contain(crop_to_content(source, padding=6), (196, 118), Image.Resampling.LANCZOS)
    for index, key in enumerate(keys):
        x = 25 + (index % columns)*230
        y = gallery_y + (index // columns)*210
        draw.rounded_rectangle((x, y, x+card_width, y+card_height), radius=9, fill="#f1f5f8", outline=colors[key], width=2)
        draw.text((x+10, y+6), f"{numbers[key]}. {key}", font=font, fill="#172334")
        draw.text((x+10, y+30), f"Definition: {nodes[key]['part_id']}", font=small, fill="#47596a")
        draw.rectangle((x+12, y+51, x+208, y+169), fill="white")
        preview = previews.get(nodes[key]["part_id"])
        if preview is not None:
            image.paste(preview, (x+12+(196-preview.width)//2, y+51+(118-preview.height)//2))
        else:
            draw.text((x+20, y+90), "ISO1 unavailable", font=small, fill="#75808b")
        draw.text((x+12, y+177), f"{distances.get(key, 0):.2f} mm COM to reference", font=small, fill="#864000")
    # Replace the file after encoding, avoiding a partial PNG and supporting
    # viewers that permit replacing an open image but deny writing into it.
    import os
    from pathlib import Path
    import uuid
    output = Path(output)
    legend = output.with_name("parts_universe_legend.png")
    contact_path = output.with_name("part_contact_map.png")
    interlock_path = output.with_name("part_interlock_map.png")
    for target, raster in ((output, map_image), (legend, image),
                           (contact_path, contact_map), (interlock_path, interlock_map)):
        temporary = target.with_name(f".{target.stem}_{uuid.uuid4().hex}.png")
        try:
            raster.save(temporary, format="PNG")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    graph["legend_file"] = legend.name
