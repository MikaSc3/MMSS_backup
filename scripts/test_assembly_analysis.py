"""Run the new assembly-analysis node on one completed StepParser output."""

import argparse
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))
DEFAULT_SESSION_DIR = (
    WORKSPACE_ROOT
    / "data/stepparser_tests/2026-09-18_190043_317be9cf/003_IPA_Reducer_Case"
)

from assembly_automation.workflows.nodes.assembly_analysis import run_assembly_analysis
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment


def main(argv=None):
    load_project_environment(WORKSPACE_ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_SESSION_DIR,
        help=f"Folder containing assembly.json, bom.json and images/ (default: {DEFAULT_SESSION_DIR})",
    )
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--context-file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    root = args.session_dir.resolve(strict=True)
    output = (args.output or root / "assembly_analysis" / "assembly_overview.json").resolve()
    if output.exists() and not args.overwrite:
        parser.error(f"Output exists; use --overwrite to replace it: {output}")
    config = load_settings(args.config)
    node_settings = config.get("nodes", {}).get("assembly_analysis")
    profiles = config.get("llms", {}).get("profiles")
    if not isinstance(node_settings, dict) or not isinstance(profiles, dict):
        parser.error("Config requires nodes.assembly_analysis and llms.profiles")
    context = {}
    if args.context_file:
        context["user_context"] = args.context_file.read_text(encoding="utf-8")
    artifacts = {
        "assembly": root / "assembly.json",
        "bom": root / "bom.json",
        "spatial_relations": root / "spatial_relations.json",
        "interlocking": root / "interlocking.json",
        "images": root / "images",
    }
    response = run_assembly_analysis(
        artifacts=artifacts,
        settings=node_settings,
        llm_profiles=profiles,
        context=context,
        output_path=output,
    )
    print(f"Result: {response['status']}")
    print(f"Output: {response['artifact']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
