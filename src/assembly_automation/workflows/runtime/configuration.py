"""Explicit configuration loading without environment-driven overrides."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings; lists and scalar values replace earlier values."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _read_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {path}")
    return value


def load_settings(
    config_path: str | Path,
    *,
    defaults_path: str | Path | None = None,
    profile_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve defaults -> config -> profile from explicitly supplied file paths.

    Returned settings are independent of previous calls. Node/schema validation
    will be supplied by the node registry as nodes are implemented.
    """
    settings: dict[str, Any] = {}
    for candidate in (defaults_path, config_path, profile_path):
        if candidate is not None:
            settings = merge_settings(settings, _read_mapping(Path(candidate)))
    return settings
