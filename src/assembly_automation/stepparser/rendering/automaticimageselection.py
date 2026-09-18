"""Select complementary original CAD views and compose two-image collages."""

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


def make_collage(paths, labels, target, tile_size):
    from PIL import Image, ImageDraw, ImageOps

    width, height = tile_size
    canvas = Image.new("RGB", (width * 2, height + 30), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (path, label) in enumerate(zip(paths, labels)):
        with Image.open(path) as image:
            tile = ImageOps.pad(image.convert("RGB"), (width, height), color="white",
                                method=Image.Resampling.LANCZOS)
        canvas.paste(tile, (index * width, 30))
        draw.text((index * width + 8, 8), label, fill="black")
    canvas.save(target)


def select_images(images, output_dir, settings, progress=None):
    root = Path(output_dir)
    groups = defaultdict(list)
    for record in images:
        path = Path(record["path"])
        if path.name.lower().startswith(("sam_", "collage_")) or record.get("transparency", 0) != 0:
            continue
        category = record.get("category")
        if category == "assembly" or (category == "exploded" and settings.include_exploded):
            groups["assembly"].append(record)
        elif category == "part":
            groups[record["part_id"]].append(record)
    results = []
    for group, candidates in sorted(groups.items()):
        candidates = sorted(candidates, key=lambda item: item["path"])
        descriptors = [(record, describe_image(root / record["path"], settings.analysis_size)) for record in candidates]
        valid = [(record, descriptor) for record, descriptor in descriptors if descriptor is not None]
        if len(valid) < 2:
            results.append({"group": group, "status": "skipped", "reason": "fewer_than_two_nonblank_views"})
            continue
        ranked = []
        assembly = group == "assembly"
        for (left, a), (right, b) in combinations(valid, 2):
            if left.get("view") == right.get("view") and left.get("category") == right.get("category"):
                continue
            metrics = pair_metrics(a, b, assembly)
            entropy = (a["entropy"] + b["entropy"]) / 2
            weight = settings.assembly_entropy_weight if assembly else 0
            score = (1 - weight) * metrics["diversity"] + weight * entropy
            ranked.append((score, left, right, metrics, entropy))
        if not ranked:
            results.append({"group": group, "status": "skipped", "reason": "fewer_than_two_distinct_view_names"})
            continue
        score, left, right, metrics, entropy = max(ranked, key=lambda pair: pair[0])
        relative = Path(left["path"]).parent / f"collage_{group}.png"
        make_collage([root / left["path"], root / right["path"]],
                     [Path(left["path"]).stem, Path(right["path"]).stem], root / relative, settings.tile_size)
        results.append({"group": group, "status": "complete", "path": relative.as_posix(),
                        "selected_images": [left["path"], right["path"]], "score": score,
                        "metrics": metrics, "mean_color_entropy": entropy,
                        "candidate_count": len(valid), "low_diversity": metrics["diversity"] < 0.03,
                        "method": "silhouette_edges_color_v1"})
        if progress:
            progress("automaticimageselection", len(results), len(groups))
    return results
