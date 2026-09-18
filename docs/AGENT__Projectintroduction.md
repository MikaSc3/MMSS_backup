# AGENT Project Introduction

Last updated: 2026-06-15

This document is a fast handoff for coding agents working on this repository. It captures the project shape, entry points, moving parts, and local conventions so an agent can start productively without rediscovering the basics.

## Project Purpose

This project turns CAD STEP assemblies into Fitness for Automation (FfA) assessments.

At a high level:

```text
STEP assembly
  -> OpenCascade/pythonOCC parsing and rendering
  -> part and assembly metadata
  -> LLM-based enrichment and sequence reasoning
  -> assembly sequence renderings
  -> FfA assessment and report
  -> evaluation against ground truth
```

The core domain is assembly analysis for automation feasibility. The system combines geometry extraction, rendered images, structured LLM outputs, workflow orchestration, and evaluation metrics.

## Current Root Layout

The root was recently cleaned up. Keep this layout unless the user asks otherwise.

```text
0_env_test.py
1_run_app_workflow_terminal.py
2_export_assy_sequence_ground_truth.py
3_run_experiments_sequence_gt.py
4_prepare_ffa_report_ground_truth_from_run.py
5_run_evaluation.py
6_open_streamlit_app.py
7_run_app_workflow_AGENT_terminal.py
8_open_streamlit_app_v3.py
env-latest.yaml
docs/
scripts/
agent/
appv3/
stepparser/
evaluation/
ui/
configs/
data/
archived/
```

Root is intended to contain only numbered workflow entry scripts, environment files, and top-level project folders.

Markdown documentation belongs in `docs/`.

Unnumbered helper/workflow scripts belong in `scripts/`.

## Main Pipeline

The recommended workflow is the numbered scripts in the project root:

```text
1_run_app_workflow_terminal.py
2_export_assy_sequence_ground_truth.py
3_run_experiments_sequence_gt.py
4_prepare_ffa_report_ground_truth_from_run.py
5_run_evaluation.py
```

### 1. Interactive App Workflow

Entry point:

```powershell
python 1_run_app_workflow_terminal.py
```

Purpose:

- Parse STEP input.
- Run the interactive app workflow.
- Let the user approve or revise the generated assembly sequence.
- Render assembly steps.
- Produce initial FfA assessment/report artifacts.

Important implementation file:

```text
scripts/app_workflow_v2.py
```

Imports were updated after cleanup:

```python
from scripts.app_workflow_v2 import ...
```

The legacy Streamlit UI under `ui/` also imports `scripts.app_workflow_v2`.

## App V3: Agent-Driven Streamlit Application

App V3 is the current agent-driven interactive application. It is separate from
the older `ui/` application described later in this document.

Launch it with:

```powershell
python 8_open_streamlit_app_v3.py
```

The terminal version of the same workflow can be launched with:

```powershell
python 7_run_app_workflow_AGENT_terminal.py
```

### V3 Architecture

Important files:

```text
8_open_streamlit_app_v3.py          # Finds a free port and launches Streamlit
appv3/app.py                        # Streamlit layout, CSS, chat, progress, visualization
appv3/runner.py                     # Background threads and session creation
appv3/state.py                      # Streamlit session state and event processing
appv3/visualization.py              # Artifact-driven stage visualization
scripts/app_workflow_v3.py          # Content-agent workflow and UI event emission
agent/app_workflow_v3_tools.py      # Grouped workflow tools called by the agent
```

The Streamlit process and workflow communicate through thread-safe queues:

```text
workflow thread -> v3_event_queue -> appv3/state.py -> Streamlit session state
Streamlit input -> v3_input_queue -> workflow thread
```

Do not call Streamlit APIs from the background workflow thread. Emit plain event
dictionaries through `ui_callback` instead.

Important event types include:

```text
session_created
agent_message
input_waiting
input_received
phase_changed
documents_ingested
tool_started
tool_completed
tool_failed
artifacts
complete
error
```

The live workspace is a Streamlit fragment that reruns every second. Long-running
stages should therefore expose progress through events or incrementally written
artifacts rather than relying on a final return value.

### V3 Workflow Tools And Stages

The content agent controls these grouped tools in order:

```text
Preprocess_Input_Data_tool
Readadditional_Data_tool
Set_Content_Context_tool
Analyse_Assembly_tool
Analyse_Monoparts_And_Merge_tool
Generate_Or_Revise_Sequence_tool
Run_Final_Assessment_Pipeline_tool
Finish_Workflow_tool
```

The final assessment tool contains several internal UI phases:

```text
FINAL_RENDERING
FINAL_INTERACTIONS
FINAL_FFA
FINAL_REPORT
```

`scripts/app_workflow_v3.py` emits tool and phase events. The underlying grouped
operations live in `agent/app_workflow_v3_tools.py`, while the individual
workflow nodes remain in `agent/workflow.py`.

The main V3 config is:

```text
configs/appconfig/appconfigV2.yaml
```

The content-agent and tool prompts are loaded from:

```text
configs/prompts.yaml
```

### V3 Session And Artifact Layout

Each UI run creates:

```text
data/sessions_v3/{UTC timestamp}_{assembly_name}/
```

Typical artifacts:

```text
input/
preprocessing/stepparser/
Agent_txt_files/
enriched_parts/
assembly_{assembly_name}_Overview_Enriched.json
{assembly_name}_BOM_enriched.json
assembly_sequence_runN/
  assembly_sequence.json
  sequence_renderings/
  interaction_analysis_partial.json   # Exists only while IA is running
  interaction_analysis.json
ffa_assessment/ffa_assessment.json
ffa_report/
  {assembly_name}_ffa_report.json
  {assembly_name}_ffa_report.pdf
  {assembly_name}_ffa_report_V2.pdf
```

The interaction-analysis worker writes
`interaction_analysis_partial.json` atomically after each completed step. The
file is removed after the final `interaction_analysis.json` is saved. Preserve
this behavior when changing parallel interaction analysis because the V3 UI
uses it for live structured-output progress.

### V3 Visualization Rules

`appv3/visualization.py` reads real artifacts from disk. It must not invent
structured-output values. User-facing fact lists are intentionally capped at
four items.

Current stage behavior:

- Assembly analysis displays fields such as `assembly_description`,
  `partslist`, and `primary_function`.
- Monopart progress uses unique geometries, not total assembly instances.
  Duplicate `_copy` parts are excluded from the analysis denominator.
- Before monopart results exist, the image carousel uses normal ISO1 and ISO4
  views of unique parts.
- Sequence generation displays actual assembly-overview and enriched-BOM input
  fields while waiting, then switches to `assembly_sequence.json`.
- Sequence rendering cycles through all currently completed normal ISO1 step
  renderings.
- Interaction analysis cycles through sequence steps and reads partial/final
  structured interaction output. Pending steps fall back to real sequence
  fields such as process, base part, and joining part.
- FfA assessment cycles through sequence steps and displays the matching
  `overall_ffa` structured output when available.
- FfA report generation displays real FfA step assessments while the report is
  being consolidated.

Sequence image selection is deliberately strict:

```text
step_XX_iso1_transp_0_0.png
```

Do not accidentally include:

```text
step_XX_iso1_exp_transp_0_0.png
step_XX_iso2_*.png
step_XX_section_*.png
```

Section images are analysis inputs, not the normal user-facing sequence
carousel.

Monopart carousel images are:

```text
part_XXX-iso1_transp_0_0.png
part_XXX-iso4_transp_0_0.png
```

Copied instances such as `part_003_copy1` must remain excluded.

### V3 Report Generation

FfA PDFs are not generated from an HTML template. They are rendered with
Matplotlib in:

```text
agent/ffa_post_processing.py
```

Both standard and V2 step pages should use the same gauge-only bottom-right
panel. V2 intentionally omits the old "ASSESSMENT IN WORDS" text from that
cell. V2 also omits part pages and uses a primary-function block on its summary
page.

The Streamlit app packages all available report PDFs into one ZIP download.

### V3 Maintenance Notes

- Keep workflow logic independent from Streamlit; communicate through events
  and filesystem artifacts.
- Scope sequence, interaction, and rendering artifacts to the active
  `assembly_sequence_runN`, especially after revisions.
- Use atomic writes for artifacts read by the one-second UI refresh.
- Keep carousels time-based and rebuild their candidate list each fragment run
  so newly rendered steps appear automatically.
- The checked-in `venv/` may reference a missing local Python installation.
  Do not assume it is runnable; use the configured project environment.
- The generic system Python may lack Matplotlib, pandas, LangChain, or
  pythonOCC. Syntax checks can still use `python -m py_compile`, but full
  workflow/report tests need the real project environment.

### 2. Export Assembly Sequence Ground Truth

Entry point:

```powershell
python 2_export_assy_sequence_ground_truth.py
```

Purpose:

- Finds the latest approved `assembly_sequence_runN`.
- Copies `assembly_sequence.json` to GT `sequence.json`.
- Copies `sequence_renderings/` to GT `renderings/`.
- Creates or updates `additional_info_{assembly_name}.txt`.

Typical output:

```text
data/ground_truth/assembly_sequence_ground_truth/{assembly_name}/
```

### 3. Sequence-GT Experiments

Entry point:

```powershell
python 3_run_experiments_sequence_gt.py
```

Purpose:

- Runs experiments where assembly order comes from ground truth, not from an LLM-generated order.
- Uses `sequence.json` and GT renderings/additional info.
- Runs enrichment, sequence description/validation, FfA assessment, and reporting.

Important defaults live near the top of the script:

```python
MASTER_STEP_INPUT_FOLDER = "data/input/test"
STEPPARSER_OUTPUT_FOLDER = "data/processed/stepparser3"
LLM_OUTPUT_FOLDER = "data/experiments/test2"
EXPERIMENT_CONFIG_FOLDER = "configs/sequence_gt"
GROUND_TRUTH_SEQUENCE_ROOT = "data/ground_truth/assembly_sequence_ground_truth"
```

### 4. Export FfA Ground Truth

Entry point:

```powershell
python 4_prepare_ffa_report_ground_truth_from_run.py
```

Purpose:

- Converts selected experiment outputs into FfA ground truth.
- Used before evaluation when curating a reference dataset.

### 5. Evaluation

Entry point:

```powershell
python 5_run_evaluation.py
```

Purpose:

- Evaluates FfA outputs against ground truth.
- Produces metrics, plots, HTML summaries, confusion matrices, and statistical comparisons.

The script now points users toward:

```powershell
python scripts/run_experiments.py
```

if no run is found.

## Helper Scripts

Moved helper scripts live in `scripts/`:

```text
scripts/app_workflow_v2.py
scripts/batch_render_from_sequences.py
scripts/create_checkpoint_from_run.py
scripts/full_workflow_experiments.py
scripts/run_assembly_sequence_generation.py
scripts/run_experiments.py
scripts/run_stepparser.py
```

Because these moved down one directory, their workspace root should generally be:

```python
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
```

If adding new scripts under `scripts/`, insert `WORKSPACE_ROOT` into `sys.path` before importing `agent`, `stepparser`, or other repo modules.

## Important Packages And Modules

### `stepparser/`

CAD/geometry side.

Key responsibilities:

- Load STEP files.
- Use pythonOCC/OpenCascade.
- Split assemblies/parts.
- Compute metadata such as bounding boxes, volume, surface area, features.
- Render views, explosions, sections, and assembly sequence images.

Important files:

```text
stepparser/processor.py
stepparser/rendering/renderer.py
stepparser/core/assembly.py
stepparser/core/part.py
stepparser/core/data_classes.py
stepparser/io/metadata_manager.py
```

Renderer notes:

- Uses `OCC.Display.SimpleGui.init_display`.
- Uses `BRepPrimAPI_MakeBox`, `AIS_Shape`, `Quantity_Color`, etc.
- The renderer contains Windows/OpenGL stability handling. Be careful before changing display lifecycle, `FitAll`, redraws, `RemoveAll`, or image dump behavior.

### `agent/`

LLM/workflow side.

Key responsibilities:

- Workflow nodes.
- LangChain/OpenAI calls.
- Structured output schemas.
- Agent managers.
- Prompt loading.
- FfA assessment logic.
- Assembly sequence generation/validation.
- Checkpoint utilities.

Important files:

```text
agent/workflow.py
agent/tools.py
agent/structured_output.py
agent/prompt_store.py
agent/config.py
agent/config_utils.py
agent/checkpoint_utils.py
agent/Assembly_sequence_generation.py
agent/Assembly_sequence_validation.py
agent/FFA_assessment.py
agent/agent_managers.py
agent/agent2_sequence_validator.py
```

LLM import pattern used in workflows:

```python
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
```

Model registry pattern appears in `agent/tools.py` and `agent/workflow.py`.

Common model aliases:

```text
4o   -> AzureChatOpenAI, deployment gpt-4o
4.1  -> AzureChatOpenAI, deployment gpt-4.1
5.4  -> ChatOpenAI via /openai/v1/, deployment gpt-5.4
```

Common env vars:

```text
AZURE_ENDPOINT_4O
AZURE_ENDPOINT_41
AZURE_ENDPOINT_54
AZURE_ENDPOINT
AZURE_API_VERSION
AZURE_DEPLOYMENT_54
API_KEY_GPT_4
API_KEY_GPT_5
```

### `evaluation/`

Evaluation and reporting side.

Key responsibilities:

- FfA scoring.
- Enum/string conversion.
- Metrics.
- Aggregation.
- Visualization.
- Dataset overview.

Important files:

```text
evaluation/ffa_evaluator.py
evaluation/ffa_scoring.py
evaluation/ffa_metrics.py
evaluation/ffa_visualization.py
evaluation/ffa_str_to_enum.py
evaluation/ffa_enum_to_str.py
```

### `ui/`

Legacy/earlier Streamlit UI side. For App V3, use `appv3/`.

Important files:

```text
ui/app.py
ui/workflow_runner.py
ui/components/
```

`ui/workflow_runner.py` runs the older app workflow in a background thread and imports from `scripts.app_workflow_v2`.

## Configuration

Main config folders:

```text
configs/appconfig/
configs/sequence_gt/
configs/test/
configs/prompts.yaml
configs/default_settings.yaml
```

Experiment scripts often have editable top-level constants. Always inspect the first 50-100 lines before running a script.

Prompt and experiment settings are loaded through `agent.prompt_store` and `agent.config_utils`.

## Data Layout

Common paths:

```text
data/input/test/                              # STEP files for current workflow runs
data/input/ALL/                               # broader STEP collection
data/input/Textbased_Data/                    # per-assembly textual context
data/processed/stepparser/                    # default stepparser output
data/processed/stepparser3/                   # frequently used current processed output
data/datapreparation/singletest/              # interactive preparation outputs
data/ground_truth/assembly_sequence_ground_truth/
data/experiments/                             # experiment runs
data/checkpoints/                             # legacy/manual checkpoint snapshots; not used by normal workflow
data/sessions/                                # app/UI sessions
data/sessions_v3/                             # App V3 agent-driven sessions
```

Output structures are nested and often assembly-specific. Do not rename output folders casually; many scripts infer paths by convention.

## Environment Smoke Test

Root contains:

```text
0_env_test.py
```

It is a quick test script for:

- LangChain/OpenAI imports.
- Interactive LLM call.
- pythonOCC viewer with a simple box.

Run it only in the environment with `langchain_openai` and pythonOCC installed. It will open a GUI viewer.

## Development Conventions

Use `rg`/`rg --files` for searching.

Prefer existing patterns in `agent/tools.py`, `agent/workflow.py`, and `stepparser/rendering/renderer.py`.

Keep root clean:

- Numbered entry scripts stay in root.
- Markdown goes in `docs/`.
- Unnumbered helper scripts go in `scripts/`.
- Archived/old material stays in `archived/`.

When moving scripts:

- Check imports from numbered scripts and UI.
- Check `Path(__file__).resolve().parent` assumptions.
- Patch usage strings in docs and CLI messages.
- Compile changed Python files with `python -m py_compile`.

When editing workflow behavior:

- Be careful with path conventions.
- Preserve checkpoint compatibility.
- Preserve structured output schemas unless the caller is updated.
- Avoid broad refactors unless explicitly requested.

When editing rendering/OCC behavior:

- Treat display lifecycle and offscreen rendering as fragile.
- Test with a minimal geometry first.
- Avoid unnecessary `Redraw`/`UpdateCurrentViewer` changes.

When editing LLM behavior:

- Check both `agent/tools.py` and `agent/workflow.py` for duplicate model setup patterns.
- Keep Azure env-var fallbacks intact.
- Prefer structured outputs already defined in `agent/structured_output.py`.

## Known Gotchas

- Some documentation and archived files contain old script names or old root paths. Prefer live root numbered scripts plus `scripts/`.
- Some docs have encoding artifacts from previous Windows/terminal handling. Do not rewrite huge docs just to fix encoding unless asked.
- `python` in a generic shell may not be the correct environment. Use the environment described by `env-latest.yaml`.
- LLM calls need the correct `.env`/Azure credentials.
- OCC rendering may open real windows and can hang if display/event-loop assumptions are changed.
- The git working tree may contain many unrelated changes. Do not revert them unless the user explicitly asks.
- Normal workflows should not create `data/checkpoints/`; checkpoint creation is disabled in `3_run_experiments_sequence_gt.py` and `scripts/full_workflow_experiments.py`.

## Useful Verification Commands

Compile changed Python files:

```powershell
python -m py_compile path\to\file.py
```

Compile the recently moved script set:

```powershell
python -m py_compile 1_run_app_workflow_terminal.py 5_run_evaluation.py ui\workflow_runner.py scripts\__init__.py scripts\app_workflow_v2.py scripts\batch_render_from_sequences.py scripts\create_checkpoint_from_run.py scripts\full_workflow_experiments.py scripts\run_assembly_sequence_generation.py scripts\run_experiments.py scripts\run_stepparser.py
```

Inspect root cleanliness:

```powershell
Get-ChildItem -Path . -File | Select-Object Name | Sort-Object Name
```

## Starting Point For Future Agents

If asked to work on this project, first read:

```text
docs/AGENT__Projectintroduction.md
docs/GETTING_STARTED.md
docs/IMPORTANT_SCRIPTS.md
```

Then inspect the specific script or module involved. Most tasks should not require reading the entire repository.
