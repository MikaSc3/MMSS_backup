"""Run the automation planner on an existing App V3 session."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional


# ============================================================================
# CONFIGURATION: edit the terminal test run here
# ============================================================================

SESSION_ROOT: str = (
    r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\sessions_v3"
    r"\2026-06-12_082233_Stehlager_Sicherungsring"
)

AUTOMATION_PLANNER_CONFIG: str = "configs/automationplanner.yaml"

# Optional free text, for example corrected part-provisioning assumptions.
USER_FEEDBACK: str = ""

MAX_CONTEXT_CHARS: int = 24000

# ============================================================================


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the automation planner on an existing completed App V3 session."
    )
    parser.add_argument("--session-root", type=Path, default=None, help="Existing V3 session root")
    parser.add_argument("--config", type=Path, default=None, help="Automation planner YAML config")
    parser.add_argument("--feedback", type=str, default=None, help="Optional user feedback for planner context")
    parser.add_argument("--feedback-file", type=Path, default=None, help="Optional text file with user feedback")
    parser.add_argument("--max-context-chars", type=int, default=None, help="Prompt context character cap")
    return parser


def _read_feedback(feedback: Optional[str], feedback_file: Optional[Path]) -> str:
    parts = []
    if feedback:
        parts.append(feedback)
    if feedback_file:
        parts.append(feedback_file.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def main() -> int:
    args = build_arg_parser().parse_args()
    from agent.automation_planner import load_automation_planner_config, run_automation_planner_on_session

    session_root = args.session_root or Path(SESSION_ROOT)
    config_path = args.config or Path(AUTOMATION_PLANNER_CONFIG)
    config = load_automation_planner_config(config_path)
    default_feedback = str(config.get("user_feedback") or USER_FEEDBACK)
    feedback = _read_feedback(args.feedback if args.feedback is not None else default_feedback, args.feedback_file)
    max_context_chars = args.max_context_chars or int(config.get("max_context_chars") or MAX_CONTEXT_CHARS)

    result = run_automation_planner_on_session(
        session_root,
        user_feedback=feedback,
        max_context_chars=max_context_chars,
        config=config,
    )
    print("\nFertig.")
    print(f"Summary: {result['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
