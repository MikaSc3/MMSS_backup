"""Interactive terminal test for the reorganized user-facing workflow agent."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys
import uuid

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.user_agent import UserFacingAgent, WorkflowAgentTools
from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment


def _step_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {directory}")
    return sorted((path.resolve() for path in directory.iterdir()
                   if path.is_file() and path.suffix.lower() in {".step", ".stp"}),
                  key=lambda path: path.name.lower())


def _choose(paths: list[Path]) -> Path:
    if not paths:
        raise FileNotFoundError("No STEP/STP files found")
    if len(paths) == 1:
        return paths[0]
    print("Available STEP files:")
    for index, path in enumerate(paths, 1):
        print(f"  {index}. {path.name}")
    while True:
        answer = input(f"Select file [1-{len(paths)}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(paths):
            return paths[int(answer) - 1]


def _new_session(step_file: Path, output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", step_file.stem).strip("._") or "assembly"
    return (output_root / f"{stamp}_{slug}_{uuid.uuid4().hex[:8]}").resolve()


def _workflow_event(event: dict) -> None:
    kind, stage = event.get("type"), event.get("stage")
    if kind == "stage_started":
        print(f"\n[{stage}] started", flush=True)
    elif kind == "stage_progress":
        total = event.get("total")
        count = f"{event.get('completed')}/{total}" if total is not None else str(event.get("completed"))
        print(f"[{stage}] {count} - {event.get('item')}", flush=True)
    elif kind == "stage_completed":
        print(f"[{stage}] {event.get('status')}", flush=True)
    elif kind == "stage_failed":
        print(f"[{stage}] FAILED: {event.get('error')}", file=sys.stderr, flush=True)


def _agent_event(event: dict) -> None:
    if event["type"] == "assistant_message":
        print(f"\nFfA Navigator: {event['content']}", flush=True)
    elif event["type"] == "tool_started":
        print(f"\n[tool] {event['tool']} started", flush=True)
    elif event["type"] == "tool_completed":
        result = event.get("result") or {}
        status = result.get("status", "complete") if isinstance(result, dict) else "complete"
        print(f"[tool] {event['tool']} {status}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=WORKSPACE_ROOT / "data/input/lager")
    parser.add_argument("--step-file", type=Path)
    parser.add_argument("--supporting-file", type=Path, action="append", default=[])
    parser.add_argument("--config", type=Path,
                        default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    parser.add_argument("--output-root", type=Path,
                        default=WORKSPACE_ROOT / "data/user_agent_tests")
    parser.add_argument("--session-root", type=Path)
    parser.add_argument("--message", help="Run one user turn and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_project_environment(WORKSPACE_ROOT)
    config = load_settings(args.config.resolve(strict=True))
    if args.session_root:
        session_root = args.session_root.resolve()
        step_file = args.step_file.resolve(strict=True) if args.step_file else None
    else:
        candidates = [args.step_file.resolve(strict=True)] if args.step_file else _step_files(args.input_dir.resolve())
        step_file = _choose(candidates)
        session_root = _new_session(step_file, args.output_root.resolve())
    supporting = [path.resolve(strict=True) for path in args.supporting_file]
    workflow = AssemblyAssessmentWorkflow(session_root=session_root, settings=config,
                                          event_callback=_workflow_event)
    toolbox = WorkflowAgentTools(workflow=workflow, step_file=step_file,
                                 supporting_files=supporting)
    agent = UserFacingAgent(toolbox=toolbox, settings=config["user_agent"],
                            llm_profiles=config["llms"]["profiles"],
                            event_callback=_agent_event)
    print("User-facing agent test")
    print(f"Session: {session_root}")
    print("Type 'exit' to stop. The session can be resumed with --session-root.")
    if args.message:
        agent.invoke(args.message)
        return 0
    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped.")
            return 0
        if message.lower() in {"exit", "quit", "stop"}:
            return 0
        if message:
            try:
                agent.invoke(message)
            except Exception as exc:
                print(f"Agent turn failed: {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
