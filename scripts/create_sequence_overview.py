"""Create or refresh the ordered sequence overview for an existing App V3 session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKSPACE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assembly_automation.stepparser.io.metadata_manager import write_json
from assembly_automation.workflows.nodes.sequence_rendering.collage import create_sequence_overview
from assembly_automation.workflows.nodes.sequence_rendering.settings import SequenceRenderingSettings


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _latest_session() -> Path:
    root = WORKSPACE_ROOT / "data/sessions"
    sessions = [path for path in root.iterdir() if path.is_dir()
                and path.joinpath("manifest.json").is_file()]
    if not sessions:
        raise FileNotFoundError(f"No sessions found below {root}")
    return max(sessions, key=lambda path: path.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-root", type=Path, default=None)
    parser.add_argument("--revision", default=None)
    args = parser.parse_args()
    session = (args.session_root or _latest_session()).resolve(strict=True)
    manifest = _read(session / "manifest.json")
    state_path = session / "user_agent/state.json"
    state = _read(state_path) if state_path.is_file() else {}
    revision = args.revision or state.get("active_sequence_revision") \
        or manifest.get("active_sequence_revision")
    if not isinstance(revision, str) or not revision:
        raise ValueError("Session has no active sequence revision")
    revision_root = session / "sequence/revisions" / revision
    renderings = revision_root / "renderings"
    summary_path = renderings / "rendering_summary.json"
    sequence_path = revision_root / "assembly_sequence.json"
    summary, sequence = _read(summary_path), _read(sequence_path)
    config = yaml.safe_load((WORKSPACE_ROOT / "configs/appsettingsv3.yaml").read_text(encoding="utf-8"))
    settings = SequenceRenderingSettings.from_mapping(config["nodes"]["sequence_rendering"])
    overview = create_sequence_overview(
        list(summary.get("images") or []), sequence, renderings, settings.collage)
    if overview is None:
        raise RuntimeError("No assembled ISO1 step images were available for an overview")
    existing = [item for item in summary.get("collages", [])
                if not isinstance(item, dict) or item.get("category") != "sequence_overview"]
    summary["sequence_overview"] = overview
    summary["collages"] = [overview, *existing]
    write_json(summary_path, summary)
    print(f"Session: {session}")
    print(f"Revision: {revision}")
    print(f"Overview: {renderings / overview['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
