# User-facing agent

This package is the conversational control layer for the reorganized App V3
workflow. It uses the shared LLM profiles from `configs/appsettingsv3.yaml` and
can only change workflow state through the allowlisted tools in `tools.py`.

## Dialogue checkpoints

1. Supporting information and user context are extracted, summarized and
   confirmed.
2. Assembly analysis is presented for correction.
3. Unique-part analyses and the enriched BOM are presented for correction.
4. Each sequence revision is presented until the user explicitly approves it.
5. The final FfA report is presented and can be discussed or regenerated from
   newly recorded assessment feedback.

STEP preprocessing is automatic. Rendering, interaction analysis, FfA scoring
and report generation remain one final tool because there is no useful user
decision between those stages.

## Tool boundary

`WorkflowAgentTools` exposes session inspection, document ingestion,
assembly analysis, monopart analysis, natural-language artifact
correction, sequence generation/revision, final assessment, focused artifact
reading, and bounded part lookup. `read_artifact` is the single conversational
artifact reader: it accepts a fixed request vocabulary for assembly context,
BOM, sequence, report, automation artifacts, or one exact part ID. It resolves
paths and active revisions internally and does not accept JSON or filesystem
paths. `inspect_session` includes the available part IDs and compact name and
quantity metadata so the agent can select valid IDs before a detailed read. It
also returns revision inventories for sequences and automation-planning
artifacts, with an explicit active flag for the current revision. Versioned
entity requests use validated selectors such as `r002:step_003` or
`layout_r001:Robot`; arbitrary JSON paths are not accepted. `summarize_parts`
remains available for paginated part summaries. It does not expose filesystem
browsing or individual internal nodes.

The tools enforce dependencies. Assembly feedback makes assembly analysis and
all downstream artifacts stale. Part/BOM feedback makes sequence and final
artifacts stale. Sequence changes invalidate renderings and assessment results.
The agent calls final assessment only after the user accepts the active
sequence in dialogue.

## Feedback and edits

Accepted feedback is append-only in `09_user_agent/feedback.json`. Each event has
a scope, optional targets, the original user message and the agent's concise
summary. Prompt context is compiled per node, so unrelated dialogue is not sent
to every model call. Sequence revision always receives the first generated
sequence plus cumulative accepted sequence feedback.

`change_artifact(artifact, change, revision_id="")` is the normal chat path for
a correction to any assessment or automation-planning JSON artifact. A
deterministic resolver selects the named complete artifact and active revision.
A dedicated structured-output LLM receives the whole artifact plus the user's
change request, updates every affected location, and returns a complete
replacement. The replacement passes source-hash and full-schema validation
before it is saved. The general-purpose context-change tool has been removed;
future planning preferences use the dedicated idea, concept, layout, or cost
tools instead.

`edit_artifact_fields` remains the exact field-level path used by the visual
editor. Both paths write atomically and save the prior file plus an audit
record below `11_history/artifact_edits/`. Semantic changes also write their
prompt, complete rewrite, model usage and application hash
below `10_runs/artifact_change/`. The generic JSON Merge Patch tool remains for
explicit schema-valid changes outside both constrained editors. A part change
keeps monopart analysis current and marks sequence/rendering/final results
stale; it does not rerun monopart analysis.

The agent prompt documents the strict flat product contract. Assembly and
sequence fields live directly at their artifact roots. A BOM part's analysis
fields live directly below `part_analysis`. The retired `analysis`,
`monopart_analysis` and `sequence` result wrappers are not supported. Runtime
inputs, prompt hashes, model information and token usage belong to `10_runs/`
and are not presented as domain findings.

## Session files

```text
09_user_agent/
  state.json
  feedback.json
  conversation.json
  documents/
    manifest.json
    raw/
    extracted/
  artifact_history/
```

Superseded LLM node artifacts are also moved into numbered `history/` folders
beside their active artifact.

## Terminal test

```powershell
& C:\Users\Mika\miniforge3\envs\apa-occ\python.exe scripts/test_user_facing_agent.py
```

Use `--supporting-file` more than once for optional documents. Resume a session
with `--session-root <path>`. The terminal adapter is intentionally thin; UI
code should construct the same workflow, toolbox and agent objects.
