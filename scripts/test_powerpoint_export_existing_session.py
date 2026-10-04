"""Generate a PowerPoint from the completed Stehlager session.

Run from the repository root:
    python scripts/test_powerpoint_export_existing_session.py
"""

from __future__ import annotations

from pathlib import Path
import sys


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from assembly_automation.presentation import build_report


SESSION = (
    WORKSPACE_ROOT
    / "data"
    / "sessions"
    / "2026-10-02_152741_Stehlager_Sicherungsring_e6229291"
)


def main() -> int:
    if not SESSION.is_dir():
        raise FileNotFoundError(f"Session does not exist: {SESSION}")
    print("Generating engineering PowerPoint...")
    print(f"Session: {SESSION}")
    output = build_report(SESSION)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"PowerPoint was not created correctly: {output}")
    print("PowerPoint generation complete.")
    print(f"PowerPoint: {output}")
    print(f"Size:       {output.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
