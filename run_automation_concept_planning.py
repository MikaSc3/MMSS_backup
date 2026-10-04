"""Run post-FFA automation concept planning on an existing session."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml


WORKSPACE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = WORKSPACE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assembly_automation.workflows.definitions.automation_planning import AutomationPlanningWorkflow
from assembly_automation.workflows.runtime.environment import load_project_environment


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Plan an automation concept from a completed FFA session")
    value.add_argument("--session-root", type=Path, required=True)
    source = value.add_mutually_exclusive_group(required=True)
    source.add_argument("--instruction",
                        help="Desired automation boundary, priorities, and constraints")
    source.add_argument("--idea-path", type=Path,
                        help="Previously reviewed planning_brief.json to continue from")
    value.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    value.add_argument("--output-root", type=Path,
                       help="Optional sidecar output root; defaults to the source session")
    value.add_argument("--idea-only", action="store_true",
                       help="Stop at the idea-review checkpoint")
    value.add_argument("--idea-revision", default="idea_r001")
    value.add_argument("--concept-revision", default="concept_r001")
    return value


def main() -> int:
    args = parser().parse_args()
    load_project_environment(WORKSPACE_ROOT)
    settings = yaml.safe_load(args.config.resolve(strict=True).read_text(encoding="utf-8"))
    workflow = AutomationPlanningWorkflow(
        session_root=args.session_root.resolve(strict=True), settings=settings,
        output_root=args.output_root)
    if args.idea_path:
        idea_path = args.idea_path.resolve(strict=True)
    else:
        idea = workflow.create_idea(args.instruction, revision_id=args.idea_revision)
        idea_path = Path(idea["artifact"])
        print(f"Automation idea: {idea_path}")
        if args.idea_only:
            print("Stopped at the automation-idea review checkpoint.")
            return 0
    concept = workflow.build_concept(idea_path=idea_path, revision_id=args.concept_revision)
    print(f"Automation concept: {concept['artifact']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
