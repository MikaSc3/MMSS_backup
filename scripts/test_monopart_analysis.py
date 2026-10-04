"""Run the new monopart-analysis node on one or all unique parts."""

import argparse
import json
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))
DEFAULT_SESSION_DIR = WORKSPACE_ROOT / "data/stepparser_tests/2026-09-18_190043_317be9cf/003_IPA_Reducer_Case"

from assembly_automation.workflows.nodes.monopart_analysis import run_monopart_analysis
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment


def main(argv=None):
    load_project_environment(WORKSPACE_ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", nargs="?", type=Path, default=DEFAULT_SESSION_DIR)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--part-id", default="part_001")
    selection.add_argument("--all", action="store_true", help="Run one model call for every unique BOM part")
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    parser.add_argument("--context-file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    root = args.session_dir.resolve(strict=True)
    config = load_settings(args.config)
    settings = config.get("nodes", {}).get("monopart_analysis")
    profiles = config.get("llms", {}).get("profiles")
    if not isinstance(settings, dict) or not isinstance(profiles, dict):
        parser.error("Config requires nodes.monopart_analysis and llms.profiles")
    bom_path = root / "bom.json"
    bom = json.loads(bom_path.read_text(encoding="utf-8"))
    available = [part["part_id"] for part in bom.get("parts", [])]
    selected = available if args.all else [args.part_id]
    unknown = [part_id for part_id in selected if part_id not in available]
    if unknown:
        parser.error(f"Unknown part IDs {unknown}; available: {available}")

    artifacts = {"bom": bom_path, "images": root / "images"}
    overview = root / "assembly_analysis/assembly_overview.json"
    if overview.is_file():
        artifacts["assembly_overview"] = overview
    context = {}
    if args.context_file:
        context["user_context"] = args.context_file.read_text(encoding="utf-8")

    for index, part_id in enumerate(selected, 1):
        output = root / "monopart_analysis/parts" / f"{part_id}.json"
        if output.exists() and not args.overwrite:
            parser.error(f"Output exists; use --overwrite to replace it: {output}")
        print(f"[{index}/{len(selected)}] {part_id}", flush=True)
        response = run_monopart_analysis(part_id=part_id, artifacts=artifacts,
                                         settings=settings, llm_profiles=profiles,
                                         context=context, output_path=output)
        print(f"Output: {response['artifact']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
