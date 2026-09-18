"""Volume/saturation behavior without mutating Python's global RNG."""

import colorsys
import hashlib
import random


def assign_colors(definitions, instances, mode="geometry"):
    if mode not in ("geometry", "different"):
        raise ValueError(f"Unknown color mode: {mode}")
    ordered = sorted(definitions, key=lambda d: (d.geometry.get("volume") or 0, d.part_id))
    if not ordered:
        return
    volumes = [d.geometry.get("volume") or 0 for d in ordered]
    low, high = min(volumes), max(volumes)
    hues = [320 * index / len(ordered) for index in range(len(ordered))]
    hues = [hue if hue < 290 else hue + 40 for hue in hues]
    random.Random(42).shuffle(hues)
    by_id = {d.part_id: d for d in definitions}

    def color(volume, hue):
        normalized = (volume - low) / (high - low) if high > low else 0.5
        saturation = 1.0 if normalized < 0.1 else (0.9 if normalized < 0.6 else 0.6)
        return [int(v * 255) for v in colorsys.hsv_to_rgb(hue / 360, saturation, 0.85)]

    for definition, hue in zip(ordered, hues):
        definition.color = color(definition.geometry.get("volume") or 0, hue)
    for instance in instances:
        definition = by_id[instance.part_id]
        if mode == "geometry":
            instance.color = list(definition.color)
        else:
            hue = (int(hashlib.sha256(instance.instance_id.encode()).hexdigest(), 16) % 1000000) / 1000000 * 320
            instance.color = color(definition.geometry.get("volume") or 0, hue if hue < 290 else hue + 40)
