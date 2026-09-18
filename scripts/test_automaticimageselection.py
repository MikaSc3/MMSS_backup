"""Create collages from an existing parser run without rerendering or SAM."""

import argparse
import json
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.settings import ImageSelectionSettings
from assembly_automation.stepparser.rendering.automaticimageselection import select_images
from assembly_automation.stepparser.io.metadata_manager import write_json
from assembly_automation.workflows.runtime.configuration import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, default=WORKSPACE_ROOT / "data/stepparser_tests/2026-09-18_121542_36fd38da")
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    args = parser.parse_args()
    try:
        manifest = json.loads((args.session_dir / "manifest.json").read_text(encoding="utf-8-sig"))
        config = load_settings(args.config)
        values = config.get("nodes", {}).get("step_preprocessing", {}).get("automaticimageselection", {})
        settings = ImageSelectionSettings(**values)
        records = select_images(manifest["images"], args.session_dir, settings)
        write_json(args.session_dir / "image_selection.json", records)
        for item in records:
            print(f"{item['group']}: {item['status']} " + str(item.get("selected_images", item.get("reason"))))
        print(f"Collages saved in: {args.session_dir / 'images'}")
        return 0
    except Exception as exc:
        print(f"Image selection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
