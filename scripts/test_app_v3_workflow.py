"""Compatibility launcher. Prefer ``python run_workflow.py``."""

from __future__ import annotations

import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKSPACE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assembly_automation.app.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
