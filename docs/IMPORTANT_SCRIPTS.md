# Active entry points and scripts

## Product entry points

| Entry point | Purpose | Status |
| --- | --- | --- |
| `run_app.py` | Launch the Streamlit product UI | Active |
| `run_workflow.py` | Run the assembly-assessment workflow in a terminal | Active |
| `run_automation_planning.py` | Run downstream automation planning | Compatibility |
| `run_layout_generation.py` | Render downstream automation layouts | Compatibility |

`run_app.py` and `run_workflow.py` are the only entry points for the first
product pilot. They call code in `src/assembly_automation` and do not import the
legacy workflow, old UI packages, or research evaluator.

## Developer utilities

`scripts/test_*.py` are manual, focused runners for individual nodes or CAD
visualizations. Automated contract and regression checks live under `tests/`.
`scripts/create_sequence_overview.py` regenerates a sequence overview from an
existing session.

`scripts/compare_workflow_runs.py` compares completed product sessions using
manifest stage timestamps and provider-reported runlog tokens. It writes CSV
tables, a Markdown report, and stacked time/token bar charts to
`data/analytics/run_comparison`:

```powershell
python scripts/compare_workflow_runs.py
python scripts/compare_workflow_runs.py --latest 3
python scripts/compare_workflow_runs.py --include-incomplete --session Stehlager
```

## Research and history

- `research/run_evaluation.py`: evaluation entry point.
- `research/scripts/`: previous workflow and experiment runners.
- `research/launchers/`: dataset preparation and experiment launchers.
- `research/configs/`: ablation, sequence-ground-truth, and legacy experiment
  configurations.
- `archived/legacy_ui/`: superseded UI implementations.
- `archived/legacy_launchers/`: old numbered product and environment launchers.

The detailed pre-reorganization inventory is preserved in
`docs/legacy_script_inventory.md`.
