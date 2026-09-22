# Product rebuild

This package is being filled incrementally from the existing implementation.
It does not yet replace the working App V3 launchers.

- `stepparser`: CAD processing and rendering.
- `user_agent`: conversation, document context, and user-facing tools.
- `workflows`: explicit execution definitions, node-local prompts/schemas, shared runtime.
- `data`: session storage, artifacts, revisions, and compatibility.
- `app`: Streamlit and terminal adapters.

The configuration loader and standalone STEP parser are implemented. Run the
parser through `scripts/test_stepparser.py`; its settings live under
`nodes.step_preprocessing` in `configs/appsettingsv3.yaml`. Workflows call it
through the thin `run_step_preprocessing` node adapter, which only delegates to
`StepProcessor` and returns artifact paths. `assembly_analysis` and the
single-part `monopart_analysis` node use the shared configured-input, prompt,
model, tool and structured-execution runtime. The deterministic `bom_merge` node
attaches one analysis to each unique part while preserving placed instances.
`sequence_generation` supports initial generation and feedback-driven revision
with deterministic BOM coverage checks. Workflow fan-out and the remaining
nodes are still pending. App V3 still uses the existing implementation.

See `docs/reorganize.md` for the source inventory, extraction order, and checks.
