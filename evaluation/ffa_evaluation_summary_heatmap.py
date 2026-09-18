# This module has been integrated into ffa_evaluation.py
# All functions from ffa_evaluation_summary_heatmap.py are now part of ffa_evaluation.py
# Please use the functions from ffa_evaluation.py:
# - generate_field_accuracy_summary_heatmap()
# - generate_step_accuracy_heatmap()

"""
FFA Evaluation Summary Heatmap

This file is deprecated. All heatmap generation functions have been 
integrated into ffa_evaluation.py for better organization.

Use:
  from evaluation.ffa_evaluation import (
      generate_field_accuracy_summary_heatmap,
      generate_step_accuracy_heatmap
  )
"""

__all__ = [
    'generate_field_accuracy_summary_heatmap',
    'generate_step_accuracy_heatmap'
]
