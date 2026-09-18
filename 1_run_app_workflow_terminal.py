"""Terminal runner for app_workflow_v2.
..
Examples:
    python run_app_workflow_terminal.py
    python run_app_workflow_terminal.py --assembly Stehlager_Sicherungsring
    python run_app_workflow_terminal.py --step-file data/input/test/assy.STEP --interactive

By default, type feedback in the terminal whenever an agent asks.
Use --auto to skip terminal answers and let the agents proceed automatically.
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.app_workflow_v2 import (
    WORKSPACE_ROOT,
    load_config,
    load_prompt_library,
    run_app_workflow_v2,
)


# ============================================================================
# CONFIGURATION: same folder structure as full_workflow_experiments.py
# ============================================================================

MASTER_STEP_INPUT_FOLDER: str = "data/input/test"
STEPPARSER_OUTPUT_FOLDER: str = "data/processed/stepparser8"
LLM_OUTPUT_FOLDER: str = "data/datapreparation/NEWFILES"
TEXTBASED_ADDITIONAL_DATA: str = "data/input/Textbased_Data"
EXPERIMENT_CONFIG_FOLDER: str = "configs/appconfig"
EXPERIMENT_CONFIG_NAME: Optional[str] = "appconfig"
TERMINAL_INTERACTIVE: bool = True  # True = answer agents in terminal, False = auto-mode

# ============================================================================


def _resolve_workspace_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def _resolve_experiment_config() -> Optional[Path]:
    if not EXPERIMENT_CONFIG_NAME or str(EXPERIMENT_CONFIG_NAME).lower() in {"all", "*"}:
        return None

    candidate = Path(EXPERIMENT_CONFIG_NAME)
    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        candidate = candidate.with_suffix(".yaml")

    if not candidate.is_absolute() and len(candidate.parts) == 1:
        candidate = _resolve_workspace_path(EXPERIMENT_CONFIG_FOLDER) / candidate
    elif not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    return candidate


def _get_step_files() -> Dict[str, Path]:
    input_root = _resolve_workspace_path(MASTER_STEP_INPUT_FOLDER)
    if not input_root.exists():
        raise FileNotFoundError(f"MASTER_STEP_INPUT_FOLDER not found: {input_root}")

    step_files = {
        path.stem: path
        for path in sorted(input_root.glob("*.STEP"))
    }
    if not step_files:
        raise FileNotFoundError(f"No .STEP files found in {input_root}")
    return step_files


def _ensure_textbased_additional_data(assembly_name: str) -> None:
    textbased_root = _resolve_workspace_path(TEXTBASED_ADDITIONAL_DATA)
    assembly_dir = textbased_root / assembly_name
    assembly_dir.mkdir(parents=True, exist_ok=True)

    for txt_file in [
        assembly_dir / f"additional_info_{assembly_name}.txt",
        assembly_dir / f"assembly_sequence_{assembly_name}.txt",
        assembly_dir / f"ground_truth_assembly_sequence_{assembly_name}.txt",
        assembly_dir / f"remarks_{assembly_name}.txt",
    ]:
        if not txt_file.exists():
            txt_file.write_text("", encoding="utf-8")


def _create_experiment_session(step_file: Path, assembly_name: Optional[str]) -> tuple[str, Path]:
    """Create an app-compatible session inside LLM_OUTPUT_FOLDER/config/assembly."""
    step_file = _resolve_workspace_path(step_file).resolve()
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    assembly = assembly_name or step_file.stem
    experiment_name = Path(EXPERIMENT_CONFIG_NAME or "app_workflow").stem
    session_root = _resolve_workspace_path(LLM_OUTPUT_FOLDER) / experiment_name / assembly

    for subdir in ["input", "preprocessing", "Agent_txt_files", "enriched_parts", "ffa_assessment"]:
        (session_root / subdir).mkdir(parents=True, exist_ok=True)

    target = session_root / "input" / f"{assembly}.STEP"
    if not target.exists() or step_file.stat().st_mtime > target.stat().st_mtime:
        shutil.copy2(step_file, target)
    _ensure_textbased_additional_data(assembly)
    return assembly, session_root


def _print_event(event: Dict[str, Any]) -> None:
    """Compact terminal display for app workflow callback events."""
    event_type = event.get("type", "event")

    if event_type == "message":
        role = event.get("role", "system")
        content = event.get("content", "")
        print(f"\n[{role}] {content}")
    elif event_type == "status":
        print(f"[status] {event.get('content', '')}")
    elif event_type == "phase_changed":
        print(f"\n--- {event.get('phase', '')} ---")
    elif event_type == "progress":
        print(f"[progress] step {event.get('step')}")
    elif event_type == "artifacts":
        print("[artifacts]")
        for key, value in event.items():
            if key != "type" and value:
                print(f"  {key}: {value}")
    elif event_type == "error":
        print(f"[error] {event.get('content', '')}", file=sys.stderr)
    elif event_type == "complete":
        print("\n[complete] workflow finished")
    else:
        print(f"[{event_type}] {event}")


def _start_stdin_forwarder(input_queue: queue.Queue, stop_event: threading.Event) -> threading.Thread:
    """Forward terminal input into the workflow input queue."""
    def _worker() -> None:
        print("\nInteractive mode enabled. Type feedback and press Enter.")
        print("Examples: 'continue', 'approve', or a correction/request for the active agent.\n")
        while not stop_event.is_set():
            try:
                line = input("> ").strip()
            except EOFError:
                return
            if not line:
                continue
            input_queue.put(line)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def main() -> int:
    parser = argparse.ArgumentParser(description="Run app_workflow_v2 from the terminal.")
    parser.add_argument("--config", type=Path, default=None, help="App config YAML path.")
    parser.add_argument("--prompts", default="prompts.yaml", help="Prompt YAML filename in configs/.")
    parser.add_argument("--assembly", default=None, help="Assembly name from MASTER_STEP_INPUT_FOLDER. Defaults to all.")
    parser.add_argument("--step-file", type=Path, default=None, help="STEP file to copy into a new session.")
    parser.add_argument("--session", type=Path, default=None, help="Existing session root to reuse.")
    parser.add_argument("--interactive", action="store_true", help="Read agent feedback from terminal stdin.")
    parser.add_argument("--auto", action="store_true", help="Disable terminal answers and use app auto-mode.")
    args = parser.parse_args()

    if args.step_file and args.session:
        parser.error("Use either --step-file or --session, not both.")

    interactive = TERMINAL_INTERACTIVE
    if args.interactive:
        interactive = True
    if args.auto:
        interactive = False
    input_queue = queue.Queue() if interactive else None
    stop_event = threading.Event()
    if input_queue is not None:
        _start_stdin_forwarder(input_queue, stop_event)

    try:
        config_path = args.config or _resolve_experiment_config()
        if config_path:
            os.environ["APA_EXPERIMENT_YAML"] = str(config_path)
        os.environ["APA_MASTER_STEP_INPUT_FOLDER"] = str(_resolve_workspace_path(MASTER_STEP_INPUT_FOLDER))
        os.environ["APA_STEPPARSER_OUTPUT_FOLDER"] = str(_resolve_workspace_path(STEPPARSER_OUTPUT_FOLDER))

        if args.step_file:
            runs = [_create_experiment_session(args.step_file, args.assembly)]
        elif args.session:
            assembly_name = args.assembly or Path(args.session).name.split("_", 2)[-1]
            runs = [(assembly_name, args.session)]
        else:
            step_files = _get_step_files()
            if args.assembly:
                if args.assembly not in step_files:
                    raise FileNotFoundError(
                        f"Assembly {args.assembly!r} not found in {MASTER_STEP_INPUT_FOLDER}"
                    )
                selected = {args.assembly: step_files[args.assembly]}
            else:
                selected = step_files
            runs = [_create_experiment_session(path, name) for name, path in selected.items()]

        config = load_config(config_path)
        prompt_library = load_prompt_library(args.prompts)

        print("\nFolder structure")
        print(f"  MASTER_STEP_INPUT_FOLDER:      {_resolve_workspace_path(MASTER_STEP_INPUT_FOLDER)}")
        print(f"  STEPPARSER_OUTPUT_FOLDER:      {_resolve_workspace_path(STEPPARSER_OUTPUT_FOLDER)}")
        print(f"  LLM_OUTPUT_FOLDER:             {_resolve_workspace_path(LLM_OUTPUT_FOLDER)}")
        print(f"  TEXTBASED_ADDITIONAL_DATA:     {_resolve_workspace_path(TEXTBASED_ADDITIONAL_DATA)}")
        print(f"  EXPERIMENT_CONFIG:             {config_path}")

        for assembly_name, session_root in runs:
            print("\n" + "=" * 80)
            print(f"APP WORKFLOW TERMINAL RUN: {assembly_name}")
            print(f"Output: {session_root}")
            print("=" * 80)
            run_app_workflow_v2(
                config_path=config_path,
                assembly_name=assembly_name,
                session_root=session_root,
                config=config,
                prompt_library=prompt_library,
                ui_callback=_print_event,
                input_queue=input_queue,
            )
        return 0
    except Exception as exc:
        print(f"\nFatal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_event.set()


if __name__ == "__main__":
    raise SystemExit(main())
