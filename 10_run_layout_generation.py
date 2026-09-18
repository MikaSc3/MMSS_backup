"""Generate box-based station and overall layouts from automation planner output."""

from __future__ import annotations

import argparse
from pathlib import Path


# Edit this value for quick terminal iteration, or pass --automation-planner-dir.
AUTOMATION_PLANNER_DIR = Path(
    r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\sessions_v3"
    r"\2026-06-12_082233_Stehlager_Sicherungsring\automation_planner"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render station and overall box layouts from module 03 variant JSON files."
    )
    parser.add_argument(
        "--automation-planner-dir",
        type=Path,
        default=AUTOMATION_PLANNER_DIR,
        help="Directory containing 03_automatisierungsvarianten",
    )
    parser.add_argument(
        "--strategy",
        action="append",
        choices=("manuell", "halbautomatisiert", "vollautomatisiert"),
        help="Render only this strategy; repeat to select multiple strategies",
    )
    parser.add_argument("--pixels-per-cm", type=float, default=4.0)
    parser.add_argument("--padding-cm", type=float, default=25.0)
    parser.add_argument("--box-width-cm", type=float, default=30.0)
    parser.add_argument("--box-height-cm", type=float, default=18.0)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    from agent.layout_generator import DEFAULT_STRATEGIES, LayoutConfig, generate_layouts_from_directory

    config = LayoutConfig(
        pixels_per_cm=args.pixels_per_cm,
        padding_cm=args.padding_cm,
        equipment_width_cm=args.box_width_cm,
        equipment_height_cm=args.box_height_cm,
    )
    strategies = tuple(args.strategy) if args.strategy else DEFAULT_STRATEGIES
    results = generate_layouts_from_directory(
        args.automation_planner_dir,
        strategies=strategies,
        config=config,
    )

    failed = False
    print(f"\nLayouts: {Path(args.automation_planner_dir).resolve() / '03a_layouts'}")
    for strategy, result in results.items():
        status = result.get("status", "unknown")
        if status == "ok":
            print(
                f"  {strategy}: OK - {len(result.get('station_images', []))} station image(s), "
                f"{len(result.get('warnings', []))} warning(s)"
            )
        else:
            failed = status == "error" or failed
            print(f"  {strategy}: {status.upper()} - {result.get('reason', 'unknown reason')}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
