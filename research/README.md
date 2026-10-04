# Research and evaluation

This directory contains code and configuration that evaluates product outputs
or reproduces pre-product experiments. Nothing under `src/assembly_automation`
imports this directory.

- `evaluation/`: FfA metrics, comparisons, plots, and dataset summaries.
- `configs/`: ablation studies, sequence-ground-truth profiles, and historical
  experiment settings.
- `scripts/`: legacy workflow and experiment implementations.
- `launchers/`: data preparation and experiment entry points.
- `run_evaluation.py`: main evaluation command.

Run commands from the repository root so relative dataset paths continue to
resolve against `data/`. For example:

```powershell
python research/run_evaluation.py --help
```

The research runtime still uses the root `agent` and `stepparser` compatibility
packages. The active product does not.
