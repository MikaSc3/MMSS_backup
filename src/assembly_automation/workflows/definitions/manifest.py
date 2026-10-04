"""Atomic session manifest for product workflows."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import RLock
import time
from typing import Any, Mapping
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManifest:
    def __init__(self, session_root: str | Path, workflow: str):
        self._lock = RLock()
        self.root = Path(session_root).resolve()
        self.path = self.root / "manifest.json"
        self.root.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("workflow") != workflow:
                raise ValueError(f"Session manifest does not belong to workflow {workflow}")
            self.data = value
        else:
            self.data = {"workflow": workflow, "session_id": self.root.name,
                         "status": "created", "created_at": _now(),
                         "active_sequence_revision": None, "stages": {}, "artifacts": {}}
            self.write()

    def relative(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"Session artifact must stay below {self.root}: {resolved}")
        return resolved.relative_to(self.root).as_posix()

    def stage(self, name: str, status: str, *, artifacts: Mapping[str, str | Path] | None = None,
              error: str | None = None, counts: Mapping[str, int] | None = None) -> None:
        with self._lock:
            entry = dict(self.data["stages"].get(name, {}))
            entry["status"] = status
            if status == "running":
                entry["started_at"] = _now()
                entry.pop("finished_at", None)
                entry.pop("error", None)
            elif status in {"complete", "partial", "failed"}:
                entry["finished_at"] = _now()
            if artifacts:
                entry["artifacts"] = {key: self.relative(value) for key, value in artifacts.items()}
            if error:
                entry["error"] = error
            if counts:
                entry["counts"] = dict(counts)
            self.data["stages"][name] = entry
            self.write()

    def publish(self, key: str, path: str | Path) -> None:
        with self._lock:
            relative = self.relative(path)
            self.data["artifacts"][key] = relative
            self._publish_registry(relative)
            self.write()

    def _publish_registry(self, relative: str) -> None:
        registry_path = self.root / "artifact_registry.json"
        registry: dict[str, Any] = {"schema_version": 1, "active": {}, "revisions": {}}
        if registry_path.is_file():
            loaded = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                registry.update(loaded)
        parts = Path(relative).parts
        if "revisions" not in parts:
            return
        index = parts.index("revisions")
        if index == 0 or index + 1 >= len(parts):
            return
        kind = {"03_assembly": "assembly", "04_monoparts": "monoparts",
                "05_sequence": "sequence", "06_assessment": "assessment",
                "07_reports": "report"}.get(parts[index - 1])
        revision = parts[index + 1]
        if kind is None:
            return
        revisions = registry.setdefault("revisions", {}).setdefault(kind, [])
        if revision not in revisions:
            revisions.append(revision)
        registry.setdefault("active", {})[kind] = revision
        temporary = registry_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(registry_path)

    def status(self, status: str, *, active_sequence_revision: str | None = None) -> None:
        with self._lock:
            self.data["status"] = status
            self.data["updated_at"] = _now()
            if active_sequence_revision is not None:
                self.data["active_sequence_revision"] = active_sequence_revision
            self.write()

    def write(self) -> None:
        with self._lock:
            temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2,
                                            allow_nan=False) + "\n", encoding="utf-8")
            try:
                for attempt in range(4):
                    try:
                        os.replace(temporary, self.path)
                        return
                    except PermissionError:
                        if attempt == 3:
                            raise
                        time.sleep(0.02 * (attempt + 1))
            finally:
                if temporary.exists():
                    temporary.unlink()
