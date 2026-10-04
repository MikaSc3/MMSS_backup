"""Single-worker durable session controller for the Streamlit adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import queue
import re
import shutil
import sys
import threading
from typing import Any, Iterable, Mapping
from uuid import uuid4

from assembly_automation.user_agent import (
    UserFacingAgent, WorkflowAgentTools)
from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow
from assembly_automation.workflows.definitions.app_v3 import WorkflowPaths
from assembly_automation.workflows.runtime.configuration import load_settings
from assembly_automation.workflows.runtime.environment import load_project_environment

from .events import normalize_agent_event, normalize_workflow_event, product_event


_REGISTRY_LOCK = threading.Lock()
_ACTIVE_SESSIONS: dict[str, str] = {}


@dataclass(frozen=True)
class Command:
    command_id: str
    kind: str
    payload: dict[str, Any]


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value).stem).strip("._") or "assembly"


def _fallback_introduction() -> str:
    return (
        "Hi, I’m **FfA Navigator**. I’ll guide you through STEP preprocessing, assembly and "
        "part review, assembly-sequence review, and the final automation assessment. Upload a "
        "STEP assembly when you’re ready to begin."
    )


class SessionController:
    """Serialize all mutating commands for one browser-side product session."""

    def __init__(self, *, workspace_root: str | Path, config_path: str | Path | None = None,
                 event_queue: queue.Queue | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        default_config = self.workspace_root / "configs/appsettingsv3.yaml"
        # Unit callers can use a temporary session workspace while retaining
        # the application's checked-in settings. Explicit config paths still
        # fail normally when invalid.
        if config_path is None and not default_config.is_file():
            default_config = Path(__file__).resolve().parents[4] / "configs/appsettingsv3.yaml"
        self.config_path = Path(config_path or default_config).resolve()
        self.events = event_queue or queue.Queue()
        self.commands: queue.Queue[Command | None] = queue.Queue()
        self.controller_id = uuid4().hex
        self.draft_root = self._create_draft_session()
        self.session_root: Path | None = self.draft_root
        self.workflow: AssemblyAssessmentWorkflow | None = None
        self.toolbox: WorkflowAgentTools | None = None
        self.agent: UserFacingAgent | None = None
        self.welcome_message: str | None = None
        self._correlation_id: str | None = None
        self._stopped = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"ffa-ui-{self.controller_id[:8]}")
        # The real conversation exists from application startup. The draft
        # deliberately exposes no workflow operations until a STEP is uploaded.
        self._initialize_runtime(self.draft_root, step_path=None, supporting_files=[])
        self._thread.start()
        self.events.put(product_event(
            "session.draft.created", session_id=self.draft_root.name,
            session_root=str(self.draft_root), checkpoint="awaiting_upload"))

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stopped

    def start_session(self, *, step_name: str, step_bytes: bytes,
                      supporting_files: Iterable[tuple[str, bytes]] = ()) -> str:
        return self._enqueue("start_session", {"step_name": step_name, "step_bytes": step_bytes,
                                                "supporting_files": list(supporting_files)})

    def start_introduction(self) -> str:
        """Generate the welcome before a CAD session exists."""
        return self._enqueue("introduce", {})

    def resume_session(self, session_root: str | Path) -> str:
        return self._enqueue("resume_session", {"session_root": str(Path(session_root).resolve())})

    def submit_user_turn(self, message: str) -> str:
        if not message.strip():
            raise ValueError("message cannot be empty")
        return self._enqueue("user_turn", {"message": message.strip()})

    def submit_tool_action(self, tool_name: str, arguments: Mapping[str, Any],
                           *, user_message: str, visible_in_chat: bool = True) -> str:
        return self._enqueue("tool_action", {"tool_name": tool_name,
                                              "arguments": dict(arguments),
                                              "user_message": user_message.strip(),
                                              "visible_in_chat": visible_in_chat})

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.commands.put(None)
        if self.agent is not None:
            self.agent.close()
        self._release_session()
        self._discard_draft()

    def _enqueue(self, kind: str, payload: dict[str, Any]) -> str:
        if not self.alive:
            raise RuntimeError("Session controller is not running")
        command_id = uuid4().hex
        self.commands.put(Command(command_id, kind, payload))
        return command_id

    def _run(self) -> None:
        while True:
            command = self.commands.get()
            if command is None:
                return
            self._correlation_id = command.command_id
            self._emit("agent.turn.started", command=command.kind)
            try:
                if command.kind == "introduce":
                    self._introduce()
                elif command.kind == "start_session":
                    self._start(**command.payload)
                elif command.kind == "resume_session":
                    self._resume(**command.payload)
                elif command.kind == "user_turn":
                    self._require_agent().invoke(command.payload["message"])
                elif command.kind == "tool_action":
                    self._require_agent().execute_tool(
                        command.payload["tool_name"], command.payload["arguments"],
                        user_message=command.payload["user_message"],
                        visible_in_chat=command.payload.get("visible_in_chat", True))
                else:
                    raise ValueError(f"Unknown controller command: {command.kind}")
                self._emit("agent.turn.completed", command=command.kind)
            except Exception as exc:
                self._emit("agent.turn.failed", command=command.kind,
                           error=f"{type(exc).__name__}: {exc}")
            finally:
                self._correlation_id = None

    def _introduce(self) -> None:
        if self.welcome_message:
            self._require_agent().announce(self.welcome_message)
            return
        try:
            result = self._require_agent().invoke(
                "Introduce yourself briefly. Explain that you can discuss the assessment now, "
                "and that a STEP file is needed before analysis can begin. Do not call tools.",
                visible_user_message=False, allow_tools=False)
            message = str(result.get("response") or "").strip()
            if not message:
                raise RuntimeError("The agent returned an empty introduction")
        except Exception:
            # The UI remains usable if the service is temporarily unavailable.
            message = _fallback_introduction()
            self._require_agent().announce(message)
        self.welcome_message = message
        # The agent has already persisted/emitted its normal message. This
        # additional UI-only event lets the upload screen reveal immediately.
        self._emit("agent.message.completed", content=message,
                   intermediate=False, pre_session=True)

    def _start(self, *, step_name: str, step_bytes: bytes,
               supporting_files: list[tuple[str, bytes]]) -> None:
        draft_history = self._draft_conversation()
        assembly = _safe_name(step_name)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        root = (self.workspace_root / "data/sessions" /
                f"{stamp}_{assembly}_{uuid4().hex[:8]}").resolve()
        input_dir = WorkflowPaths(root).input
        document_dir = input_dir / "supporting"
        input_dir.mkdir(parents=True, exist_ok=False)
        if draft_history:
            conversation = WorkflowPaths(root).user_agent_root / "conversation.json"
            conversation.parent.mkdir(parents=True, exist_ok=True)
            temporary = conversation.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(draft_history, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
            temporary.replace(conversation)
        self.events.put(product_event("session.created", session_id=root.name,
                                      correlation_id=self._correlation_id,
                                      session_root=str(root), assembly_name=assembly))
        self.events.put(product_event("session.setup.progress", session_id=root.name,
                                      correlation_id=self._correlation_id,
                                      operation="saving_uploaded_files"))
        step_path = input_dir / f"{assembly}{Path(step_name).suffix or '.STEP'}"
        step_path.write_bytes(step_bytes)
        supporting_paths = []
        for index, (name, content) in enumerate(supporting_files, 1):
            document_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
            target = document_dir / (safe or f"document_{index}.txt")
            if target.exists():
                target = document_dir / f"{target.stem}_{index}{target.suffix}"
            target.write_bytes(content)
            supporting_paths.append(target)
        self.events.put(product_event("session.setup.progress", session_id=root.name,
                                      correlation_id=self._correlation_id,
                                      operation="initializing_workflow_agent"))
        self._initialize_runtime(root, step_path=step_path, supporting_files=supporting_paths)
        # _initialize_runtime closes the draft agent before replacing it.
        # Only remove the draft after that connection has been released.
        self._discard_draft()
        self._emit("session.setup.completed", operation="workflow_agent_ready")
        uploaded = [step_path.name, *(path.name for path in supporting_paths)]
        start_context = (
            "System startup context (not a user-visible chat message): the user pressed Start "
            "assessment and uploaded these files:\n"
            + "\n".join(f"- {name}" for name in uploaded)
            + "\n\nInspect the current session, ingest supporting files when present, and begin "
              "the appropriate workflow action. Do not narrate internal routing.")
        self._require_agent().invoke(start_context, visible_user_message=False)

    def _resume(self, *, session_root: str) -> None:
        root = Path(session_root).resolve(strict=True)
        manifest = root / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"Session has no manifest.json: {root}")
        paths = WorkflowPaths(root)
        steps = sorted(path for path in paths.input.iterdir()
                       if path.is_file() and path.suffix.lower() in {".step", ".stp"})
        if len(steps) != 1:
            raise ValueError(f"Session requires exactly one STEP file, found {len(steps)}")
        documents = sorted(path for path in (paths.input / "supporting").glob("*") if path.is_file())
        self._initialize_runtime(root, step_path=steps[0], supporting_files=documents)
        self._discard_draft()
        self._emit("session.resumed", session_root=str(root), assembly_name=steps[0].stem)

    def _initialize_runtime(self, root: Path, *, step_path: Path | None,
                            supporting_files: list[Path]) -> None:
        previous_root = self.session_root
        previous_agent = self.agent
        self._claim_session(root)
        try:
            load_project_environment(self.workspace_root)
            settings = load_settings(self.config_path)
            workflow = AssemblyAssessmentWorkflow(
                session_root=root, settings=settings,
                event_callback=lambda event: self._handle_workflow_event(event, root.name))
            toolbox = WorkflowAgentTools(workflow=workflow, step_file=step_path,
                                         supporting_files=supporting_files)
            agent = UserFacingAgent(
                toolbox=toolbox, settings=settings["user_agent"],
                llm_profiles=settings["llms"]["profiles"],
                event_callback=lambda event: self.events.put(normalize_agent_event(
                    event, session_id=root.name,
                    correlation_id=self._correlation_id or "system")))
        except Exception:
            with _REGISTRY_LOCK:
                if _ACTIVE_SESSIONS.get(str(root)) == self.controller_id:
                    _ACTIVE_SESSIONS.pop(str(root), None)
                if previous_root is not None:
                    _ACTIVE_SESSIONS[str(previous_root)] = self.controller_id
            raise
        self.session_root, self.workflow, self.toolbox, self.agent = root, workflow, toolbox, agent
        if previous_agent is not None:
            previous_agent.close()
        self._write_controller_state("active")

    def _handle_workflow_event(self, event: Mapping[str, Any], session_id: str) -> None:
        """Forward workflow events to the UI and show STEP parser progress in the terminal."""
        if event.get("stage") == "step_preprocessing":
            event_type = str(event.get("type", ""))
            if event_type == "stage_started":
                print("\n[stepparser] started", flush=True)
            elif event_type == "stage_progress":
                completed = event.get("completed")
                total = event.get("total")
                count = f" {completed}/{total}" if total is not None else f" {completed}"
                item = f" - {event.get('item')}" if event.get("item") is not None else ""
                print(f"[stepparser]{count}{item}", flush=True)
            elif event_type == "stage_completed":
                print(f"[stepparser] {event.get('status')}", flush=True)
            elif event_type == "stage_failed":
                print(f"[stepparser] FAILED: {event.get('error')}",
                      file=sys.stderr, flush=True)
        self.events.put(normalize_workflow_event(
            event, session_id=session_id, correlation_id=self._correlation_id))

    def _require_agent(self) -> UserFacingAgent:
        if self.agent is None:
            raise RuntimeError("Start or resume a session before sending a message")
        return self.agent

    def _claim_session(self, root: Path) -> None:
        key = str(root)
        with _REGISTRY_LOCK:
            owner = _ACTIVE_SESSIONS.get(key)
            if owner and owner != self.controller_id:
                raise RuntimeError("This session is already controlled by another active browser session")
            if self.session_root and str(self.session_root) != key:
                _ACTIVE_SESSIONS.pop(str(self.session_root), None)
            _ACTIVE_SESSIONS[key] = self.controller_id

    def _release_session(self) -> None:
        if self.session_root is None or self.session_root == self.draft_root:
            return
        with _REGISTRY_LOCK:
            if _ACTIVE_SESSIONS.get(str(self.session_root)) == self.controller_id:
                _ACTIVE_SESSIONS.pop(str(self.session_root), None)
        self._write_controller_state("released")

    def _write_controller_state(self, status: str) -> None:
        if self.session_root is None:
            return
        path = self.session_root / "user_agent/controller.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"controller_id": self.controller_id,
                                         "status": status,
                                         "thread_alive": self._thread.is_alive()}, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(path)

    def _create_draft_session(self) -> Path:
        """Create a tiny pre-upload session and remove abandoned drafts."""
        drafts = (self.workspace_root / "data/sessions/.drafts").resolve()
        drafts.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        for candidate in drafts.iterdir():
            marker = candidate / "draft.json"
            if not candidate.is_dir() or not marker.is_file():
                continue
            try:
                modified = datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc)
                candidate.resolve().relative_to(drafts)
                if modified < cutoff:
                    shutil.rmtree(candidate)
            except (OSError, ValueError):
                continue
        root = (drafts / f"draft_{uuid4().hex[:12]}").resolve()
        root.relative_to(drafts)
        root.mkdir(parents=False, exist_ok=False)
        now = datetime.now(timezone.utc).isoformat()
        manifest = {
            "workflow": "assembly_assessment", "session_id": root.name,
            "status": "draft", "checkpoint": "awaiting_upload",
            "active_sequence_revision": None, "stages": {}, "artifacts": {},
            "created_at": now, "updated_at": now,
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (root / "draft.json").write_text(
            json.dumps({"controller_id": self.controller_id, "created_at": now}, indent=2) + "\n",
            encoding="utf-8")
        return root

    def _discard_draft(self) -> None:
        draft = getattr(self, "draft_root", None)
        if draft is None or not draft.exists():
            return
        drafts = (self.workspace_root / "data/sessions/.drafts").resolve()
        try:
            draft.resolve().relative_to(drafts)
        except ValueError:
            raise RuntimeError(f"Refusing to remove draft outside {drafts}")
        if not draft.joinpath("draft.json").is_file():
            raise RuntimeError(f"Refusing to remove unmarked draft session: {draft}")
        shutil.rmtree(draft)
        if self.session_root == draft:
            self.session_root = None

    def _draft_conversation(self) -> list[dict[str, str]]:
        """Carry the real agent's pre-upload dialogue into the CAD session."""
        draft = self.draft_root
        path = WorkflowPaths(draft).user_agent_root / "conversation.json"
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return [{"role": str(item.get("role", "assistant")),
                 "content": str(item.get("content", ""))}
                for item in value if isinstance(item, dict)]

    def _emit(self, event_type: str, **payload: Any) -> None:
        session_id = self.session_root.name if self.session_root else None
        self.events.put(product_event(event_type, session_id=session_id,
                                      correlation_id=self._correlation_id, **payload))

    @staticmethod
    def list_sessions(workspace_root: str | Path) -> list[Path]:
        root = Path(workspace_root).resolve() / "data/sessions"
        if not root.is_dir():
            return []
        return sorted((path for path in root.iterdir() if path.is_dir()
                       and path.joinpath("manifest.json").is_file()),
                      key=lambda path: path.stat().st_mtime, reverse=True)
