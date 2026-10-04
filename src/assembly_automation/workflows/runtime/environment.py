"""Environment loading for local workflow entry points.

The library itself does not load dotenv files implicitly. CLI scripts call this
helper so an already configured process environment keeps precedence while the
project's local files provide development credentials.
"""

from __future__ import annotations

from pathlib import Path


def load_project_environment(project_root: Path) -> tuple[Path, ...]:
    """Load supported project dotenv files without overriding process values."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "python-dotenv is required for local LLM credentials; "
            "install the project with the 'llm' extra"
        ) from exc

    root = Path(project_root).resolve()
    loaded: list[Path] = []
    # New installations use the root file. The second path keeps existing local
    # installations working while credentials are migrated out of agent/.
    for path in (root / ".env", root / "agent" / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)
    return tuple(loaded)
