"""Terminal interface for the product assembly-assessment workflow."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import uuid

from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _step_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {directory}")
    return sorted(
        (path.resolve() for path in directory.iterdir()
         if path.is_file() and path.suffix.lower() in {".step", ".stp"}),
        key=lambda path: path.name.lower(),
    )


def _choose_step(paths: list[Path], *, automatic: bool) -> Path:
    if not paths:
        raise FileNotFoundError("No STEP/STP files found")
    if len(paths) == 1:
        return paths[0]
    print("\nAvailable STEP files:")
    for index, path in enumerate(paths, 1):
        print(f"  {index}. {path.name}")
    if automatic:
        print(f"Auto mode selected the first file: {paths[0].name}")
        return paths[0]
    while True:
        answer = input(f"Select file [1-{len(paths)}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(paths):
            return paths[int(answer) - 1]
        print("Enter one of the listed numbers.")


def _new_session(step_file: Path, output_root: Path) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", step_file.stem).strip("._") or "assembly"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return (output_root / f"{stamp}_{safe_name}_{uuid.uuid4().hex[:8]}").resolve()


def _event(event: dict) -> None:
    kind, stage = event.get("type"), event.get("stage")
    if kind == "stage_started":
        print(f"\n[{stage}] started", flush=True)
    elif kind == "stage_progress":
        completed, total = event.get("completed"), event.get("total")
        count = f" {completed}/{total}" if total is not None else f" {completed}"
        item = f" - {event.get('item')}" if event.get("item") is not None else ""
        print(f"[{stage}]{count}{item}", flush=True)
    elif kind == "stage_completed":
        print(f"[{stage}] {event.get('status')}", flush=True)
    elif kind == "stage_failed":
        print(f"[{stage}] FAILED: {event.get('error')}", file=sys.stderr, flush=True)
    elif kind == "checkpoint":
        print(f"\n[checkpoint] sequence revision {event.get('revision_id')} is ready", flush=True)
    elif kind == "workflow_completed":
        print(f"\n[workflow] revision {event.get('revision_id')} complete", flush=True)


def _show_sequence(path: Path) -> None:
    sequence = json.loads(path.read_text(encoding="utf-8"))
    print(f"\nSequence: {path}\nAssembly: {sequence.get('assembly_name', 'unknown')}\nSteps:")
    for step in sequence.get("steps", []):
        print(
            f"  {step.get('step_id'):>2}. {step.get('step_description')}"
            f"  [{step.get('joining_process')}; joining={step.get('joining_part')}]"
        )


def _decision() -> str:
    while True:
        answer = input("\nApprove, revise, or stop? [a/r/s]: ").strip().lower()
        if answer in {"a", "approve", "go", "continue", "yes"}:
            return "approve"
        if answer in {"r", "revise"}:
            return "revise"
        if answer in {"s", "stop", "q", "quit"}:
            return "stop"
        print("Enter a, r, or s.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=WORKSPACE_ROOT / "data/input/lager")
    parser.add_argument("--step-file", type=Path)
    parser.add_argument("--config", type=Path, default=WORKSPACE_ROOT / "configs/appsettingsv3.yaml")
    parser.add_argument("--output-root", type=Path, default=WORKSPACE_ROOT / "data/sessions")
    parser.add_argument("--session-root", type=Path)
    parser.add_argument("--context", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--auto", action="store_true",
                        help="Select the first input and approve the first generated sequence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_root: Path | None = None
    try:
        load_project_environment(WORKSPACE_ROOT)
        candidates = ([args.step_file.resolve(strict=True)] if args.step_file
                      else _step_files(args.input_dir.resolve()))
        step_file = _choose_step(candidates, automatic=args.auto)
        settings = load_settings(args.config.resolve(strict=True))
        session_root = (args.session_root.resolve() if args.session_root
                        else _new_session(step_file, args.output_root.resolve()))
        print("Assembly Automation workflow")
        print(f"Input:   {step_file}\nConfig:  {args.config.resolve()}\nSession: {session_root}")

        workflow = AssemblyAssessmentWorkflow(
            session_root=session_root, settings=settings, event_callback=_event)
        revision_number = 1
        initial_sequence: Path | None = None
        feedback: list[str] = []
        while True:
            revision_id = f"r{revision_number:03d}"
            checkpoint = workflow.prepare_through_sequence(
                step_file=step_file,
                revision_id=revision_id,
                sequence_mode="generate" if revision_number == 1 else "revise",
                initial_sequence=initial_sequence,
                user_feedback_summary="\n".join(feedback),
                user_context=args.context,
                sequence_constraints=args.constraints,
            )
            sequence_path = Path(checkpoint["sequence"])
            initial_sequence = initial_sequence or sequence_path
            _show_sequence(sequence_path)
            decision = "approve" if args.auto else _decision()
            if decision == "stop":
                print(f"Stopped at the sequence checkpoint. Session: {session_root}")
                return 0
            if decision == "revise":
                summary = input("Summarize the required sequence changes: ").strip()
                if not summary:
                    print("Revision feedback cannot be empty.")
                    continue
                feedback.append(f"Revision {revision_number}: {summary}")
                revision_number += 1
                continue
            result = workflow.complete_from_sequence(
                revision_id=revision_id,
                approved_sequence=sequence_path,
                user_context=args.context,
            )
            print("\nWorkflow complete")
            print(f"Session manifest: {result['manifest']}\nReport JSON:      {result['report']}")
            return 0
    except KeyboardInterrupt:
        print("\nStopped by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nWorkflow failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if session_root is not None:
            print(f"Resume with: --session-root \"{session_root}\"", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
