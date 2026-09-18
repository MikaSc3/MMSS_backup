# Evaluation Module Migration

## Summary

The FFA evaluation-related files have been successfully migrated from `agent/` to a new `evaluation/` folder in the project root. This provides better organization and separation of concerns.

## Files Migrated

1. **ffa_evaluation.py** - Core evaluation engine with metrics calculation and visualizations
2. **ffa_evaluation_orchestrator.py** - Multi-experiment orchestrator
3. **ffa_str_to_enum.py** - String-to-integer enum conversion
4. **ffa_enum_to_str.py** - Integer-to-string enum conversion (reverse)
5. **ffa_evaluation_summary_heatmap.py** - Heatmap visualization utilities
6. **generate_comparison_charts.py** - Cross-experiment comparison charts
7. **FFA_EVALUATION_OUTPUT_STRUCTURE.md** - Documentation of output structure
8. **__init__.py** - Python package initialization

## Dependencies

The evaluation module depends on:
- **agent/structured_output.py** - Pydantic models and Enum definitions (remains in agent/)
- **agent/schemas/** - Schema definitions (remains in agent/)

## Import Usage

### From evaluation module (internal, relative imports):
```python
from .ffa_str_to_enum import convert_ffa_stripped_to_enum, create_ffa_enum_mapping
from .ffa_evaluation import run_evaluation
```

### From other modules (external, absolute imports):
```python
from agent.structured_output import NatureOfProvisionOption
from evaluation.ffa_evaluation import run_evaluation
from evaluation.ffa_evaluation_orchestrator import run_evaluation_orchestrator
```

## CLI Usage

### Run evaluation for a specific experiment:
```bash
python -m evaluation.ffa_evaluation <predictions_dir>
```

### Run full evaluation orchestrator:
```bash
python -m evaluation.ffa_evaluation_orchestrator <run_root>
```

### Convert FFA data to enum format:
```bash
python -m evaluation.ffa_str_to_enum <experiment_dir>
```

### Convert enum format back to strings:
```bash
python -m evaluation.ffa_enum_to_str <evaluation_run_dir>
```

### Generate comparison charts:
```bash
python -m evaluation.generate_comparison_charts <eval_root>
```

## File Structure

```
project_root/
├── agent/                           # Agent-related code
│   ├── structured_output.py        # FFA enums & schemas (dependency)
│   ├── schemas/                    # Schema definitions (dependency)
│   └── ...
├── evaluation/                      # FFA Evaluation module
│   ├── __init__.py
│   ├── ffa_evaluation.py           # Main evaluation engine
│   ├── ffa_evaluation_orchestrator.py  # Multi-experiment orchestrator
│   ├── ffa_str_to_enum.py          # String→Integer conversion
│   ├── ffa_enum_to_str.py          # Integer→String conversion
│   ├── ffa_evaluation_summary_heatmap.py  # Heatmap visualization (deprecated)
│   ├── generate_comparison_charts.py     # Comparison charts
│   └── FFA_EVALUATION_OUTPUT_STRUCTURE.md  # Output documentation
├── data/
│   ├── ground_truth/               # Ground truth FFA assessments
│   └── experiments/                # Experiment runs
│       └── run_2026-02-10_154526/
│           ├── exp1_baseline/      # Experiment results
│           └── evaluation/         # Evaluation outputs
├── run_experiments.py
└── ...
```

## Migration Impact

### No breaking changes
- All original files remain in `agent/` directory
- New `evaluation/` folder coexists without conflicts
- Imports updated to reference new locations
- Dependencies properly managed (structured_output stays in agent/)

### Benefits
- Better organization and separation of concerns
- Evaluation logic isolated from agent logic
- Clearer module boundaries
- Easier to maintain and extend

## Next Steps (Optional)

If you want to complete the refactoring:
1. Update `run_experiments.py` to import from `evaluation` module
2. Remove original files from `agent/` (keeping only imports/references)
3. Update any other scripts that use these evaluation functions

## Verification

All files successfully migrated:
- ✅ ffa_evaluation.py
- ✅ ffa_evaluation_orchestrator.py
- ✅ ffa_str_to_enum.py
- ✅ ffa_enum_to_str.py
- ✅ ffa_evaluation_summary_heatmap.py
- ✅ generate_comparison_charts.py
- ✅ FFA_EVALUATION_OUTPUT_STRUCTURE.md
- ✅ __init__.py

Imports verified:
- ✅ Relative imports within evaluation module use `.` notation
- ✅ External imports to agent use `agent.` prefix
- ✅ No circular dependencies

