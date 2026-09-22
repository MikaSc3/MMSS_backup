"""Compose ISO1, two complementary views, and a final assembly explosion."""

from collections import defaultdict
from itertools import combinations
from pathlib import Path


def describe_image(path, size):
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        # Crop the near-white background, then normalize scale without distortion.
        pixels = np.asarray(rgb)
        foreground = np.any(pixels < 245, axis=2)
        ys, xs = np.where(foreground)
        if not len(xs):
            return None
        rgb = rgb.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        rgb = ImageOps.pad(rgb, (size, size), color="white", method=Image.Resampling.LANCZOS)
        pixels = np.asarray(rgb, dtype=np.float32) / 255
        mask = np.any(pixels < 245 / 255, axis=2)
        grey = pixels.mean(axis=2)
        dy, dx = np.gradient(grey)
        edges = np.hypot(dx, dy) > 0.08
        # Hue histogram suppresses brightness variation from CAD lighting.
        hsv = np.asarray(rgb.convert("HSV"))
        colorful = mask & (hsv[:, :, 1] > 40)
        counts = np.bincount((hsv[:, :, 0][colorful] // 16).astype(int), minlength=16)
        probabilities = counts[counts > 0] / max(int(counts.sum()), 1)
        entropy = float(-(probabilities * np.log2(probabilities)).sum() / 4)
        return {"mask": mask, "edges": edges, "pixels": pixels, "entropy": entropy}


def pair_metrics(a, b, assembly):
    import numpy as np

    union = a["mask"] | b["mask"]
    silhouette = float(np.count_nonzero(a["mask"] ^ b["mask"]) / max(np.count_nonzero(union), 1))
    # Allow a one-pixel tolerance so antialiasing does not dominate edge distance.
    def dilate(mask):
        padded = np.pad(mask, 1)
        return np.logical_or.reduce([padded[y:y + mask.shape[0], x:x + mask.shape[1]]
                                     for y in range(3) for x in range(3)])
    unmatched = np.count_nonzero(a["edges"] & ~dilate(b["edges"])) + np.count_nonzero(b["edges"] & ~dilate(a["edges"]))
    edge = float(unmatched / max(np.count_nonzero(a["edges"]) + np.count_nonzero(b["edges"]), 1))
    color = float(np.abs(a["pixels"] - b["pixels"])[union].mean()) if union.any() else 0.0
    diversity = 0.35 * silhouette + 0.35 * edge + 0.3 * color if assembly else 0.5 * silhouette + 0.5 * edge
    return {"silhouette_difference": silhouette, "edge_difference": edge,
            "color_difference": color, "diversity": diversity}


def make_collage(paths, labels, target, tile_size, *, crop_whitespace=True, crop_padding_px=12):
    from PIL import Image, ImageDraw, ImageOps

    width, height = tile_size
    images = []
    for path in paths:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            if crop_whitespace:
                from .image_layout import crop_to_content
                rgb = crop_to_content(rgb, crop_padding_px)
            images.append(rgb)
    if crop_whitespace:
        # A shared height and variable widths keep aspect ratios without padded
        # landscape boxes around tall/narrow views. tile_size is a maximum.
        common_height = max(1, int(min(height, *(width * image.height / image.width for image in images))))
        tiles = [image.resize((max(1, round(image.width * common_height / image.height)), common_height),
                              Image.Resampling.LANCZOS) for image in images]
    else:
        tiles = [ImageOps.pad(image, (width, height), color="white", method=Image.Resampling.LANCZOS)
                 for image in images]
    gap = 12
    canvas = Image.new("RGB", (sum(tile.width for tile in tiles) + gap * (len(tiles) - 1),
                               tiles[0].height + 30), "white")
    offset = 0
    for tile, label in zip(tiles, labels):
        canvas.paste(tile, (offset, 30))
        # Clip labels to their own column so narrow views cannot overwrite others.
        label_image = Image.new("RGB", (tile.width, 30), "white")
        ImageDraw.Draw(label_image).text((8, 8), label, fill="black")
        canvas.paste(label_image, (offset, 0))
        offset += tile.width + gap
    canvas.save(target)


def select_images(images, output_dir, settings, progress=None):
    root = Path(output_dir)
    groups = defaultdict(list)
    assembly_exploded_iso1 = None
    highlights = {}
    for record in images:
        path = Path(record["path"])
        if path.name.lower().startswith(("sam_", "collage_")) or record.get("transparency", 0) != 0:
            continue
        category = record.get("category")
        if category == "highlighted":
            part_id = record.get("part_id") or record.get("instance_id", "").split("_copy")[0]
            highlights.setdefault(part_id, record)
            continue
        if category == "exploded" and record.get("view") == "iso1":
            assembly_exploded_iso1 = record
            # Reserve this image for the last panel instead of selecting it twice.
            continue
        if category == "assembly" or (category == "exploded" and settings.include_exploded):
            groups["assembly"].append(record)
        elif category == "part":
            groups[record["part_id"]].append(record)
    results = []
    for group, candidates in sorted(groups.items()):
        candidates = sorted(candidates, key=lambda item: item["path"])
        descriptors = [(record, describe_image(root / record["path"], settings.analysis_size)) for record in candidates]
        valid = [(record, descriptor) for record, descriptor in descriptors if descriptor is not None]
        anchors = [(record, descriptor) for record, descriptor in valid
                   if record.get("view") == "iso1" and record.get("category") != "exploded"]
        if not anchors:
            results.append({"group": group, "status": "skipped", "reason": "missing_nonblank_iso1"})
            continue
        anchor, anchor_descriptor = anchors[0]
        alternatives = [(record, descriptor) for record, descriptor in valid
                        if (record.get("view"), record.get("category")) !=
                        (anchor.get("view"), anchor.get("category"))]
        ranked = []
        assembly = group == "assembly"
        for (left, a), (right, b) in combinations(alternatives, 2):
            if left.get("view") == right.get("view") and left.get("category") == right.get("category"):
                continue
            pairs = [pair_metrics(anchor_descriptor, a, assembly),
                     pair_metrics(anchor_descriptor, b, assembly), pair_metrics(a, b, assembly)]
            differences = [pair["diversity"] for pair in pairs]
            diversity = 0.5 * sum(differences) / 3 + 0.5 * min(differences)
            metrics = {"pairwise": pairs, "diversity": diversity}
            entropy = (a["entropy"] + b["entropy"]) / 2
            weight = settings.assembly_entropy_weight if assembly else 0
            score = (1 - weight) * metrics["diversity"] + weight * entropy
            ranked.append((score, left, right, metrics, entropy))
        if not ranked:
            results.append({"group": group, "status": "skipped", "reason": "fewer_than_two_additional_distinct_views"})
            continue
        score, left, right, metrics, entropy = max(ranked, key=lambda pair: pair[0])
        selected = [anchor, left, right]
        if assembly:
            if assembly_exploded_iso1 is None or describe_image(
                    root / assembly_exploded_iso1["path"], settings.analysis_size) is None:
                results.append({"group": group, "status": "skipped", "reason": "missing_nonblank_iso1_exploded"})
                continue
            selected.append(assembly_exploded_iso1)
        elif group in highlights:
            selected.append(highlights[group])
        relative = Path(anchor["path"]).parent / f"collage_{group}.png"
        make_collage([root / record["path"] for record in selected],
                     [Path(record["path"]).stem for record in selected], root / relative, settings.tile_size,
                     crop_whitespace=settings.crop_whitespace, crop_padding_px=settings.crop_padding_px)
        results.append({"group": group, "status": "complete", "path": relative.as_posix(),
                        "selected_images": [record["path"] for record in selected], "score": score,
                        "metrics": metrics, "mean_color_entropy": entropy,
                        "candidate_count": len(valid), "low_diversity": metrics["diversity"] < 0.03,
                        "highlighted_instance_id": highlights[group].get("instance_id") if not assembly and group in highlights else None,
                        "highlighted_instance_ids": highlights[group].get("highlighted_instance_ids",
                            [highlights[group].get("instance_id")]) if not assembly and group in highlights else [],
                        "method": "iso1_plus_two_then_exploded_v3" if assembly else
                                  "iso1_plus_two_then_highlight_v4" if group in highlights else "iso1_plus_two_complementary_v2"})
        if progress:
            progress("automaticimageselection", len(results), len(groups))
    return results
