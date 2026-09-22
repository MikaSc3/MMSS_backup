"""Allowlisted tool selection shared by LLM nodes."""

from typing import Any, Mapping


def resolve_tools(names: list[str] | tuple[str, ...], registry: Mapping[str, Any] | None) -> list[Any]:
    registry = registry or {}
    unknown = [name for name in names if name not in registry]
    if unknown:
        raise ValueError(f"Unknown node tools: {unknown}")
    return [registry[name] for name in names]
