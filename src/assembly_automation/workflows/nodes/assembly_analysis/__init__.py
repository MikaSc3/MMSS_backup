"""Assembly-analysis workflow node."""

from .node import run_assembly_analysis
from .structured_output import AssemblyAnalysis

__all__ = ["AssemblyAnalysis", "run_assembly_analysis"]
