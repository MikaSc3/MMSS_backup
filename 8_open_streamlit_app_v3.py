"""Launch the agent-driven STEP2FfA Streamlit App V3."""

from __future__ import annotations

import subprocess
import socket
import sys
from pathlib import Path


def _requested_port(arguments: list[str]) -> int | None:
    for index, argument in enumerate(arguments):
        if argument.startswith("--server.port="):
            return int(argument.split("=", 1)[1])
        if argument == "--server.port" and index + 1 < len(arguments):
            return int(arguments[index + 1])
    return None


def _first_free_port(start: int = 8501, stop: int = 8599) -> int:
    for port in range(start, stop + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free Streamlit port found between {start} and {stop}")


def main() -> int:
    workspace_root = Path(__file__).resolve().parent
    app_path = workspace_root / "appv3" / "app.py"
    passthrough_args = sys.argv[1:]
    requested_port = _requested_port(passthrough_args)
    port = requested_port or _first_free_port()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=false",
        *([] if requested_port else ["--server.port", str(port)]),
        *passthrough_args,
    ]

    print("Opening STEP2FfA App V3...")
    print(f"URL: http://localhost:{port}")
    print("Press Ctrl+C in this terminal to stop the app.\n")
    try:
        return subprocess.run(command, cwd=workspace_root).returncode
    except KeyboardInterrupt:
        print("\nStreamlit App V3 stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
