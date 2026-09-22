"""Visualize an existing STEP-parser run; defaults to the latest complete run."""

import argparse
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.stepparser.rendering.distance_diagram import create_distance_diagram


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--step-file", type=Path, help="Original STEP, required only for missing exact gap distances")
    parser.add_argument("--start-part", help="Placed instance ID, e.g. part_001; defaults to closest COM")
    parser.add_argument("--layout", choices=("universe", "contacts"), default="universe")
    args = parser.parse_args()
    try:
        session = args.session_dir
        if session is None:
            root = WORKSPACE_ROOT / "data/stepparser_tests"
            candidates = sorted((p.parent for p in root.rglob("manifest.json")),
                                key=lambda p: p.relative_to(root).parts, reverse=True)
            session = next((p for p in candidates if all((p / name).is_file() for name in ("bom.json", "assembly.json", "spatial_relations.json"))), None)
            if session is None:
                raise ValueError("No parser run found; use --session-dir")
        create_distance_diagram(session, step_file=args.step_file, start_part=args.start_part, workspace_root=WORKSPACE_ROOT, layout=args.layout)
        return 0
    except Exception as exc:
        print(f"Distance diagram failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
