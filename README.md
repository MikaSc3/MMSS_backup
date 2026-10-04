# Assembly Automation

The product turns a STEP assembly into editable assembly and part knowledge,
an assembly sequence, interaction and FfA assessments, and HTML reports. The
active implementation is the installable `assembly_automation` package under
`src/`.

## Run the product

Use the Python environment that contains pythonOCC and the optional LLM/UI
dependencies. From the repository root:

```powershell
python run_app.py
```

The launcher selects the first free Streamlit port from 8501 through 8599.
Pass Streamlit flags directly when needed:

```powershell
python run_app.py --server.port 8510
```

Run the same workflow in a terminal with:

```powershell
python run_workflow.py
python run_workflow.py --step-file data/input/lager/example.step
python run_workflow.py --session-root data/sessions/<session_id>
```

The default STEP input directory is `data/input/lager`, the main configuration
is `configs/appsettingsv3.yaml`, and product sessions are stored under
`data/sessions`.

## Repository map

- `src/assembly_automation/stepparser`: STEP loading, geometry relations,
  rendering, image selection, and diagrams.
- `src/assembly_automation/workflows`: node implementations, shared LLM
  runtime, and the end-to-end workflow definition.
- `src/assembly_automation/user_agent`: dialogue, feedback, workflow tools,
  and audited artifact changes.
- `src/assembly_automation/app`: Streamlit and terminal adapters.
- `configs/appsettingsv3.yaml`: active product and node configuration.
- `data`: input and generated session data.
- `scripts`: focused developer utilities and manual component tests.
- `tests`: automated product tests.
- `research`: evaluation code, experiment configurations, and legacy
  experiment runners.
- `archived`: superseded UI implementations and historical launchers.

Automation planning and layout generation remain available through
`run_automation_planning.py` and `run_layout_generation.py`. They still use the
legacy `agent` compatibility package while those downstream modules await their
own product extraction.

See [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) for setup and validation,
and [docs/reorganize.md](docs/reorganize.md) for architecture decisions.

## Repeatable evaluation

> **Status:** The evaluation workflow is currently unfinished and not working
> reliably. Keep the scripts for further development, but do not treat their
> experiment runs, metrics, or diagrams as validated results yet.

```powershell
python eval_system.py
```

The experiment runner prompts for an evaluation name and description and creates
`data/evaluations/<timestamp>_<name>/`. It processes every STEP file in
`data/input/Evaluierungsset`, pins the assembly sequence to ground truth,
caches only deterministic STEP preprocessing and the fixed ground-truth
renderings, and then executes four independent repetitions without the
conversational agent. Every repetition generates its own assembly analysis,
monopart analyses/enriched BOM, interaction analysis, and FFA assessment. That
run-local context propagates through the whole repetition; only the evaluated
sequence and images remain fixed. The ground-truth sequence is not validated
against the generated BOM. Change the repetition count with `-n`.

Generate or regenerate metrics afterward without rerunning the experiment:

```powershell
python eval_metrics.py "data/evaluations/<timestamp>_<name>"
```

The resulting `evaluation` subfolder contains the requested
`ground_truth_ffa_vs_runs.png`, a per-run CSV, macro-F1 and supporting metrics,
and an explicit list of assemblies for which no FFA ground truth exists.
