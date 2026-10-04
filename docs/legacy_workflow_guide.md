# Getting Started

This project turns STEP assembly data into Fitness for Automation (FfA) assessments and evaluates those assessments against ground truth.

The recommended workflow is organized around the numbered scripts in the repository root. They are intended to be run in order:

```text
1_run_app_workflow_terminal.py
2_export_assy_sequence_ground_truth.py
3_run_experiments_sequence_gt.py
4_prepare_ffa_report_ground_truth_from_run.py
5_run_evaluation.py
```

Think of the pipeline as two phases:

```text
Data preparation:
  STEP file -> interactive app workflow -> approved assembly sequence ground truth

Experiment and evaluation:
  sequence ground truth -> FfA experiment runs -> FfA ground truth export -> metrics/evaluation
```

## Before You Start

Use the Python environment that contains OpenCascade/OCC, Streamlit dependencies, LangChain, and the Azure/OpenAI dependencies used by the repo.

Secrets and model endpoints are expected in environment variables or `.env` files used by the project. The LLM code reads settings from the YAML configs and from environment variables.

Put STEP files here unless a script says otherwise:

```text
data/input/test/
```

Most scripts have an editable configuration block near the top. Start there before running anything.

## Pipeline Overview

### 1. Initial Processing

Script:

```powershell
python 1_run_app_workflow_terminal.py
```

Role:

Runs the app workflow from the terminal. This is the interactive preparation step where the system parses STEP files, analyzes the assembly, generates an assembly sequence, lets you discuss/correct it, renders assembly steps, and creates an initial FfA assessment.

Important top-level settings:

```python
MASTER_STEP_INPUT_FOLDER = "data/input/test"
STEPPARSER_OUTPUT_FOLDER = "data/processed/stepparser3"
LLM_OUTPUT_FOLDER = "data/datapreparation/singletest"
EXPERIMENT_CONFIG_FOLDER = "configs/appconfig"
EXPERIMENT_CONFIG_NAME = "appconfig"
TERMINAL_INTERACTIVE = True
```

Typical output:

```text
data/datapreparation/singletest/appconfig/{assembly_name}/
  input/
  preprocessing/
  Agent_txt_files/
  assembly_sequence_runN/
    assembly_sequence.json
    sequence_renderings/
    interaction_analysis.json
  ffa_assessment/
  ffa_report/
```

Important behavior:

- The latest `assembly_sequence_runN` is the assembly sequence you approved or most recently generated.
- `TERMINAL_INTERACTIVE = True` lets you answer the agents in the terminal.
- Use `--auto` for automatic progression without terminal feedback.

Common commands:

```powershell
python 1_run_app_workflow_terminal.py
python 1_run_app_workflow_terminal.py --assembly "Coupling O Ring"
python 1_run_app_workflow_terminal.py --assembly "Coupling O Ring" --auto
```

### 2. Export Assembly Sequence Ground Truth

Script:

```powershell
python 2_export_assy_sequence_ground_truth.py
```

Role:

Copies the approved app-workflow assembly sequence into the ground-truth format used by the sequence-GT experiment runner.

Input:

```text
data/datapreparation/singletest/appconfig/{assembly_name}/assembly_sequence_runN/
  assembly_sequence.json
  sequence_renderings/
```

Output:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/
  sequence.json
  renderings/
  additional_info_{assembly_name}.txt
```

Important behavior:

- The script detects the latest `assembly_sequence_runN`.
- It copies `assembly_sequence.json` as `sequence.json`.
- It copies `sequence_renderings/` as `renderings/`.
- It creates `additional_info_{assembly_name}.txt` with a placeholder:

```text
Additional Info about the assembly
```

You can edit this text file before running experiments. During sequence-GT experiments, this information is loaded into the assembly analysis and ASGT prompt context.

### 3. Run Experiments Based On Assembly Sequence

Script:

```powershell
python 3_run_experiments_sequence_gt.py
```

Role:

Runs the main experiment workflow using the ground-truth assembly sequence from step 2. The sequence order is fixed by `sequence.json`; the LLM fills/describes the step content and the workflow performs the FfA assessment.

Important top-level settings:

```python
MASTER_STEP_INPUT_FOLDER = "data/input/test"
STEPPARSER_OUTPUT_FOLDER = "data/processed/stepparser3"
LLM_OUTPUT_FOLDER = "data/experiments/test2"
EXPERIMENT_CONFIG_FOLDER = "configs/sequence_gt"
EXPERIMENT_CONFIG_NAME = None
GROUND_TRUTH_SEQUENCE_ROOT = "data/ground_truth/assembly_sequence_ground_truth"
FORCE_LOAD_GT_ADDITIONAL_INFO = True
```

Input:

```text
data/input/test/{assembly_name}.STEP
data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/sequence.json
data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/renderings/
data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/additional_info_{assembly_name}.txt
configs/sequence_gt/*.yaml
```

Output:

```text
data/experiments/test2/{experiment_name}/{assembly_name}/
  {assembly_name}_BOM_enriched.json
  assembly_sequence_run1/
    assembly_sequence.json
    sequence_renderings/        # or copied GT renderings when use_gt_renderings is true
    interaction_analysis.json
  ffa_assessment/
    ffa_assessment.json
  ffa_report/
  experiment_summary.json
```

Important behavior:

- Selective STEP rendering is built in. Existing stepparser results are skipped.
- Existing completed assemblies are skipped when `ffa_assessment/ffa_assessment.json` exists.
- `GROUND_TRUTH_SEQUENCE_ROOT` controls where `sequence.json` and renderings are loaded from.
- `FORCE_LOAD_GT_ADDITIONAL_INFO = True` forces loading of the additional info text even if a YAML config disables `ASGT_use_additional_info`.

Experiment YAMLs:

- Stored in `configs/sequence_gt/` by default.
- Set `EXPERIMENT_CONFIG_NAME` to a YAML stem to run one config.
- Leave `EXPERIMENT_CONFIG_NAME = None` to run all configs in the folder.

### 4. Export FfA Ground Truth

Script:

```powershell
python 4_prepare_ffa_report_ground_truth_from_run.py
```

Role:

Creates FfA ground truth from a completed run. This is used when you want to evaluate later experiments against a curated FfA reference set.

Typical input:

```text
data/experiments/{run_or_experiment_folder}/
```

Typical output:

```text
data/ground_truth/{target_ground_truth_folder}/
```

What it does:

- Discovers assembly folders inside a run or experiment output folder.
- Finds FfA assessment files.
- Converts or copies them into the expected ground-truth format for evaluation.

Check the top config block before running. The important values are usually the source run path and the target ground-truth output folder.

### 5. Run Evaluation

Script:

```powershell
python 5_run_evaluation.py
```

Role:

Evaluates experiment results against FfA ground truth.

Important top-level settings:

```python
RUN_DIR_TO_EVALUATE = Path("data/experiments/test")
AUTO_DISCOVER_MODE = False
EXPERIMENTS_BASE = Path("data/experiments")
GT_EVAL_SET = Path("data/ground_truth/ffa_ground_truth_evaluierungsdaten rev2")
GT_TEST_SET = Path("data/ground_truth/ffa_ground_truth_testdatenMASTER")
```

Metrics include:

- Macro F1, weighted F1, balanced accuracy
- Confusion matrices
- MAE, RMSE, R2, Spearman, Pearson
- Soft score
- Cross-experiment comparison
- Statistical tests
- Plots and CSV exports

Common commands:

```powershell
python 5_run_evaluation.py
python 5_run_evaluation.py data/experiments/test2
python 5_run_evaluation.py --list-runs
python 5_run_evaluation.py --eval-only
python 5_run_evaluation.py --test-only
```

## Data Flow

```text
STEP files
  data/input/test/
    |
    v
1_run_app_workflow_terminal.py
  data/datapreparation/singletest/appconfig/{assembly}/assembly_sequence_runN/
    |
    v
2_export_assy_sequence_ground_truth.py
  data/ground_truth/assembly_sequence_ground_truth/{assembly}/
    sequence.json
    renderings/
    additional_info_{assembly}.txt
    |
    v
3_run_experiments_sequence_gt.py
  data/experiments/test2/{experiment}/{assembly}/
    ffa_assessment/
    ffa_report/
    |
    v
4_prepare_ffa_report_ground_truth_from_run.py
  data/ground_truth/{ffa_ground_truth_folder}/
    |
    v
5_run_evaluation.py
  data/experiments/{run}/evaluation/
```

## Key Concepts

### App Workflow Output

The app workflow is for interactive sequence creation and correction. It produces candidate sequences and renderings. Its output is not automatically ground truth until step 2 exports it.

### Assembly Sequence Ground Truth

The sequence-GT format is:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly}/
  sequence.json
  renderings/
  additional_info_{assembly}.txt
```

`sequence.json` fixes the assembly order. In `3_run_experiments_sequence_gt.py`, the LLM should not invent a new order; it describes or enriches the fixed sequence.

### FfA Ground Truth

FfA ground truth is separate from assembly sequence ground truth. It is used only by evaluation. Step 4 prepares it, and step 5 consumes it.

### YAML Configs

YAML configs control LLM prompts, included images, included JSON keys, FfA mode, interaction analysis, rendering behavior, and model selection.

Common folders:

```text
configs/appconfig/       # interactive app workflow config
configs/sequence_gt/     # sequence-GT experiment configs
configs/prompts.yaml     # consolidated prompt library
```

## Practical Checklist

1. Put STEP files into `data/input/test/`.
2. Run `1_run_app_workflow_terminal.py`.
3. Review the latest `assembly_sequence_runN/assembly_sequence.json`.
4. Run `2_export_assy_sequence_ground_truth.py`.
5. Edit `additional_info_{assembly}.txt` in the GT folder if needed.
6. Run `3_run_experiments_sequence_gt.py`.
7. Inspect `ffa_assessment.json` and reports.
8. Run `4_prepare_ffa_report_ground_truth_from_run.py` when you want to create/update FfA ground truth.
9. Run `5_run_evaluation.py` to compare experiment outputs against FfA ground truth.

## Troubleshooting

### The experiment runner says GT sequence not found

Check:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly}/sequence.json
```

The `{assembly}` folder name must match the assembly folder name from the stepparser output and the STEP filename stem.

### Renderings are missing

For app workflow export, check:

```text
data/datapreparation/singletest/appconfig/{assembly}/assembly_sequence_runN/sequence_renderings/
```

For sequence-GT experiments, check:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly}/renderings/
```

### Additional info is not appearing in prompts

Check:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly}/additional_info_{assembly}.txt
```

`3_run_experiments_sequence_gt.py` has:

```python
FORCE_LOAD_GT_ADDITIONAL_INFO = True
```

### A run is skipped unexpectedly

Completed assemblies are skipped when this exists:

```text
data/experiments/.../{assembly}/ffa_assessment/ffa_assessment.json
```

Delete or move the assembly output folder if you intentionally want to rerun it.

### Assembly names with spaces

Names such as `Coupling O Ring` are supported, but the name must be consistent across:

```text
STEP filename stem
stepparser assembly folder
ground truth assembly folder
experiment output assembly folder
```

## Developer Notes

The core workflow nodes live in:

```text
agent/workflow.py
```

Important domain modules:

```text
agent/Assembly_sequence_generation.py
agent/Assembly_sequence_validation.py
agent/Interaction_analysis.py
agent/FFA_assessment.py
agent/tools.py
agent/structured_output.py
```

The UI and terminal app workflow call into the same app workflow:

```text
scripts/app_workflow_v2.py
ui/app.py
```

The numbered scripts are the recommended public entry points for this project.
