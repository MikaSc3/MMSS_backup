"""Root launcher for the agent-driven app workflow v3 terminal runner."""

from __future__ import annotations

from typing import Optional

import scripts.app_workflow_v3 as app_workflow_v3


# ============================================================================
# CONFIGURATION: edit V3 terminal runs here
# ============================================================================

MASTER_STEP_INPUT_FOLDER: str = "data/input/test"
STEPPARSER_OUTPUT_FOLDER: str = "data/processed/stepparser10"
LLM_OUTPUT_FOLDER: str = "data/datapreparation/NEWFILESAGENT"
TEXTBASED_ADDITIONAL_DATA: str = "data/input/Textbased_Data"
EXPERIMENT_CONFIG_FOLDER: str = "configs/appconfig"
EXPERIMENT_CONFIG_NAME: Optional[str] = "appconfigV2"
TERMINAL_INTERACTIVE: bool = True  # True = answer agents in terminal, False = auto-mode

# ============================================================================


def _apply_terminal_config() -> None:
    app_workflow_v3.MASTER_STEP_INPUT_FOLDER = MASTER_STEP_INPUT_FOLDER
    app_workflow_v3.STEPPARSER_OUTPUT_FOLDER = STEPPARSER_OUTPUT_FOLDER
    app_workflow_v3.LLM_OUTPUT_FOLDER = LLM_OUTPUT_FOLDER
    app_workflow_v3.TEXTBASED_ADDITIONAL_DATA = TEXTBASED_ADDITIONAL_DATA
    app_workflow_v3.EXPERIMENT_CONFIG_FOLDER = EXPERIMENT_CONFIG_FOLDER
    app_workflow_v3.EXPERIMENT_CONFIG_NAME = EXPERIMENT_CONFIG_NAME
    app_workflow_v3.TERMINAL_INTERACTIVE = TERMINAL_INTERACTIVE


def main() -> int:
    _apply_terminal_config()
    return app_workflow_v3.main()


if __name__ == "__main__":
    raise SystemExit(main())
