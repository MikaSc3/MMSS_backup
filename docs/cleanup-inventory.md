# Reorganization cleanup inventory

Updated: 2026-09-24

This inventory records the final migration classification. It is based on
static import searches from the active entry points, the accepted end-to-end
workflow run, and the automated product suite.

| Path | Classification | Evidence and decision |
| --- | --- | --- |
| `run_app.py` | Product entry point | Launches only `src/assembly_automation/app/streamlit/app.py`. |
| `run_workflow.py` | Product entry point | Calls `assembly_automation.app.cli`; usable independently of the current directory. |
| `src/assembly_automation` | Product runtime | Contains the STEP parser, workflow nodes/runtime, user agent, session behavior, UI, and CLI. |
| `configs/appsettingsv3.yaml` | Product configuration | Loaded by both product adapters and all workflow tests. |
| `data` | Product/session data | Contains inputs, models, generated sessions, and retained research datasets. It is not importable code. |
| `scripts/test_*.py` | Developer utilities | Focused manual runners for the reorganized package. They are not workflow implementations. |
| `tests` | Product verification | Unit and integration contracts for parser, workflow, agent, editing, reporting, and UI helpers. |
| `research/evaluation` | Research | Evaluation consumes product outputs; product runtime has no reverse dependency. |
| `research/configs` | Research | Ablation, sequence-ground-truth, test, and historical experiment profiles. |
| `research/scripts` and `research/launchers` | Research/legacy reproducibility | Previous workflow and experiment runners retained with updated package paths. |
| `archived/legacy_ui` | Archive | Old Streamlit/Reflex and App V3 prototypes; no active product imports. |
| `archived/legacy_launchers` | Archive | Superseded numbered launchers retained for history. |
| `agent` and root `stepparser` | Compatibility runtime | No product imports. Retained temporarily because automation planning/layout and historical research still call them. |
| `run_automation_planning.py` and `run_layout_generation.py` | Compatibility entry points | Preserve the separate downstream workflow. Their implementation has not yet been rebuilt as product nodes. |
| `configs/default_settings.yaml` and `configs/prompts.yaml` | Compatibility resources | Used by the retained legacy runtime and research runners. |
| `configs/automationplanner.yaml` | Downstream configuration | Used by the retained automation-planning entry point. |

## Verified dependency boundary

Searches under `src/assembly_automation` find no imports from `agent`, the root
`stepparser`, archived UI packages, or `research.evaluation`. The evaluator was
moved only after production FfA scoring and report generation had local node
implementations and resources.

## Deferred removal

The root `agent` and `stepparser` compatibility packages can be removed after
automation planning and layout generation are rebuilt under
`src/assembly_automation/workflows/nodes`. Removing them earlier would break
those documented downstream commands and the preserved research runners.
