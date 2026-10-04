"""
Launch the STEP2FfA Streamlit UI.

Run:
    python 6_open_streamlit_app.py

Optional Streamlit flags can be passed through, for example:
    python 6_open_streamlit_app.py --server.port 8502
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    workspace_root = Path(__file__).resolve().parent
    app_path = workspace_root / "ui" / "app.py"

    if not app_path.exists():
        print(f"ERROR: Streamlit app not found: {app_path}")
        return 1

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=false",
        *sys.argv[1:],
    ]

    print("Opening STEP2FfA Streamlit UI...")
    print("URL: http://localhost:8501")
    print("Press Ctrl+C in this terminal to stop the app.\n")

    try:
        return subprocess.run(command, cwd=workspace_root).returncode
    except KeyboardInterrupt:
        print("\nStreamlit app stopped.")
        return 0
    except ModuleNotFoundError:
        print("ERROR: Streamlit is not installed in this Python environment.")
        print("Install/activate the environment from env-latest.yaml, then try again.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
