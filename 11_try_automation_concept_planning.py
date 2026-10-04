"""Press Run/Play to try automation concept planning on an existing session."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


# ---------------------------------------------------------------------------
# EDIT ONLY THIS SECTION
# ---------------------------------------------------------------------------

SESSION_FOLDER = Path(
    r"C:\Users\Mika\Desktop\apa_from_cad_save\data\sessions\2026-09-28_092612_Stehlager_Sicherungsring_0cdf204e"
)

PLANNING_INSTRUCTION = (
    "Create an automation concept. Prefer high automation for assembly steps "
    "1 and 2, while steps 3 and 4 should remain manual or operator-assisted."
)

# "idea"     = generate only the idea, then stop for review
# "continue" = use the reviewed idea and generate the detailed concept
# "full"     = generate the idea and detailed concept in one run
MODE = "full"

IDEA_REVISION = "idea_r001"
CONCEPT_REVISION = "concept_r001"

# Leave as None to store results inside the session folder.
OUTPUT_FOLDER: Path | None = None

# ---------------------------------------------------------------------------


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
CONFIG_PATH = PROJECT_ROOT / "configs" / "appsettingsv3.yaml"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assembly_automation.workflows.definitions.automation_planning import AutomationPlanningWorkflow
from assembly_automation.workflows.runtime.environment import load_project_environment


def main() -> None:
    if MODE not in {"idea", "continue", "full"}:
        raise ValueError('MODE must be "idea", "continue", or "full"')

    load_project_environment(PROJECT_ROOT)
    settings = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    workflow = AutomationPlanningWorkflow(
        session_root=SESSION_FOLDER,
        output_root=OUTPUT_FOLDER,
        settings=settings,
    )

    idea_path = (
        (OUTPUT_FOLDER or SESSION_FOLDER)
        / "automation_planning"
        / "ideas"
        / IDEA_REVISION
        / "planning_brief.json"
    )

    if MODE in {"idea", "full"}:
        print("\nGenerating automation-planning idea...")
        response = workflow.create_idea(
            PLANNING_INSTRUCTION,
            revision_id=IDEA_REVISION,
        )
        idea_path = Path(response["artifact"])
        print(f"\nIdea ready for review:\n{idea_path}")

    if MODE == "idea":
        print('\nReview the file, then change MODE to "continue" and press Run again.')
        return

    if not idea_path.is_file():
        raise FileNotFoundError(
            f"Reviewed idea not found: {idea_path}\n"
            'Run once with MODE = "idea" first.'
        )

    print("\nPlanning all assembly steps and consolidating the concept...")
    response = workflow.build_concept(
        idea_path=idea_path,
        revision_id=CONCEPT_REVISION,
    )
    print(f"\nAutomation concept ready:\n{response['artifact']}")


if __name__ == "__main__":
    main()
