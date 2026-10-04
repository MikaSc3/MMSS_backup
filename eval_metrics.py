"""Generate metrics and charts from an existing eval_system experiment run."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval_system import DEFAULT_FFA_GT, _evaluate, _write_json


def _metadata(run_root: Path) -> tuple[Path, dict]:
    run_root = run_root.resolve(strict=True)
    path = run_root / "run_metadata.json"
    if not path.is_file():
        raise FileNotFoundError(f"Not an eval_system run (run_metadata.json missing): {run_root}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid run metadata: {path}")
    return run_root, value


def generate_metrics(run_root: Path, gt_root: Path) -> dict:
    run_root, metadata = _metadata(run_root)
    assemblies = metadata.get("assemblies")
    repetitions = metadata.get("repetitions")
    if not isinstance(assemblies, list) or not all(isinstance(item, str) for item in assemblies):
        raise ValueError("run_metadata.json has no valid assemblies list")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("run_metadata.json has no valid repetition count")

    result = _evaluate(run_root, assemblies, repetitions, gt_root.resolve(strict=True))
    metadata["evaluation"] = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ffa_ground_truth_root": str(gt_root.resolve()),
        "rows": result["rows"],
        "missing_ffa_ground_truth": result["missing_gt"],
        "errors": result["errors"],
    }
    _write_json(run_root / "run_metadata.json", metadata)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_folder", type=Path,
                        help="Completed data/evaluations/<timestamp>_<name> folder")
    parser.add_argument("--ffa-gt-root", type=Path, default=DEFAULT_FFA_GT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = generate_metrics(args.run_folder, args.ffa_gt_root)
    except Exception as exc:
        print(f"Metrics generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Metrics generated in: {args.run_folder.resolve() / 'evaluation'}")
    print(f"Evaluated run/assembly pairs: {result['rows']}")
    if result["missing_gt"]:
        print(f"Assemblies without FFA ground truth: {', '.join(result['missing_gt'])}")
    if result["errors"]:
        print(f"Evaluation errors: {len(result['errors'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
