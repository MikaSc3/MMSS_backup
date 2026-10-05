"""Schema-validated whole-artifact rewriting from natural-language corrections."""

from .planner import ArtifactChangePlanner
from .target_resolver import ResolvedTarget, resolve_target

__all__ = ["ArtifactChangePlanner", "ResolvedTarget", "resolve_target"]
