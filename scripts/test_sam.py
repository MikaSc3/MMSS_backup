"""Run SAM on one existing image without STEP loading or rendering."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys
import time

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE_DIR = WORKSPACE_ROOT / "data/stepparser_tests/2026-09-18_121542_36fd38da/images/assembly"
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.settings import SamSettings
from assembly_automation.stepparser.rendering.sam_segmentation import SamSegmenter
from assembly_automation.workflows.runtime.configuration import load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Override the first image in the default assembly folder")
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--points-per-side", type=int)
    args = parser.parse_args(argv)
    try:
        image = args.image
        if image is None:
            candidates = sorted(p for p in DEFAULT_IMAGE_DIR.iterdir()
                                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")
                                and not p.name.lower().startswith("sam_"))
            if not candidates:
                raise FileNotFoundError(f"No original images in {DEFAULT_IMAGE_DIR}")
            image = candidates[0]
        image = image.resolve(strict=True)
        config = load_settings(args.config)
        values = config.get("nodes", {}).get("step_preprocessing", {}).get("sam", {})
        settings = SamSettings(**values)
        checkpoint = args.checkpoint or Path(settings.checkpoint)
        if not checkpoint.is_absolute():
            checkpoint = WORKSPACE_ROOT / checkpoint
        overrides = {"enabled": True, "checkpoint": str(checkpoint)}
        if args.device is not None:
            overrides["device"] = args.device
        if args.points_per_side is not None:
            overrides["points_per_side"] = args.points_per_side
        settings = replace(settings, **overrides)
        print(f"Input: {image}\nCheckpoint: {checkpoint}\nSAM enabled for this isolated test", flush=True)
        print("Loading model and segmenting one image (CPU can take a while)...", flush=True)
        started = time.monotonic()
        records = SamSegmenter(settings).segment_images(
            [{"path": image.name, "category": "single_image_test"}], image.parent)
        result = records[0]
        print(f"Device: {result['device']} | Masks: {result['mask_count']} | "
              f"Time: {time.monotonic() - started:.2f}s", flush=True)
        print(f"Output: {image.parent / result['path']}", flush=True)
        if not result["mask_count"]:
            print("No masks detected; try lowering the SAM filtering thresholds in the config.")
        return 0
    except Exception as exc:
        print(f"SAM test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
