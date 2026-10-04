# Streamlit product UI

This package is the product adapter for the reorganized assembly-assessment
workflow. It must not import legacy `agent/` modules or
`scripts/app_workflow_v3.py`.

## Runtime model

`SessionController` owns one background worker and a FIFO command queue. All
mutations enter through `UserFacingAgent` and `WorkflowAgentTools`; Streamlit
components never write workflow artifacts. A process-level registry rejects a
second active controller for the same session.

Opening the app creates a lightweight marked draft under `data/sessions/.drafts`
and immediately queues a deterministic, tool-free introduction. It does not use
an LLM because the introduction shares the assessment command queue and must not
delay a user who starts immediately. The UI shows the draft and complete workflow
track before a STEP file is uploaded. The introduction is cached and copied into
the durable conversation when the assessment starts. Starting a new
assessment, resuming an existing session, or stopping the controller removes the
draft. Marked drafts older than 24 hours are removed when another controller is
created.

Durable truth lives in the session directory:

- `manifest.json` publishes active artifact paths and workflow stages;
- `09_user_agent/state.json` stores active/approved revisions and stale flags;
- `09_user_agent/conversation.json` stores the visible dialogue;
- node outputs remain the authoritative structured artifacts.

`session_view.py` reconstructs an immutable snapshot from these files after a
browser refresh. `image_catalog.py` indexes only documented image directories
and the active sequence revision. Do not replace these with recursive scans.

## Linked artifact navigation

The middle structured-output pane owns the shared `SelectionContext`. Its
primary segmented control selects assembly analysis, monopart analysis,
assembly sequence, interaction analysis, or FfA analysis. A second control
selects a part or step only where the artifact requires it. The right visual
workspace filters its images from that context and never changes the selected
artifact or entity. Navigation away from an edited record remains guarded by
the save, discard, or stay dialog.

## Event flow

Agent and workflow callbacks are normalized in `events.py`. Every event has an
event ID, timestamp, session ID, correlation ID and product event type. The UI
drains the queue from a lightweight Streamlit fragment. Events trigger a new
disk snapshot; event payloads are progress hints, not authoritative state.
The UI tracks the correlation ID of its active command, so completion of an
earlier background introduction cannot clear the busy state of a later queued
workflow command.

The visual workspace is a separate two-second fragment. While work is active it
rescans only the documented image roots and displays the newest completed files,
so sequential CAD renderings become visible before the entire node finishes.

## UI actions

Chat calls `submit_user_turn`. Sequence approval/revision and artifact patches
call `submit_tool_action`, which uses the agent's configured tool allowlist and
persists the exact user action in conversation history. JSON patches receive a
client-side diff preview, then the artifact editor performs schema validation,
history backup, atomic replacement and stale-state propagation.

## Running and testing

Launch with the repository entry point:

```powershell
& C:\Users\Mika\miniforge3\envs\apa-occ\python.exe .\8_open_streamlit_app_v3.py
```

The UI requires the same LLM environment variables as the configured
`user_agent.llm` profile. Headless rendering can be checked with
`streamlit.testing.v1.AppTest`; unit tests are in
`tests/test_streamlit_session.py` and `tests/test_user_agent.py`.
