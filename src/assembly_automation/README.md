# `assembly_automation` package

This is the active product implementation.

- `stepparser` owns STEP/XCAF ingestion, assembly and part geometry, spatial
  evidence, rendering, image selection, and diagrams.
- `workflows/runtime` owns configuration, prompts, model construction, tools,
  execution, and run records.
- `workflows/nodes` contains deterministic and LLM-backed nodes with local
  prompts and structured outputs.
- `workflows/definitions/app_v3.py` composes the assessment workflow and its
  review checkpoints.
- `user_agent` owns dialogue, bounded artifact access, feedback, revisions,
  and semantic artifact changes.
- `app/streamlit` is the durable three-pane product UI.
- `app/cli.py` is the terminal adapter used by `run_workflow.py` and the
  installed `assembly-workflow` command.

Product runtime code must not import the root `agent` or `stepparser` packages,
the archived UIs, or `research.evaluation`. Configuration for the product lives
in `configs/appsettingsv3.yaml`; node prompts and schemas live with each node.
