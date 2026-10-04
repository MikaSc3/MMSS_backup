"""Persistent, scoped user feedback for workflow nodes and revisions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from .storage import atomic_write_json


SCOPES = {"global", "assembly", "part", "sequence", "interaction", "ffa_report",
          "automation_idea", "automation_concept"}
# Keep the boundary tolerant of the planning label used by older prompts/models.
# The persisted ledger still contains only canonical scopes.
FEEDBACK_TYPES = {"context", "correction", "constraint", "requirement", "approval"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackStore:
    """Append-only feedback ledger plus node-specific context compilation."""

    def __init__(self, session_root: str | Path):
        self.root = Path(session_root).resolve() / "09_user_agent"
        self.path = self.root / "feedback.json"
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"events": []})

    def _read(self) -> dict[str, Any]:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("events"), list):
            raise ValueError(f"Invalid feedback ledger: {self.path}")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.path, value)

    def append(self, *, scope: str, raw_user_message: str, agent_summary: str,
               feedback_type: str = "context", targets: Iterable[str] = ()) -> dict[str, Any]:
        if scope not in SCOPES:
            raise ValueError(f"Unknown feedback scope {scope!r}; expected {sorted(SCOPES)}")
        if feedback_type not in FEEDBACK_TYPES:
            raise ValueError(f"Unknown feedback type {feedback_type!r}")
        raw = raw_user_message.strip()
        summary = agent_summary.strip()
        if not raw or not summary:
            raise ValueError("Feedback requires the original user message and a concise summary")
        document = self._read()
        event = {"feedback_id": f"feedback_{len(document['events']) + 1:04d}",
                 "created_at": _now(), "scope": scope,
                 "targets": list(dict.fromkeys(str(item) for item in targets if str(item))),
                 "type": feedback_type, "raw_user_message": raw,
                 "agent_summary": summary, "status": "accepted"}
        document["events"].append(event)
        self._write(document)
        return event

    def events(self, *, scopes: Iterable[str] | None = None,
               targets: Iterable[str] | None = None) -> list[dict[str, Any]]:
        selected_scopes = set(scopes or SCOPES)
        selected_targets = set(targets or [])
        result = []
        for event in self._read()["events"]:
            if event.get("status") != "accepted" or event.get("scope") not in selected_scopes:
                continue
            event_targets = set(event.get("targets") or [])
            if selected_targets and event_targets and not event_targets.intersection(selected_targets):
                continue
            result.append(dict(event))
        return result

    def compile_context(self, *, scopes: Iterable[str], targets: Iterable[str] = (),
                        max_chars: int = 12000) -> str:
        events = self.events(scopes=scopes, targets=targets)
        if not events:
            return ""
        lines = ["## Confirmed User Context and Feedback"]
        for event in events:
            target = f" Targets: {', '.join(event['targets'])}." if event["targets"] else ""
            lines.append(f"- [{event['scope']}/{event['type']}] {event['agent_summary']}{target}")
        value = "\n".join(lines)
        if len(value) <= max_chars:
            return value
        marker = "\n[Earlier feedback truncated to the configured context limit.]"
        return value[-(max_chars - len(marker)):] + marker

    @property
    def count(self) -> int:
        return len(self._read()["events"])
