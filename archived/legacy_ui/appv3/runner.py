"""Background runner connecting Streamlit to app_workflow_v3."""

from __future__ import annotations

import importlib
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def safe_assembly_name(file_name: str) -> str:
    stem = Path(file_name).stem
    return re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_") or "assembly"


def start_initial_agent(*, workspace_root: Path, event_queue) -> None:
    """Ask the real content agent to introduce itself when the app opens."""

    def worker() -> None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            workflow_module = _load_workflow_module(workspace_root)
            from agent.tools import _get_img_describer_llm

            config_path = workspace_root / "configs" / "appconfig" / "appconfigV2.yaml"
            config = workflow_module.load_config(config_path)
            prompt_id = str(
                config.get("content_workflow_agent_prompt_id")
                or "content_workflow_agent_v3"
            )
            system_prompt = workflow_module._load_required_prompt(prompt_id)
            llm = _get_img_describer_llm(max_completion_tokens=500)
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content="Please introduce yourself."),
                ]
            )
            content = str(getattr(response, "content", "") or "").strip()
            if not content:
                raise RuntimeError("The content agent returned an empty introduction.")
            event_queue.put(
                {
                    "type": "agent_message",
                    "role": "agent",
                    "phase": "CONTENT_AGENT",
                    "content": content,
                }
            )
        except Exception as exc:
            event_queue.put(
                {
                    "type": "intro_error",
                    "content": f"Could not start the content agent: {type(exc).__name__}: {exc}",
                }
            )

    threading.Thread(
        target=worker,
        daemon=True,
        name="appv3-content-agent-introduction",
    ).start()


def start_workflow(
    *,
    step_name: str,
    step_bytes: bytes,
    additional_files: Iterable[tuple[str, bytes]],
    workspace_root: Path,
    event_queue,
    input_queue,
    initial_agent_message: str,
) -> Path:
    assembly_name = safe_assembly_name(step_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    session_root = workspace_root / "data" / "sessions_v3" / f"{timestamp}_{assembly_name}"
    input_dir = session_root / "input"
    documents_dir = input_dir / "additional_data"
    documents_dir.mkdir(parents=True, exist_ok=True)

    step_path = input_dir / f"{assembly_name}.STEP"
    step_path.write_bytes(step_bytes)

    document_paths: list[Path] = []
    used_names: set[str] = set()
    for original_name, content in additional_files:
        file_name = _unique_name(Path(original_name).name, used_names)
        path = documents_dir / file_name
        path.write_bytes(content)
        document_paths.append(path)

    event_queue.put(
        {
            "type": "session_created",
            "session_root": str(session_root),
            "assembly_name": assembly_name,
        }
    )

    def worker() -> None:
        try:
            app_workflow_v3 = _load_workflow_module(workspace_root)

            config_path = workspace_root / "configs" / "appconfig" / "appconfigV2.yaml"
            os.environ["APA_EXPERIMENT_YAML"] = str(config_path)
            os.environ["APA_MASTER_STEP_INPUT_FOLDER"] = str(input_dir)
            os.environ["APA_STEPPARSER_OUTPUT_FOLDER"] = str(session_root / "preprocessing" / "stepparser")

            app_workflow_v3.run_app_workflow_v3_terminal(
                config_path=config_path,
                assembly_name=assembly_name,
                step_file=step_path,
                additional_files=document_paths,
                session_root=session_root,
                auto=False,
                ui_callback=event_queue.put,
                input_queue=input_queue,
                prompt_for_setup_inputs=False,
                initial_agent_message=initial_agent_message,
            )
        except Exception as exc:
            event_queue.put(
                {
                    "type": "error",
                    "content": f"{type(exc).__name__}: {exc}",
                }
            )

    threading.Thread(target=worker, daemon=True, name=f"appv3-{assembly_name}").start()
    return session_root


def _load_workflow_module(workspace_root: Path):
    """Load this repository's workflow even if Streamlit imported another scripts module."""
    workspace_text = str(workspace_root.resolve())
    if workspace_text in sys.path:
        sys.path.remove(workspace_text)
    sys.path.insert(0, workspace_text)

    scripts_dir = (workspace_root / "scripts").resolve()
    loaded_scripts = sys.modules.get("scripts")
    if loaded_scripts is not None:
        loaded_paths = [
            Path(path).resolve()
            for path in getattr(loaded_scripts, "__path__", [])
        ]
        if scripts_dir not in loaded_paths:
            for module_name in [
                name
                for name in tuple(sys.modules)
                if name == "scripts" or name.startswith("scripts.")
            ]:
                sys.modules.pop(module_name, None)

    importlib.invalidate_caches()
    return importlib.import_module("scripts.app_workflow_v3")


def _unique_name(file_name: str, used_names: set[str]) -> str:
    candidate = file_name
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    index = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    used_names.add(candidate.lower())
    return candidate
