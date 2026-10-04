# App V3 assembly-assessment workflow

`app_v3.py` composes the product nodes without importing legacy workflow or
evaluation modules. The workflow owns session paths, parallel fan-out, partial
aggregates, sequence approval, stage events, retries and the session manifest.

## Public entry points

```python
from assembly_automation.workflows.definitions import AssemblyAssessmentWorkflow

workflow = AssemblyAssessmentWorkflow(
    session_root="data/sessions/<session_id>",
    settings=appsettings,
    event_callback=handle_event,  # optional
)

# Interactive flow: stop after sequence generation.
checkpoint = workflow.prepare_through_sequence(
    step_file="input/assembly.STEP",
    revision_id="r001",
    user_context=user_context,
)

# Continue after the user accepts or edits the generated sequence.
result = workflow.complete_from_sequence(
    revision_id="r001",
    approved_sequence=checkpoint["sequence"],
    user_context=user_context,
)
```

For terminal automation, `workflow.run(..., approve_sequence=True)` executes
both phases. With the default `False`, it returns
`awaiting_sequence_approval`. Sequence revision calls use a new revision ID and
`sequence_mode="revise"`, while upstream STEP, assembly and monopart artifacts
are reused.

## Session layout

```text
01_input/<assembly>.STEP
02_preprocessing/
03_assembly/revisions/<revision_id>/
  assembly_overview.json
04_monoparts/revisions/<revision_id>/
  parts/<part_id>.json
  analyses.json
  bom.json
05_sequence/revisions/<revision_id>/
  assembly_sequence.json
  renderings/
  interaction_analysis/
    steps/step_NNN.json
    interaction_analysis.json
06_assessment/revisions/<revision_id>/
  steps/step_NNN.json
  ffa_assessment.json
  ffa_scores.json
07_reports/revisions/<revision_id>/
  report.json
  rendered/
08_planning/
09_user_agent/
10_runs/
11_history/
manifest.json
artifact_registry.json
```

The manifest stores session-relative artifact references. The artifact registry
stores active and historical revisions for assembly, monoparts, sequence,
assessment, reports, and planning artifacts.
sequence revision. Fan-out writes an atomic partial aggregate after each
completed item, then replaces it with an ordered final aggregate and removes
the partial file. Existing valid per-item files are reused after interruption.
Incomplete preprocessing and sequence-rendering directories are preserved as
`*.failed_NN` before a retry.

Events include `stage_started`, `stage_progress`, `stage_completed`,
`stage_failed`, `checkpoint` and `workflow_completed`. App V3 can adapt these
events to its current UI event contract without putting Streamlit behavior into
the workflow.

Report rendering is configured for self-contained HTML only. PDF output remains
disabled until a stable product PDF backend is selected.

## Terminal smoke test

Run the real workflow against the default STEP file in `data/input/lager`:

```powershell
& C:\Users\Mika\miniforge3\envs\apa-occ\python.exe scripts/test_app_v3_workflow.py
```

The script creates a timestamped session below `data/workflow_tests`, prints
stage progress and pauses at the sequence checkpoint. Use `--auto` to approve
the first generated sequence automatically. `--step-file`, `--session-root`,
`--context` and `--constraints` are also available.
