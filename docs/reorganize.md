# App V3 code reorganization plan

Updated: 2026-09-24. Status: product workflow migration and first cleanup pass complete.

## Rebuild outcome

The first product pilot now runs entirely through the installable
`src/assembly_automation` package. The package contains the standalone STEP
parser, shared node runtime, all assessment nodes, durable workflow/session
state, user-facing agent, semantic artifact editing, terminal adapter, and the
three-pane Streamlit UI. The accepted end-to-end run covers STEP preprocessing,
assembly and monopart review, sequence generation/revision/rendering,
interaction analysis, FfA classification/scoring, and HTML reporting.

The active entry points are `run_app.py` and `run_workflow.py`. Experimental
evaluation and configurations live under `research/`; superseded UI prototypes
and numbered launchers live under `archived/`. The full classification and
dependency evidence are recorded in `docs/cleanup-inventory.md`.

Final verification on 2026-09-24 compiled the product and research trees,
loaded both product entry points from outside the repository, and passed all
117 `unittest` cases in the pythonOCC environment.

The root `agent` and `stepparser` packages remain as an explicit compatibility
boundary for the separate automation-planning/layout commands and historical
research runners. The product package has no imports from them. Their eventual
removal depends on rebuilding those downstream modules, which is outside this
pilot cleanup. PDF output also remains deliberately deferred; report rendering
produces self-contained HTML.

The detailed dated progress sections below are retained as migration history.
Statements describing a later node or UI integration as "next" reflect the
state on their recorded date and are superseded by this outcome section.

## Goal and boundaries

Make the existing App V3 workflow the product foundation. Preserve its STEP processing, document ingestion, assembly and monopart analysis, sequence dialogue, interaction analysis, FfA assessment, reports, and continuing report discussion. Organize code into STEP parser, user-facing agent, workflows, session data services, and application adapters.

Keep `docs/` and all existing documentation. Preserve existing session data, configuration variants, and research results. Retain research/evaluation tooling outside the product runtime as the default; permanent deletion requires a proven dependency inventory. Automation planning and layout rendering remain available as a separate downstream workflow, without expanding the first pilot.

This plan is based on documentation, imports, function searches, and targeted source inspection. It is not a runtime verification or an exhaustive proof that any file is unused.

## Target folder structure

Use one installable package to avoid collisions with generic names such as `data`, `app`, and `scripts`. `assembly_automation` is the internal package name, not a customer-facing brand.

```text
repository/
  pyproject.toml
  run_app.py                         # Thin Streamlit launcher
  run_workflow.py                    # Thin terminal launcher
  src/
    assembly_automation/
      stepparser/                    # Preserve existing internal organization initially
        core/
        analysis/
        identification/
        bom/
        io/
        rendering/
      user_agent/
        agent.py                     # Conversation and tool-calling loop
        context.py
        document_ingestion.py
        tools.py                     # Workflow/edit interfaces exposed to the agent
        prompts.yaml
      workflows/
        definitions/
          assembly_assessment.py
          automation_planning.py
        runtime/
          configuration.py
          model_factory.py
          prompting.py
          execution.py
          events.py
          registry.py
        nodes/
          step_preprocessing/
          document_summary/
          assembly_analysis/
          monopart_analysis/
          bom_merge/
          sequence_generation/
          sequence_rendering/
          interaction_analysis/
          ffa_assessment/
          ffa_scoring/
          report_synthesis/
          report_rendering/
          automation_requirements/
          process_principles/
          automation_variants/
          layout_planning/
          layout_rendering/
      data/                          # Code that manages session data
        schemas.py                   # Shared identities and execution/revision records
        storage.py
        artifacts.py
        revisions.py
        compatibility.py
      app/
        streamlit/
          app.py
          runner.py
          state.py
          visualization.py
        cli.py
        assets/
  configs/
    defaults.yaml
    appsettingsv3.yaml               # Main product configuration
    profiles/                        # Explicit experimental overrides
    scoring/
      ffa_scoring_mapping.json
  data/                              # Original and generated session data
    sessions/
      <session_id>/
  research/
    scripts/
    evaluation/
    configs/
  tests/
  docs/                              # Existing contents retained
  archived/                          # Existing history retained
```

Each LLM node owns `node.py`, `inputs.py`, `prompts.yaml`, `structured_output.py`, and, where domain checks justify it, `validation.py`. Add focused helper files only when the implementation needs them. Deterministic nodes do not need prompts or LLM schemas. The user agent owns its conversational prompt; workflow node prompts stay with their nodes. Do not keep a second authoritative root prompt library after migration.

The prompt migration is complete. All 83 entries from the former global library are assigned exactly once to an owning module. Current `system_v1`, `human_v1`, generation, and revision prompts incorporate the useful engineering instructions against the new flat schemas. Numbered `legacy_###_*` entries retain the original variants, provenance, and hashes for experiments; they are historical references rather than runtime defaults. The complete cross-reference is in [prompt-migration.md](prompt-migration.md), and `test_prompt_migration.py` checks coverage, uniqueness, source fidelity, and formatter safety.

### Naming and enumeration

- Use the same descriptive `snake_case` node IDs in directories, config keys, prompt namespaces, events, execution records, and artifact metadata.
- Express order and dependencies in workflow definitions. Do not number source folders or launchers. Keep legacy numbered launchers as forwarding wrappers during migration.
- Within a node's `prompts.yaml`, use role/task IDs such as `system_v1`, `human_v1`, and `revise_v1`; their qualified names are `assembly_analysis.system_v1`, for example. Keep schema IDs such as `assembly_analysis_v1` in a local registry.
- Version prompts, schemas, and result revisions separately. A prompt change does not automatically change the output schema.
- Preserve existing entity IDs, including copied part instances. Use zero-padded ordinals for new image/file sequences, but do not renumber old entities or assume an ordinal is an immutable identity after sequence revisions.
- Name new artifacts by purpose (`assembly_overview.json`, `bom.json`, `assembly_sequence.json`), with assembly name and identity in metadata rather than repeated in every filename.
- Use UTC session timestamps plus a collision-resistant suffix for new sessions; preserve all existing session IDs.

## Observed implementation and migration map

### Application and user agent

The active UI chain is `8_open_streamlit_app_v3.py` -> `appv3/app.py` -> `appv3/runner.py` -> `scripts/app_workflow_v3.py`. Preserve the free-port launcher, background execution, event/input queues, one-second live refresh, artifact previews, ZIP report download, and report Q&A.

Move `appv3` into the application adapter. Split the agent-controlled loop, tool observations, conversation memory, and checkpoint dialogue out of `scripts/app_workflow_v3.py` into `user_agent`; move CLI discovery and argument handling into the terminal adapter. Move `agent/content_agent.py` and `agent/content_ingestion.py` by responsibility rather than copying them wholesale.

V3 directly imports `discover_assembly`, `load_config`, and `load_prompt_library` from `scripts/app_workflow_v2.py`. Extract these helpers before moving V2 to research/legacy. That module also wraps stdout/stderr at import time on Windows; terminal setup must move to the CLI boundary so importing the product does not rewrite process streams.

The UI references `ui/assets/logos/JointLogo.png`. Verify whether this asset exists and preserve or explicitly replace the reference before relocating the old UI. Audit artifact-discovery patterns, report selection, and active sequence selection in both the app and visualization code.

### Workflow nodes and domain code

`agent/app_workflow_v3_tools.py` groups calls to private functions in `agent/workflow.py`. Its grouped agent tools should remain user-facing operations, while their component nodes become independently defined execution units.

| Target responsibility | Current implementation to extract or wrap |
| --- | --- |
| STEP preprocessing/path resolution | V3 grouped tools, `StepProcessor`, `_node_resolve_paths` |
| Document summary/context | `ContentAgent`, ingestion helpers, V3 read/set-context tools |
| Assembly analysis | `_node_run_assembly`, `agent/tools.py::analyse_assembly_img`, shared image describer |
| Monopart analysis | `_node_list_parts`, `_node_run_monoparts`, `analyse_monopart_img` |
| Copy handling and BOM merge | `_node_merge_copy_part_data`, `_node_merge_bom`, `agent/merge_enriched.py` |
| Sequence generation/revision | Sequence nodes, `agent/Assembly_sequence_generation.py` |
| Sequence rendering | `_node_render_assembly_steps`, rendering code inside `agent/Assembly_sequence_validation.py` |
| Interaction analysis | Interaction node, `agent/Interaction_analysis.py` |
| FfA classification | Assessment node, `agent/FFA_assessment.py` |
| Deterministic FfA scoring | Relevant scoring/parser/aggregation helpers currently in `evaluation/` |
| Report synthesis | `_node_ffa_reporter` and report compaction helpers in `agent/workflow.py` |
| PDF/chart/export rendering | Post-processing node, `agent/ffa_post_processing.py` |
| Downstream automation/layout | `agent/automation_planner.py`, `agent/layout_generator.py`, launchers 9 and 10 |

Do not remove `Assembly_sequence_validation.py` because ASV is disabled: it also contains required sequence rendering. Separate optional LLM validation from CAD rendering. Preserve renderer display lifecycle and Windows/OpenGL behavior during structural migration.

`agent/tools.py` combines model setup, image selection/encoding, JSON field filtering, prompt construction, persistence, and analysis entry points. Extract common execution/prompt helpers into workflow runtime, persistence into data services, and node-specific analysis into its node folder. Inspect `agent/utils.py`, text processing, configuration classes, checkpoint imports, and merge logic for their transitive dependencies before moving them.

`agent/structured_output.py` contains analysis, sequence, interaction, FfA, reporting, geometry, and automation schemas. Move each schema family with its owner, preserving field names and defaults initially. Keep genuinely shared CAD/entity types in shared data or STEP parser contracts. Maintain old import aliases until callers migrate; audit `agent/schemas/` separately rather than assuming it duplicates the active schemas.

### Hidden product dependencies in evaluation

`agent/ffa_post_processing.py` imports criterion records, parsing/constants, plots, and scoring from `evaluation/ffa_evaluator.py`, `ffa_plots.py`, and `ffa_scoring.py`. The evaluator imports SciPy. Extract production scoring/report helpers first; research evaluation should consume the product scoring rules, not be imported by the product.

The scoring mapping currently lives at `data/ground_truth/mapping/ffa_scoring_mapping.json`. It is a product rule resource, not session output. Move its authoritative copy to `configs/scoring/` and give research a compatible reference. Preserve option IDs, labels, weights, and numerical behavior.

## Configuration and vanilla node contract

Main configuration: `configs/appsettingsv3.yaml`. Resolve defaults -> main config -> explicitly selected profile using recursive mapping merges; lists replace earlier lists. Do not discover implicit root `experiment.yaml` overrides. Freeze the resolved configuration for each execution.

```yaml
workflow: assembly_assessment
llms:
  profiles:
    gpt_5_4:
      provider: azure_openai_v1
      model: gpt-5.4
      endpoint_env: AZURE_ENDPOINT_54
      api_key_env: API_KEY_GPT_5
    llama_local:
      provider: openai_compatible
      model: llama3.2-vision
      base_url: http://localhost:11434/v1
nodes:
  assembly_analysis:
    enabled: true
    llm:
      profile: gpt_5_4
      max_completion_tokens: 4000
    prompts:
      system: system_v1
      human: human_v1
    structured_output: assembly_analysis_v1
    tools: []
    inputs:
      assembly_metadata:
        enabled: true
        required: true
        kind: json
        source: assembly
        fields: [total_parts, unique_parts, geometry.size]
      assembly_images:
        enabled: true
        required: true
        kind: images
        source: images
        path: assembly
        patterns: [collage_assembly.png]
        limit: 1
        downscale_factor: 0.7
      user_context:
        enabled: true
        kind: text
        source: user_context
        max_chars: 12000
    execution:
      max_tool_rounds: 4
```

A vanilla LLM node declares required artifact inputs, builds a configured prompt payload, resolves local prompt/schema IDs, executes via shared infrastructure, validates its output, and returns a structured result plus artifact references. Runtime saves actual token usage, elapsed time, model identity, prompt hashes, schema version, selected inputs and tool-call counts. Config specifies token budgets; actual usage is measured.

The prompt builder handles JSON field selection, optional list-item selection,
text blocks and deterministic image selection. Input sources are semantic artifact
keys supplied by the workflow, so nodes do not search for legacy filenames.
Paths and patterns may use invocation variables such as `{part_id}`.

Workflow definitions own fan-out. `assembly_analysis` invokes once. The
implemented `monopart_analysis` node analyzes exactly one unique `part_id`; its
future workflow reads the BOM, creates one invocation context per unique part,
and calls the node for each. Parallelism, retry and result aggregation stay in
workflow execution instead of the node or prompt builder.

Models are named profiles under `llms.profiles`. A node selects a profile and may
override bounded generation settings. The current factory supports Azure OpenAI,
Azure's OpenAI-compatible v1 endpoint, OpenAI and local/OpenAI-compatible servers.
Optional tools are node-local allowlists resolved against a runtime registry; an
empty list means the model receives no tools.

Preserve nested JSON field selectors, image filters/limits/downscaling, context toggles, generation/revision prompts, examples, model overrides, and parallel worker settings from the existing configs. Translate legacy `AAI`, `AMI`, `ASG`, `IA`, `FFA`, and reporter settings explicitly; do not silently discard settings. Map existing filename keywords and `NONE` sentinels to semantic sources and explicit enabled flags.

Preflight must reject unknown prompts/schemas/config keys, invalid field selectors, unsupported required inputs, and incompatible output schemas. Disabling a prerequisite requires a valid existing result or an explicitly supported workflow branch. Preserve documented optional context behavior. Schema selection uses an allowlisted node registry; downstream contracts determine compatibility.

Current loaders in `agent/prompt_store.py`, `agent/tools.py`, V2, and `agent/config.py` overlap. Consolidate loading and invalidate prompt caches between explicitly changed configurations. Keep Azure credential/environment fallbacks through one model factory; do not snapshot secrets. No live API calls are required to inspect or migrate configuration.

## Session artifacts, edits, and compatibility

Use root `data/` for session inputs/results and package `data/` for their management code. Initially keep all current paths and JSON shapes. The later layout for new sessions is:

```text
data/sessions/<session_id>/
  input/
  preprocessing/
  context/
  assembly_analysis/assembly_overview.json
  monopart_analysis/parts/<part_id>.json
  monopart_analysis/bom.json
  sequence/revisions/<revision_id>/
    assembly_sequence.json
    renderings/
    interaction_analysis.json
  ffa_assessment/
  reports/
  automation_planning/
  revisions/
  executions/
  manifest.json
```

Provide a reader adapter for existing `sessions_v3`, `Agent_txt_files`, enriched filenames, and `assembly_sequence_runN` structures. Do not rewrite historical sessions. Introduce new paths only after every producer, UI reader, report reader, exporter, and research consumer is migrated together. The manifest identifies active artifact revisions instead of relying on newest-file globbing.

The inspected baseline is `data/sessions_v3/2026-09-17_143937_Stehlager_Sicherungsring`. Its overview combines CAD facts with analyst text; its BOM combines geometry and inferred monopart analyses. The BOM records an absolute datasource path from another checkout. Replace new stored references with session-relative artifact references and resolve old references through the compatibility layer.

The consolidated BOM becomes authoritative for unique-part geometry, optional detailed surfaces and placed instances; no separate part-metadata files are required. Assembly metadata belongs in `assembly.json`, with a relative file reference to the separate `spatial_relations.json`. Preserve geometry-vs-instance relationships and copied instances. Keep original CAD facts as source evidence; user corrections are explicit overrides rather than destructive changes to original metadata.

Both direct UI edits and agent edits use one validated revision service. Preserve previous values, author/source, reason, and dependency provenance. Prevent stale edits and writes to results currently being regenerated. Mark affected descendants outdated; rerun only the affected dependency closure. Revoke sequence approval when the sequence changes. Keep report discussion grounded in the active result revisions.

Structured results and context are editable. Images/PDFs are viewable/downloadable and regenerated from edited source data. Preserve atomic partial interaction-analysis writes and their removal after final completion. Keep assessment/report artifacts tied to the sequence revision that produced them.

Replace process-global `APA_EXPERIMENT_OUTPUT_DIR`, `APA_EXPERIMENT_YAML`, and STEP/input-path routing with explicit execution/session context. Preprocessing currently copies results into shared `data/processed/stepparser`; remove that dependency only after sequence rendering accepts explicit session-local inputs. Concurrent sessions must not share output paths or configuration.

## Implementation phases and inspection checklist

Phases 1 through 4 are complete for the first pilot. Phase 5 is complete for
the product runtime, UI prototypes, evaluation code, experiment configs, and
entry points. The compatibility runtime needed by downstream automation
planning/layout is intentionally retained and documented rather than deleted.

1. **Baseline and inventory.** Build a static import/call/resource map, including lazy imports, runtime tool registrations, prompts, scoring mappings, assets, and artifact readers/writers. Inspect full implementations of the source families above, UI state/events, numbered launchers, experiment scripts, and environment manifests. Check `backend/`, tracked assets, archived tests, alternative agents, and duplicate enrichment workflows individually. Record keep/extract/research/archive decisions with evidence. Capture a baseline small-assembly run in the actual OCC/LLM environment before behavioral migration.
2. **Package and shared infrastructure.** Add packaging and thin launchers. Extract config/prompt loading, model factory, events, explicit execution context, and storage while leaving existing node behavior behind adapters. Resolve package resources independently of the working directory. Preserve old launcher/import compatibility.
3. **Extract nodes and local resources.** Move analysis, merge, sequence, rendering, interaction, FfA, scoring, and reporting one subsystem at a time. Split the schema and prompt libraries by ownership. Translate the active App V3 config into `appsettingsv3.yaml`; retain research variants. Switch V3 to public workflow interfaces and remove runtime dependence on V2/evaluation.
4. **Session contracts and edit foundation.** Add execution manifests, authoritative artifact references, revisions, invalidation, and common edit interfaces. Then add UI/agent editing and selective reruns as a distinct feature phase; do not hide these behavioral changes inside file moves. Migrate new-session paths behind compatible readers.
5. **Research separation and final cleanup.** Move experiment/GT/evaluation entry points and their configs under research after product dependencies are extracted. Preserve downstream planning/layout tools. Archive proven superseded code; delete only confirmed dead code after searches and checks pass. Update README/current docs with active entry points while retaining historical docs.

### Validation and acceptance

- Compile/import the installed package and launch both UI and CLI from a different working directory; imports must not start viewers, rewrite streams, or make model calls.
- Validate all active prompt references, schema selections, templates, nested field filters, image choices, and translated settings. Verify baseline profile parity and explicit profile overrides.
- Compare the saved example's artifact loading, unique-part counts, copy handling, sequence/interaction step matching, and standard/V2 report behavior before and after migration.
- Test deterministic scoring against the original mapping and representative assessments; numerical output must remain unchanged.
- Test the queue/event bridge through assembly confirmation, sequence revision/approval, final phases, error handling, and continuing report Q&A. Mock model responses for migration checks; use a small real assembly for OCC rendering validation.
- Test revisions, BOM/part synchronization, stale-edit rejection, dependency invalidation, sequence approval reset, atomic partial outputs, and session isolation when the edit phase is implemented.
- Verify research exporters/evaluation still consume legacy and new compatible outputs, and automation/layout tools retain their documented outputs.
- No code is classified unused solely because it is absent from the direct V3 import list. No existing docs or session data are removed.

Completion means App V3 runs through the new package with local node resources and explicit configuration/session context, produces compatible results, and no longer imports legacy workflow or research evaluation modules. A full hosting/API/frontend redesign is outside this reorganization.

## STEP parser implementation progress (2026-09-18)

The standalone parser now lives in `src/assembly_automation/stepparser`, with
settings in `configs/appsettingsv3.yaml` and a runnable
`scripts/test_stepparser.py`. It writes consolidated assembly/BOM JSON, a stage
manifest and configurable images, using XCAF placements, normalized units,
early BREP validation and geometric distance/contact maps. Details and run
instructions are in the module's `stepparser.md`.

The registered `C:/Users/Mika/miniforge3/envs/apa-occ` environment was located
and used for thirteen focused checks, a real-example geometry run and rendering
checks. App V3 integration, artifact editing/revisions and remaining workflow
extractions are pending. The legacy parser and original session data remain intact.

## Sequence rendering implementation progress (2026-09-21)

The deterministic `sequence_rendering` node now lives under
`src/assembly_automation/workflows/nodes/sequence_rendering`. It accepts an
explicit STEP file, approved sequence, enriched BOM and empty revision output
directory. It uses physical `instance_id` values and the new XCAF loader rather
than rediscovering legacy experiment paths, rerunning BREP analysis, or assigning
a second set of identifiers.

The useful legacy visualization behavior remains: cumulative normal and
exploded views plus before/after XY, XZ and YZ sections centered on the current
joining geometry. It adds an optional current-part highlight. The implementation
uses the StepParser's persistent viewer, batched camera capture, matte material,
origin axes, whitespace cropping and cached bounds. Boolean section results are
cached by instance, plane and cut coordinate, and OCC parallel booleans are
configurable. Stable filenames retain the selectors required by later visual
nodes; entropy and failures are stored in `rendering_summary.json`.

Focused unit tests and a real two-part OCC smoke run pass. The node has not yet
replaced the legacy App V3 workflow call; that switch belongs in workflow
composition after the remaining downstream nodes have explicit artifact inputs.

## Interaction analysis implementation progress (2026-09-21)

The new `interaction_analysis` package defines one configured LLM invocation per
assembly step. It has local prompts and structured output, uses the shared model,
prompt, tool and execution runtime, and accepts explicit sequence, BOM, spatial,
interlocking and rendering artifacts. Its required visual input is the new step
collage; before-state section images are optional supporting evidence.

Input preparation resolves copies through BOM instance-to-definition links and
filters geometric distances and interlocking blockers to the actual sequence
state, preventing future parts from leaking into the current-step assessment.
Parallel fan-out settings are declared in config but remain workflow-owned.
The future workflow must write per-step results atomically, update a partial
aggregate after each completion, and replace it with the final ordered artifact.

## FFA assessment implementation progress (2026-09-23)

The new `ffa_assessment` package defines one complete FFA classification per
sequence step. It consumes the matching interaction result, step collage,
before sections, joining-part collage and enriched BOM evidence through explicit
artifact references. Its local schema preserves every historical enum string so
the deterministic scoring mapping remains compatible, while adding validation
for complete subprocess summaries, evidence and drawbacks.

The legacy shared cache has not been copied: it performed the full LLM call and
then overwrote repeated Separation/Handling results, providing consistency but
no token or latency reduction. Parallelism and any future unique-part intrinsic
assessment reuse remain workflow-owned. The next extraction is deterministic
`ffa_scoring`, followed by report synthesis and rendering.

## FFA scoring implementation progress (2026-09-23)

The new `ffa_scoring` package deterministically converts the exact structured
FFA classifications into criterion, subprocess, per-step and aggregate scores.
It accepts explicit assessment artifacts, validates step identity and mapping
coverage, sorts output deterministically, rejects incomplete classifications in
strict mode and writes atomically. It has no LLM, NumPy, plotting or research
dependency. Every result records the mapping version, status and content hash.

The supplied historical `ffa_scoring_mapping.json` has now been migrated into
the package resource. Every option ID, exact label, numeric value, criterion
weight and subprocess weight is retained, together with the source-file hash.
The product scorer accepts both structured-output strings and integer annotation
IDs. Representative mixed-value results and direct comparisons against the
legacy scorer verify numerical parity. The next extraction is report synthesis
and report rendering.

## Report synthesis implementation progress (2026-09-23)

The new `report_synthesis` package replaces the large presentation-oriented
reporter prompt with a decision-layer architecture. A deterministic builder
collects authoritative assembly, BOM, sequence, FFA and scoring data into a
compact evidence catalog. The LLM only deduplicates, prioritizes and phrases
cross-step findings and recommendations. A deterministic compiler then creates
the editable `report.json` and links every result to stable source references.

Scores, step summaries, part facts, unknowns and image references are no longer
rewritten by the LLM. Validation state is stored in fields instead of prose
markers. Source-derived recommendations must cite an existing improvement;
new proposals are explicitly hypotheses with assumptions. The report is the
single content model for the user-facing agent and future rendering profiles.
The deterministic `report_rendering` package now creates self-contained
executive and engineering-detail HTML outputs over this same JSON. The unstable
PDF execution path was removed and configuration explicitly rejects PDF until a
stable product backend is selected.

## End-to-end workflow implementation progress (2026-09-23)

The new `workflows/definitions/app_v3.py` composes all extracted public nodes
through explicit artifacts. It creates the target session layout, supports the
sequence-approval checkpoint and revision IDs, owns parallel monopart,
interaction and FFA fan-out, publishes atomic partial/final aggregates and
maintains a session-relative manifest. Completed per-item artifacts are reused
after interruption; incomplete geometry-rendering directories are preserved
before retry rather than overwritten.

Report rendering is active for self-contained executive and engineering HTML
profiles. PDF remains disabled pending a stable backend. The product Streamlit
adapter now calls this workflow definition directly and maps workflow events to
the durable UI state. Artifact revisions, validation, dependency invalidation,
and audited semantic changes are implemented in the user-agent package.

## User-facing agent implementation progress (2026-09-23)

The new `src/assembly_automation/user_agent` package now controls the product
workflow through a small allowlisted tool surface. The workflow definition has
public preprocessing, assembly-analysis, monopart/BOM and sequence-generation
phases, so dialogue can stop at assembly review, BOM review and sequence
approval without duplicating node orchestration.

User feedback is stored as scoped, append-only events and compiled into the
context relevant to each downstream node. Dependency state prevents stale
assembly, BOM or sequence artifacts from reaching final assessment. Sequence
revision uses the initially generated sequence and cumulative accepted feedback;
final assessment requires explicit approval of the active revision.

The assembly overview, enriched BOM and sequence can be changed through a
validated JSON Merge Patch tool. Every edit retains the previous artifact and
an audit record. LLM reruns archive superseded outputs in numbered history
folders. Authorized TXT, Markdown, JSON, YAML, CSV, TSV, DOCX and optionally PDF
supporting files can be extracted for review before their confirmed meaning is
recorded as workflow context.

`scripts/test_user_facing_agent.py` remains a focused interactive developer
runner. The product UI uses the same agent and toolbox objects through
`assembly_automation.app.streamlit.controller`; UI behavior does not leak into
the workflow or agent.

## UI requirements for the product App V3 (2026-09-23)

### Product intent

The new UI is a technical workspace for one assembly-assessment session. Its
primary layout is always visible and follows the original concept:

```text
+------------------------------------------------------------------------------+
| Session / assembly / workflow state / uploads / compact stage progress      |
+-------------------+---------------------------------+------------------------+
| Dialogue          | Visual evidence                 | Structured results     |
| user + agent      | assembly / part / step images   | JSON-derived views     |
|                   |                                 | and validated editing  |
+-------------------+---------------------------------+------------------------+
```

Desktop proportions should begin near `30% / 44% / 26%`, with user-resizable
panes if Streamlit can support them reliably. On narrower screens the structured
results pane moves below the visual pane; chat remains first. The work area
should use the available viewport instead of growing into a long dashboard.

The visual language should feel like an engineering application: graphite or
deep navy surfaces, restrained cyan/green operational accents, orange only for
attention and active processing, thin grid/coordinate motifs, compact
monospaced metadata and high-contrast readable content. Decorative gradients,
large marketing cards and oversized empty space should be avoided. Light and
dark themes are not both required for the first implementation; the first
theme must nevertheless meet accessible contrast and focus-state requirements.

### Findings from the existing UIs

Useful behavior to retain:

- STEP plus supporting-document upload.
- A compact stage/progress indicator.
- A non-blocking worker and event queue.
- Stage-aware selection of assembly, monopart and sequence images.
- Session-local artifacts and downloadable reports.
- Persistent conversation and resumable sessions.

Behavior to replace:

- `appv3/runner.py` still starts the legacy `scripts/app_workflow_v3.py`; the
  new UI must construct `AssemblyAssessmentWorkflow`, `WorkflowAgentTools` and
  `UserFacingAgent` from `src/assembly_automation` directly.
- The old UI runs one long workflow thread that blocks on an input queue. The
  product agent is turn-based: each submitted message is one queued agent turn,
  and the tool called during that turn may run a long workflow phase.
- Artifact selection currently relies heavily on recursive `rglob` scans and
  legacy filename patterns. The manifest, active revision and tool results must
  be the authoritative artifact index.
- Chat is enabled only when the old workflow explicitly requests input. The new
  chat remains available whenever no agent turn is executing.
- The current visualization pane mixes image display and technical facts. The
  new middle pane owns visual evidence; the right pane owns structured data,
  status, provenance and editing.
- Automatic image cycling makes detailed comparison difficult. Users need a
  stable selected image, explicit navigation and optional autoplay.

### Top session bar

The top bar is compact and sticky. Before a session starts it contains the STEP
upload, multiple supporting-file upload and Start action. After start it shows:

- assembly/session name and short session ID;
- connection/worker state: idle, thinking, running tool, failed or complete;
- current checkpoint: context, assembly review, BOM review, sequence review or
  final assessment;
- active sequence revision and approval state;
- a compact stage strip with running/complete/failed state;
- Resume/New Session and artifact/report download actions.

Starting creates the session and saves uploads before the first agent turn. A
session browser may initially be a simple select box listing valid manifests;
resume must reconstruct state from `manifest.json`, `user_agent/state.json` and
`user_agent/conversation.json`, not from transient Streamlit state.

### Left pane: dialogue and decisions

The left pane is the primary control surface, not a log window.

- Render persisted user and agent messages with compact timestamps and clear
  separation from tool/status events.
- Stream or progressively reveal agent text when supported. Tool execution is
  represented by one collapsible activity card rather than chat spam.
- Keep the composer enabled whenever the session worker is idle. Disable it
  only while the current agent turn is executing; allow Cancel only when the
  underlying operation can be cancelled safely.
- Support multiline input and attachments already authorized for the session.
- Show contextual quick actions at explicit checkpoints: confirm/correct
  context, accept/edit assembly understanding, accept/edit BOM, approve/revise
  sequence, regenerate assessment and open report.
- Quick actions must enqueue ordinary audited user turns or validated tool
  commands. They must not mutate JSON or approval state directly in Streamlit.
- Sequence approval requires the existing explicit approval tool. A generic
  Continue button must never imply approval.
- Preserve the exact user message used for feedback, edits, revisions and
  approval so the feedback ledger remains authoritative.

### Middle pane: visual evidence

The middle pane displays stable visual evidence with a large primary canvas and
a compact filmstrip or selector row.

Required visual groups:

- Assembly: selected collage, named views, exploded views, distance/contact
  diagram and part-universe/interlocking diagram when present.
- Parts: part selector plus collage, isolated views and highlighted-in-assembly
  view. Copies share the definition views and expose their instance IDs.
- Sequence: revision selector, step selector, collage, assembled/exploded,
  highlighted joining parts and before/after sections.
- Assessment: current step image alongside the relevant interaction/FfA result.

The active workflow checkpoint chooses a sensible initial group, but the user
can pin any image and navigate completed evidence while later tools run. The UI
must not replace a selected image every few seconds. Optional autoplay is a
user-controlled mode. Image labels come from rendering manifests and metadata,
not filename fragments displayed to the user.

Image loading should be cached by absolute path, modification time and size.
Only paths published below the active session may be displayed. Missing or
partially written images use a clear placeholder without breaking the pane.

### Right pane: structured results

The right pane is an artifact inspector driven by JSON, with tabs or a compact
artifact selector for:

- Assembly overview;
- Enriched BOM and selected part;
- Sequence and selected step;
- Interaction and FfA result for the selected step;
- Scores and final report;
- Provenance/activity for technical inspection.

Default views are concise typed cards/tables, not raw JSON dumps. A Raw JSON
view remains available in a collapsible technical section. Large artifacts are
loaded by section and capped; the UI should never inject an entire large report
or BOM into the page when only one part or step is selected.

The assembly overview, BOM and sequence expose an Edit mode backed by
`edit_intermediate_artifact`. The first implementation may use structured
forms for common fields and a JSON editor for advanced changes. Before apply it
must show a diff, validation result and downstream invalidation impact. Apply
creates an audited agent/tool action and refreshes the manifest-backed view.
No UI component writes generated JSON directly.

During fan-out stages the pane may show partial progress and completed items as
they arrive. A partial aggregate is labelled `in progress`; it cannot be edited
or mistaken for the active final artifact. Validation/provenance badges should
distinguish generated, user-edited, superseded, stale and approved artifacts.

### Workflow and agent integration

The Streamlit layer needs a session controller rather than imports from legacy
scripts. Recommended package boundary:

```text
src/assembly_automation/app/streamlit/
  app.py                 # composition only
  controller.py          # one worker and command queue per session
  events.py              # product event schema and adapters
  session_view.py        # manifest-backed read model
  artifact_presenters.py # bounded typed JSON projections
  image_catalog.py       # manifest-backed visual groups
  components/
    topbar.py
    chat.py
    visuals.py
    structured_results.py
```

The controller owns a single FIFO command queue. Commands include `user_turn`,
`start_session`, `resume_session` and validated UI actions. Only one mutating
command runs per session. A `user_turn` calls `UserFacingAgent.invoke`; its
agent events and the nested workflow events are normalized and sent to the UI
event queue. The UI thread only drains events and renders the persisted session.

All product events should carry `event_id`, timestamp, session ID, correlation
ID and type. Required event families:

```text
agent.message.delta / agent.message.completed
agent.turn.started / agent.turn.completed / agent.turn.failed
tool.started / tool.completed / tool.failed
workflow.stage.started / progress / completed / failed
workflow.checkpoint
artifact.published / artifact.updated / artifact.stale
session.created / resumed / completed
```

The current workflow event contract needs two small extensions for an efficient
UI:

1. `stage_completed` and `checkpoint` should include published artifact IDs and
   session-relative paths.
2. Fan-out completion should emit `artifact.updated` with the partial aggregate
   ID, completed item ID and counts. The UI can then refresh one bounded view
   without polling the directory tree.

Tool results may include a non-authoritative `ui_focus` hint such as
`{"pane":"sequence","revision":"r002","step_id":3}`. The controller may use
that to select a useful visual/result. Artifact paths and workflow truth still
come from the manifest.

### Session read model and synchronization

Streamlit session state contains presentation state only: selected tab, part,
step, image, open editor and the queues/controller handle. Durable truth stays
on disk. `session_view.py` creates one immutable snapshot from:

- `manifest.json`;
- `user_agent/state.json`;
- `user_agent/conversation.json`;
- the active artifacts referenced by the manifest;
- rendering summaries/manifests referenced from those artifacts.

Snapshots are refreshed when an artifact/session event arrives and once after a
browser reconnect. While a command runs, a lightweight fragment can drain the
event queue every 0.5–1 second. Idle pages should stop aggressive polling.
Events are deduplicated by `event_id`, allowing Streamlit reruns without
duplicated messages or progress entries.

### Reliability, safety and performance

- Never access arbitrary paths from chat/tool output. Resolve artifact and
  image IDs through the active session manifest and verify containment.
- Sanitize rendered text; avoid general `unsafe_allow_html` for generated model
  content.
- Enforce upload type and size limits before saving; show extraction warnings.
- Keep one mutating worker per session and reject duplicate Start/Approve/Edit
  commands using command IDs.
- Persist conversation/tool outcome before acknowledging completion in the UI.
- Recover from browser reloads and worker failure without losing completed node
  artifacts. A failed command leaves the composer usable and exposes Resume or
  Retry when safe.
- Avoid recursive filesystem scans on every Streamlit rerun. Cache bounded JSON
  projections and images using path metadata; invalidate caches from events.
- Never hold full image bytes or large JSON documents permanently in
  `st.session_state`.

### First implementation scope

The first working UI must provide:

1. new/resumed session setup with STEP and optional supporting files;
2. real chat turns through the reorganized `UserFacingAgent`;
3. the three-pane desktop workspace and responsive stacking;
4. manifest-backed assembly, part and sequence image navigation;
5. assembly overview, BOM, sequence and final report structured views;
6. sequence approve/revise actions and validated overview/BOM/sequence edits;
7. live stage/tool progress, stale/approval state and recoverable errors;
8. HTML report download and session artifact bundle download.

PDF stays out of scope. A general-purpose workflow debugger, research/evaluation
controls, free filesystem browser and arbitrary JSON editing are also out of
scope for the product UI.

### Acceptance criteria

- A new session can proceed through every dialogue checkpoint and final report
  without importing `agent/` or `scripts/app_workflow_v3.py`.
- Refreshing or reopening the browser reconstructs conversation, progress,
  selected active revision and available artifacts from the session.
- Assembly/BOM/sequence corrections show a diff, validate, create history and
  visibly mark all affected downstream artifacts stale.
- The final pipeline cannot start before explicit approval of the active
  sequence revision.
- Images and structured results update from events during long stages without
  blocking chat rendering or scanning the full session tree every second.
- Two browser sessions cannot execute concurrent mutating commands against the
  same session without a visible lock/rejection.
- The layout remains usable at 1440×900 and common laptop widths, supports
  keyboard navigation and does not rely on color alone for status.
- Component and controller tests use fake workflow/agent events; one manual
  smoke run verifies upload, assembly review, BOM review, sequence revision,
  approval, final assessment and session resume.

### Implementation status (2026-09-23)

The first durable UI implementation now lives in
`src/assembly_automation/app/streamlit/`. The repository launcher points to
this package. It uses the reorganized workflow and user-facing agent directly;
the legacy App V3 workflow adapter is no longer part of the launch path.

Implemented product boundaries:

- one background FIFO controller per browser session with a process-level
  session mutation lock;
- normalized agent, tool, workflow, artifact and session events;
- reconstruction from manifest, agent state and persisted conversation;
- bounded assembly, part and active-revision sequence image indexing;
- chat, explicit sequence approve/revise actions and audited JSON merge-patch
  edits with preview and downstream invalidation warning;
- structured artifact inspection, activity feedback, recoverable errors, HTML
  report downloads and a session ZIP export;
- a responsive dark technical three-pane workspace.

The implementation guide for coding agents is
`src/assembly_automation/app/streamlit/ui.md`. PDF remains deferred.

## UI review and second-iteration design (2026-09-24)

This section records product feedback after the first live UI run. It is a
design brief only; implementation should begin after the interaction model is
reviewed together.

### Visible startup and workflow progress

After uploading a STEP file and pressing **Start assessment**, session setup,
model initialization and STEP preprocessing can take long enough that the UI
appears inactive. The next iteration should restore the useful progress view
from the old app, backed by the new event contract rather than console output
or guessed percentages.

The progress component should show:

- immediate upload/session acknowledgement before LLM or OCC initialization;
- current phase, current operation and a short plain-language status;
- completed, active, queued, skipped and failed states;
- determinate item progress for known fan-outs such as parts and sequence
  steps, and an indeterminate activity state for operations with no meaningful
  total;
- elapsed time without fabricated time-remaining estimates;
- a compact completed-state summary that does not permanently consume the
  workspace;
- recoverable failure information and the valid next action.

Proposed product phases are **Session setup**, **STEP preprocessing**,
**Assembly review**, **Part analysis**, **Sequence generation**, **Sequence
review**, **Sequence rendering**, **Interaction analysis**, **FfA assessment**,
**Scoring**, and **Report generation**. Phase progress must be derived from the
manifest plus normalized workflow events. Node-level events remain available
in a technical run log.

### Structured output controls the visual workspace

The structured-output pane is the primary selection surface. Its first toggle
selects **Assembly analysis**, **Monopart analysis**, **Assembly sequence**,
**Interaction analysis**, or **FfA analysis** as soon as that artifact exists.
A contextual second selector chooses the unique part for monopart analysis and
the assembly step for interaction or FfA analysis. Assembly analysis and the
complete sequence need no second selector.

One `SelectionContext` with `scope`, `entity_id`, `revision_id`, and `step_id`
drives both panes. The visual workspace only selects image views inside that
context: assembly images for assembly analysis, one part's images for monopart
analysis, the ordered sequence evidence for the sequence, and the matching
step collage/renderings for interaction or FfA. It must not maintain a second
artifact or entity selector. Unsaved field changes still guard a context change.

### Human-readable structured results

Raw JSON should no longer be the default presentation. Each artifact should
have a schema-aware renderer composed from field labels, sections, cards,
tables, badges and appropriate controls. Raw JSON remains available through a
toggle for technical inspection. The renderer must preserve existing relevant
field names in storage even when the UI displays friendlier labels.

The first renderers should cover:

- assembly overview as identity, function, description, parts and assumptions;
- each monopart as identification, function, geometry/manufacturing clues and
  automation-relevant observations;
- sequence as ordered editable step cards;
- interaction and FfA as one selected step with classifications, evidence and
  drawbacks;
- report as key findings, recommendations and traceable evidence.

### Field-level editing and unsaved changes

Users should be able to edit relevant leaf values directly in the presented
structured view, for example the text at
`part_analysis.part_identification`. The UI should keep an in-memory draft for
the selected entity and generate a minimal JSON Merge Patch from changed
fields. It must not write the source artifact on every keystroke.

Before navigating from an entity with a dirty draft, the UI should interrupt
the navigation with a small **Save changes / Discard changes / Stay here**
decision. Since Streamlit reruns after widget changes, navigation must be
implemented as a requested selection followed by a guarded commit; changing a
select box must not immediately replace the active editor state. Saving uses
the existing audited `edit_intermediate_artifact` boundary, validates the full
artifact, records the reason and user message, archives the previous version,
and propagates stale state. A successful save then completes the requested
navigation. Validation failure keeps the draft and displays field-level errors.

Part editing needs a stable part-addressed patch operation rather than asking
the browser to submit the complete BOM. The backend should accept an artifact,
an entity selector such as `part_id`, a field path, the expected source
revision/hash, and the new value. It should resolve that selector server-side,
build the merge patch, detect concurrent modification, validate and save
atomically. The current generic JSON patch editor can remain behind an
**Advanced / Raw JSON** toggle.

### Agent context for BOM and monopart results — candidate change

The user-facing agent should not automatically ingest the full enriched BOM on
every turn. The current direction of focused `read_artifact` calls is better
for token usage. A possible improvement is a compact, deterministic **part
index** containing every part ID, name, quantity and the intrinsic summary from
monopart analysis. The agent could receive this index at the BOM review and
sequence checkpoints, then request one complete part record only when the user
or current decision concerns that part.

This remains a candidate change until token size and information loss are
measured. The compact index must be derived data with provenance, never a new
source of truth. It should preserve all part IDs so the agent can reliably map
phrases such as “the retaining ring” back to the canonical BOM record.

### Sequence review through dialogue

Remove the separate **Sequence decision** form from the normal product flow.
The user-facing agent should infer the next action from the user's ordinary
message:

- explicit, unqualified approval calls `approve_sequence` with the exact user
  message;
- requested changes call `revise_sequence`, passing the exact message and an
  agent-written concise feedback summary;
- ambiguous reactions lead to one short clarification question and no workflow
  mutation.

The agent already owns the approval/revision tools and should remain the only
decision-maker at this checkpoint. The UI may show non-mutating suggestion
chips that insert text into the composer, but it should not expose a second
feedback form or independently summarize feedback.

### Separate product artifacts from execution records

Generated outputs currently mix user-facing domain content with execution
metadata such as node inputs. The next revision should keep relevant field
names and domain values stable while separating the envelopes:

```text
<artifact>.json          # canonical product/domain data consumed by UI and downstream nodes
runlog/<node>/<run>.json # prompt/input selection, model profile, token usage, timing,
                         # warnings, retries, hashes and provenance
```

Product JSON omits duplicated status, source paths, prompt payloads and other
execution-only fields. Every LLM invocation writes a timestamped record below
`runlog/<node>/`, while node responses expose its path for workflow logging.
All active downstream readers use the new shapes directly. Old wrapped
structured outputs are intentionally unsupported. New product schemas use one
shallow, predictable domain root rather than multiple generic `result`,
`analysis`, `inputs` and node-name wrappers.

### Research and decisions required before implementation

Before coding, compare native Streamlit forms/data editors, a schema-driven
custom renderer, and maintained JSON-editor components for accessibility,
nested-object editing, dirty-state handling and compatibility with the current
Streamlit version. Prefer native widgets plus schema metadata unless an
external component materially improves nested editing without becoming the
owner of validation or persistence.

Open design decisions:

1. whether navigation with unsaved changes uses an inline confirmation card,
   a modal dialog, or automatic draft persistence plus an explicit save;
2. which fields in each artifact are product-facing, editable, read-only or
   technical;
3. whether the compact all-part index is injected automatically only at BOM
   review/sequence generation or also made available as a focused agent tool;
4. whether execution envelopes are removed in one migration or hidden first
   through projection/adaptor layers and physically separated afterward.

### Research conclusion and recommended implementation

Research was performed against Streamlit 1.64 documentation and the current
application code. Native Streamlit is sufficient for the product editor; a
generic third-party JSON editor should not become the main interface.

Relevant platform behavior:

- [`st.dialog`](https://docs.streamlit.io/develop/api-reference/execution-flow/st.dialog)
  provides a real modal and reruns independently like a fragment. It can host
  the unsaved-change decision.
- [`st.fragment`](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
  can isolate editor reruns and poll live workflow progress without rerunning
  the whole workspace.
- [Session State](https://docs.streamlit.io/develop/concepts/architecture/session-state)
  and widget callbacks provide the requested-selection/active-selection guard.
- [Forms](https://docs.streamlit.io/develop/concepts/architecture/forms) batch
  values until submit. This is unsuitable for the main field editor because a
  navigation widget outside the form can rerun the app before unsent form
  values reach Python. Forms remain useful for small self-contained actions.
- [`st.data_editor`](https://docs.streamlit.io/develop/api-reference/data/st.data_editor)
  is appropriate for flat repeated records such as sequence steps, but nested
  `dict` values are not editable and JSON columns are display-only. It cannot
  serve as a general nested artifact editor.
- [`st.status`](https://docs.streamlit.io/develop/api-reference/status/st.status)
  and [`st.progress`](https://docs.streamlit.io/develop/api-reference/status/st.progress)
  cover the progress surface when supplied with real workflow events.

A third-party editable JSON tree can remain an optional technical control. It
would add a component dependency, provide a weaker domain experience, and
still require all server-side validation, locking, auditing and stale-state
logic. The product view should therefore use a schema-driven native renderer:

```text
ArtifactViewRegistry
  assembly_overview -> AssemblyOverviewPresenter
  bom/part          -> PartPresenter
  sequence/step     -> SequenceStepPresenter
  interaction/step  -> InteractionPresenter
  ffa/step          -> FfaPresenter
  report            -> ReportPresenter
```

Each presenter declares sections, friendly labels, field paths, widget type,
editable/read-only state and optional formatting. Pydantic descriptions can
seed labels/help text, while an explicit UI schema controls ordering and hides
technical fields. Text fields use `st.text_area`; enums use `st.selectbox`;
booleans and numbers use typed widgets; repeated flat records may use
`st.data_editor`. Raw JSON uses `st.json` behind a toggle.

#### Guarded selection state

Use two separate values:

```text
active_selection     # entity currently rendered and owning the draft
requested_selection  # entity clicked in visual navigation
```

Editor widgets live in a keyed fragment and update a `DraftState` in Session
State on change. `DraftState` stores the source artifact hash, original leaf
values, edited leaf values and dirty paths. When visual navigation requests a
new entity:

1. if the current draft is clean, promote the requested selection;
2. if it is dirty, keep the current editor mounted and open a non-dismissible
   `st.dialog`;
3. **Save changes** calls the audited backend edit and promotes the selection
   only after success;
4. **Discard changes** removes the draft and promotes the selection;
5. **Stay here** resets the navigation control to the active selection.

This is implementable in Streamlit without JavaScript. It also avoids relying
on a browser-style `beforeunload` event, which would not protect server-side
state reliably.

#### Backend edit contract

Add a narrow service below both the UI and agent tool layer:

```text
preview_field_edits(
  artifact_id, entity_selector, changes, expected_sha256
) -> validated diff + downstream impact

apply_field_edits(
  artifact_id, entity_selector, changes, expected_sha256,
  reason, raw_user_message
) -> new hash + audit record + stale state
```

`entity_selector` is stable and semantic (`part_id`, `step_id`, revision), not
a browser-provided list index. The service resolves paths server-side,
rejects a stale source hash, applies changes to a copy, validates the complete
domain model, computes a minimal merge patch, archives the previous artifact,
writes atomically and returns normalized events. The user-facing agent and UI
should call the same service so their edit behavior cannot diverge.

#### Agent part context

Current behavior: `analyse_monoparts` returns status and artifact paths. The
agent prompt then instructs the model to call `read_artifact`, which supports a
focused dotted path but also permits loading the whole enriched BOM. The full
BOM is therefore not injected into every chat turn, but focused access is a
model choice rather than an enforced context budget.

Recommended replacement is a deterministic projection tool:

```text
list_parts() -> part_id, name, quantity
summarize_parts(part_ids | page) -> part_id, name, quantity, intrinsic_summary
read_part(part_id) -> complete editable part domain record
```

At BOM review, automatically return all intrinsic summaries only when the
serialized projection fits a configurable context budget. Above that budget,
return the complete compact index and paginated summaries. This retains every
part identifier, prevents accidental full-BOM reads, and lets the agent fetch
detail only for the selected visual part or current question. Record projection
size and estimated token count in the run log so this candidate change can be
measured rather than assumed.

#### Honest progress model

Do not assign timing-based weights without measurements. The main progress bar
reports completed product phases out of the applicable phase plan, while a
secondary bar reports real item counts for the current phase. Long operations
without a known total use `st.status(state="running")` and an indeterminate
activity treatment.

The controller must emit activity before model construction, which requires
splitting session startup into observable operations:

```text
upload_received -> files_saved -> configuration_loaded -> agent_ready
-> preprocessing_started -> importing_step -> validating_geometry
-> extracting_geometry -> rendering_views -> calculating_relations
-> preprocessing_complete
```

Later phases reuse node `stage_started`, `stage_progress`, `artifact_updated`,
`stage_completed` and `stage_failed` events. A `ProgressPlan` maps internal
stage IDs to the stable product phases above and derives state from the
manifest on resume. The UI should never advance a bar merely because time has
passed.

#### Proposed cleaned product shapes

The physical files and all active consumers use strict flat shapes. Relevant
leaf names remain unchanged while generic node wrappers are removed:

```text
assembly_overview.json
  assembly_description
  partslist
  assembly_name_guess
  primary_function

bom.json / parts[] / part_analysis
  part_identification
  part_name_guess
  part_color
  material_and_mechanical_behavior
  bulk_behavior
  magazine_behavior
  nature_of_provision_guess
  geometric_characteristics
  gripping_analysis
  handling_implications
  intrinsic_summary

assembly_sequence.json
  assembly_name
  assembly_description
  sequence_rationale
  sequence_notation
  steps[]
```

This removes the current `analysis` and nested `monopart_analysis` envelopes
without renaming their useful leaf fields. `inputs`, `images_used`, execution
settings, prompt hashes, token usage, elapsed time and tool-call counts move to
the linked run record. Readers and writers accept only this target shape; old
wrapped sessions may fail and can be discarded.

### Recommended implementation order after design approval

1. Add startup events, `ProgressPlan` and the visible progress component.
2. Add `SelectionContext` and link assembly/part/step visuals to presenters.
3. Build read-only schema-aware presenters and keep raw JSON as a toggle.
4. Add `DraftState`, edit preview/apply service and unsaved-change dialog.
5. Remove the separate sequence-decision UI and rely on agent dialogue.
6. Add bounded part-index tools and measure context usage.
7. Write strict flat product artifacts and separate timestamped run records.

### Confirmed decisions (2026-09-24)

- All descriptive domain fields are editable. Identifiers, geometry,
  calculated values, rendered colors and quantities remain read-only in the
  first field editor.
- The generic `analysis` and nested `monopart_analysis` envelopes are approved
  for removal. Relevant leaf-field names remain unchanged. Old wrapped session
  artifacts do not require backward compatibility; all active consumers and
  prompt configurations move directly to the new flat contract.
- Saving a user edit does not require agent interpretation or confirmation.
  The user may directly change any editable descriptive field. The backend
  still validates, audits, writes atomically and propagates stale state; the
  agent receives the persisted correction afterward as session context.

### Implementation status (2026-09-24)

The approved second UI iteration is implemented. The visual workspace now
selects the assembly, a unique part, or a rendered sequence step and drives the
structured-output pane. Descriptive fields use native Streamlit editors;
identifiers, geometry, quantities and calculated references remain read-only.
Dirty navigation opens a Save/Discard/Stay dialog, saves use an artifact hash
to reject stale browser drafts, and every successful edit is validated,
archived, written atomically and recorded as user feedback.

The separate sequence decision form is removed. Approval and revision now flow
through chat and the user-facing agent's existing tools. Agent BOM access is
bounded through `list_parts`, paginated `summarize_parts`, and `read_part`.
Progress is derived from manifest stages and real item counts across eleven
stable product phases, with startup events emitted before model initialization.

Assembly analysis, monopart analysis and sequence generation now write flat
product JSON. Prompt configuration and every downstream consumer use those
flat shapes directly. Execution inputs, selected images, prompts, model
settings, token use, timings and tool calls are stored in timestamped runlog
records. There is deliberately no reader for the former `analysis`,
`monopart_analysis`, or `sequence` envelopes.

## Post-FFA automation-concept planning (proposed 2026-09-28)

### Product intent and dialogue

The FfA report is not the terminal product result. It is the evidence base for
two optional, non-exclusive continuations:

```text
active FfA report
  -> discuss or formalize Design for Assembly (DfA) measures
  -> user and agent define an overall automation idea
  -> plan every assembly step in parallel
  -> consolidate the step plans into one automation concept
  -> user reviews and revises the overall concept
  -> plan station allocation from production and ergonomic requirements
  -> independently plan/render layout and estimate investment cost
```

After presenting the report, the user-facing agent remains available. It should
ask which direction is useful, but it must not force the user through a fixed
wizard. The user may discuss DfA first, start concept planning immediately, or
return from concept planning to a DfA measure when a concept exposes a product
design limitation.

The first automation-planning interaction is a tool-scoped instruction such as:

```text
develop_automation_idea(
  "Plan a concept in which steps 1-2 are automated and steps 3-4 remain manual."
)
```

This instruction is planning context, not a correction to the assembly, BOM,
sequence, or FfA report. It must therefore not use the artifact correction tool and
must not mark the assessment pipeline stale. The exact user message and a
normalized planning brief are persisted as an automation-idea revision. The
agent presents that idea and discusses it with the user. Only after acceptance
does `plan_automation_concept(idea_id)` start the parallel detailed step plans
and consolidate them into an overall automation concept.

The agent must keep two meanings separate:

- **FfA potential** is evidence about how suitable a process is for automation.
- **Selected execution mode** is the user's planning decision. A low-FfA step
  may still be requested as automated, but the concept must expose the required
  measures, residual risks, assumptions, and open validation tasks instead of
  silently changing the request.

### Findings from the legacy automation planner

The useful engineering decomposition in `agent/automation_planner.py`,
`agent/structured_output.py`, `configs/prompts.yaml`, and
`docs/Automatisierungsplaner.spec.md` is:

1. derive initial requirements and provisioning assumptions from the sequence,
   part analyses, interaction analysis, FfA assessment, and report;
2. generate process principles per assembly step and subprocess;
3. combine compatible principles into an overall technical concept with
   equipment functions, material flow, handovers, and assembly states;
4. evaluate the concept against FfA findings;
5. plan stations and detailed workplaces;
6. create a schematic layout and render it deterministically.

The current legacy launcher only executes requirements, per-step principles,
three overall variants, and LLM layout planning. Variant evaluation, station
planning, and workplace design have prompts and schemas but are not wired into
the executed workflow. The deterministic box renderer is separate.

The extraction should preserve the decomposition and discard these limitations:

- every step always produces manual, semi-automated, and fully automated
  principles, even when the user requested one mixed concept;
- overall concepts are restricted to three global strategies, so a request such
  as automated steps 1-2 and manual steps 3-4 cannot be represented directly;
- one undifferentiated feedback string is sent to every step;
- existing files are reused by filename rather than input hashes and dependency
  provenance, so changed inputs can silently reuse stale planning results;
- context may be truncated in the middle of serialized JSON;
- legacy session artifacts are discovered with filename globs instead of the
  active revision and manifest;
- equipment names act as join keys in layout data where stable equipment IDs
  are required;
- LLM-generated coordinates are schematic assumptions, not verified plant
  dimensions; and
- planner calls do not use the product node run-record contract for prompts,
  model settings, token use, timing, and source hashes.

### Agent-facing tool boundary

Expose meaningful decisions, not every internal node. The first product slice
should add these tools to `WorkflowAgentTools`:

| Tool | Purpose |
|---|---|
| `develop_automation_idea(instruction)` | Turn the user's high-level direction into a reviewable planning brief/overall idea grounded in the active sequence and FfA report. It does not yet perform detailed step planning. |
| `revise_automation_idea(idea_id, instruction)` | Apply user feedback to the high-level idea and create an immutable idea revision. |
| `plan_automation_concept(idea_id)` | After the idea is accepted, run detailed planning for every assembly step in parallel, consolidate the results, and validate the overall concept. |
| `revise_automation_concept(concept_id, instruction)` | Revise an existing concept. Reuse unaffected per-step principles and regenerate only the affected dependency closure. |
| `read_automation_concept(concept_id, section="summary")` | Return a bounded summary, one step realization, equipment requirements, risks, or open questions without loading the entire concept into agent context. |
| `evaluate_automation_concept(concept_id)` | Run or refresh the explicit technical evaluation when the user wants a comparison or recommendation. This may be included in `plan_automation_concept` once its cost is acceptable. |
| `plan_stations(concept_id, production_instruction="")` | Allocate the accepted concept's steps across one or more stations using volume, takt/cycle targets, shifts, availability, staffing, ergonomics, buffers, and process constraints. |
| `plan_automation_layout(station_plan_id)` | Plan schematic coordinates and invoke deterministic rendering for an accepted station plan. |
| `estimate_investment_cost(station_plan_id, cost_catalog_id)` | Map planned equipment to a versioned cost catalog and calculate investment totals. This does not depend on layout generation. |
| `develop_dfa_measures(instruction)` | Optional structured DfA branch grounded in report drawbacks and selected steps/parts. It creates proposals and scenarios; it does not pretend to modify CAD. |

The first implementation can combine concept evaluation into
`plan_automation_concept` and defer `develop_dfa_measures`, station, layout, and
cost tools. Do
not expose `generate_process_principles`, `synthesize_concept`, or rendering
helpers directly to the conversational model: there is no useful user decision
between those internal operations.

`develop_automation_idea` accepts the user's ordinary language verbatim.
`plan_automation_concept` accepts the selected `idea_id`; neither tool asks the
agent to paste large JSON artifacts into arguments. The tool implementation
supplies trusted context:

- active sequence revision and approval record;
- assembly overview and bounded part records for referenced steps;
- per-step interaction analysis and FfA assessment;
- active FfA scores and report;
- accepted planning/DfA context relevant to the selected steps; and
- an optional parent concept revision for a revision call.

The agent prompt should route post-report messages as follows:

- questions about the report: answer from the active report and focused reads;
- proposed product-design changes: discuss them, or call
  `develop_dfa_measures` when the user asks to formalize alternatives;
- a high-level automation direction: call `develop_automation_idea` with the
  exact request, present the resulting idea, and use `revise_automation_idea`
  while the user changes its scope;
- acceptance of the presented idea: call `plan_automation_concept` with its
  stable idea ID;
- a correction to a presented concept: call `revise_automation_concept`;
- a request to compare concepts: read/evaluate the named concept revisions; and
- a request to divide work across stations: call `plan_stations` for an accepted
  concept revision and collect missing production requirements first;
- a request for physical layout: call `plan_automation_layout` for a named
  station-plan revision; and
- a request for investment cost: call `estimate_investment_cost` with a named
  station plan and cost catalog. Layout does not need to exist.

### Internal nodes and contracts

#### 1. `automation_idea` / `automation_planning_brief`

This node converts conversational planning intent into an explicit,
user-reviewable overall idea and control artifact. It is the critical addition
missing from the legacy planner and is a checkpoint before detailed step calls.

Input:

- exact tool instruction;
- active sequence step index and descriptions;
- report-level recommendation and per-step FfA levels; and
- optional prior brief when revising.

Output: `AutomationPlanningBrief` with at least:

```text
brief_id
idea_revision
source_sequence_revision
source_report_revision
objective
step_policies[]
  step_id
  target_mode: manual | assisted | automated | planner_choice
  subprocess_overrides
    separation | handling | positioning | joining | inspection | transfer
    -> manual | assisted | automated | not_required | planner_choice
  user_rationale
global_constraints[]
preferred_equipment_or_technology[]
prohibited_equipment_or_technology[]
planning_assumptions[]
open_questions[]
source_user_message
```

The artifact also includes a concise user-facing concept direction: intended
automation boundary, human role, technical theme, major material-flow idea,
expected benefits, conflicts with FfA evidence, and decisions still needed. It
must remain high level; detailed grippers, fixtures, operations, station counts,
and layouts belong to later nodes.

Natural expressions such as “highly automated” are normalized to explicit
subprocess targets. The node must preserve ambiguity in `open_questions`; it
must not silently interpret production volume, cycle time, budget, floor space,
operator availability, safety category, or preferred technology when none was
provided. Missing non-critical information may remain a labeled planning
assumption so concept generation can continue.

Deterministic validation must reject unknown or duplicate step IDs, references
outside the active sequence, invalid subprocess names, and contradictions such
as the same subprocess being both mandatory-manual and mandatory-automated.

#### 2. `process_principles`

Run once per affected assembly step, in parallel. Unlike the legacy schema, it
generates only the realization required by the planning brief, while retaining
the useful subprocess decomposition:

```text
separation -> handling -> positioning -> joining -> optional inspection -> transfer
```

Each subprocess result contains the selected execution mode, concrete technical
solution, responsible actor/equipment, evidence references, necessary measures,
residual risks, assumptions, and open questions. Evidence references identify
the source step/part/report fields rather than copying unsupported claims.

Persist one artifact per step. A revision affecting steps 1-2 must not rerun
steps 3-4. Cache reuse requires matching hashes for the planning policy, prompt,
schema, and all selected source artifacts.

#### 3. `automation_concept_synthesis`

Combine the step principles into one coherent concept. Its responsibilities are
binding sequence coverage, assembly state continuity, human-machine allocation,
required equipment functions, material supply, transfer requirements,
inspection, and safety/open engineering tasks.

The structured output must use stable IDs (`concept_id`, `operation_id`,
`equipment_requirement_id`) and reference sequence `step_id` values. Display
names are not join keys. Every sequence step appears exactly once in the
concept. Each step realization contains ordered operations that explicitly
state actor/equipment function, action, object, and resulting state. Equipment
requirements remain structured data, not prose embedded in one field.

This node must not decide the number of stations or assign steps to stations.
It defines what technically happens across the full process and which resources
and interfaces are required. Station formation is a later planning decision
based on production targets and ergonomics. Unsupported selections are labeled
`planning_assumption`; they are not presented as CAD-derived facts.

#### Deferred: `automation_concept_validation`

Do not build a dedicated validation node in the first version. Pydantic still
checks the structured output shape. A later hardening phase may add cross-
artifact checks for:

- exact sequence-step coverage and order;
- policy compliance for every step and subprocess;
- operation/equipment-requirement integrity and unique stable IDs;
- no transfer of an unsecured intermediate assembly without a stated restraint;
- every identified high-severity FfA risk is addressed, accepted, or explicitly
  unresolved;
- manual and automated responsibilities are complete and non-contradictory; and
- assumptions and open questions remain visible.

The separate optional LLM evaluation produces strengths, weaknesses,
recommended measures, feasibility gates, and a recommendation for continued
planning. Keep economic claims out unless the user supplied volume, cycle-time,
labor, investment, and cost assumptions.

#### 5. `station_planning`

Station planning starts only after the user accepts an automation concept. It
decides where each already-defined operation happens; it must not redesign the
underlying joining or handling principle without producing an explicit concept
revision.

Required production inputs belong in a versioned `ProductionPlanningBasis`:

```text
annual_volume
working_days_per_year
shifts_per_day
net_shift_duration
target_availability_or_oee
target_takt_time
known_or_estimated_operation_cycle_times
parallelization_limits
operator_count_or_staffing_constraints
ergonomic_constraints
buffer_policy
floor_space_or_line_form_constraints
changeover_and_variant_requirements
```

The tool should derive takt only when the required calendar, volume, and
availability inputs exist. Unknown operation times stay estimated with their
basis and confidence; they must not be presented as measured times. Missing
values that materially change station count become focused agent questions.

Output: a revisioned `StationPlan` containing station IDs, ordered step and
operation assignments, manual/automatic work content, station cycle-time load,
shared equipment, fixtures, operator tasks, ergonomic measures, buffers,
handover state, capacity assumptions, bottlenecks, and balancing rationale.
Every concept operation is assigned exactly once unless explicitly modeled as a
shared or parallel operation. Deterministic validation checks coverage,
precedence, takt overload, resource conflicts, and station interface integrity.

This creates the user-visible answer to “what happens at which station.” The
agent presents the station plan and can revise it from feedback without
regenerating accepted per-step technical principles unless the requested change
actually changes the automation concept.

#### 6. `automation_layout_planning` and `automation_layout_rendering`

Layout is downstream of an accepted station plan, not part of every exploratory
concept call. The planning node assigns schematic station/equipment coordinates
without changing concept or station-plan identities/content. The deterministic
renderer may reuse the legacy box-layout logic after extraction from `agent/`.

Coordinates, default footprints, and safety envelopes must record their basis as
`user_input`, `catalog_data`, or `visual_default`. Rendered layouts must state
that unverified schematic dimensions are not an installation-ready factory
layout. Use stable equipment IDs instead of normalized names for joins.

#### 7. `investment_cost_estimation`

Cost estimation is independent of layout planning and rendering. It consumes
the accepted station plan because station formation determines equipment
quantities, duplicated fixtures, transfer systems, safety zones, controls, and
installation scope.

The authoritative input is a versioned user- or organization-provided cost
catalog, for example CSV/XLSX/JSON, with stable catalog item IDs, description,
category, unit, unit cost, currency, validity date, optional vendor, and optional
cost range. The estimator must never invent a price.

The workflow may use an LLM or deterministic rules to propose mappings from
`equipment_id` to catalog items, but every mapping records confidence and
requires review when ambiguous. Arithmetic is deterministic. The output
contains line items, quantity, unit cost, subtotal, mapping basis, unresolved
equipment, optional engineering/integration/commissioning factors, contingency,
and totals by station/category and for the complete concept. Assumptions and
excluded operating costs are explicit. Cost artifacts record catalog version,
currency, price date, station-plan revision, and calculation-rule version.

#### 8. `dfa_measures` (optional branch)

This node turns selected report drawbacks into structured design proposals:

```text
measure_id
targets: part IDs, step IDs, or assembly
problem_and_evidence
proposed_change
expected_ffa_effect
affected_subprocesses
tradeoffs
validation_required
status: proposed | accepted_for_scenario | rejected
```

The result is a planning scenario, not a mutation of CAD-derived geometry or of
the approved baseline FfA report. Accepted measures may be injected into a new
planning brief as assumptions. A future re-analysis against modified CAD is a
separate workflow and must not be implied by textual acceptance.

### Concrete node build catalog: inputs, outputs, and prompts

All LLM nodes follow the existing product-node pattern demonstrated by
`sequence_generation`: one local `node.py`, `inputs.py`, `structured_output.py`,
and `prompts.yaml`, executed through `run_llm_node`. Workflow definitions own
fan-out, retries, atomic partial aggregates, revision directories, and manifest
publication. Each node writes product JSON separately from its standard
`runlog/<node>/...run.json` execution record.

The legacy German class and field names may be read during extraction, but new
product contracts use consistent English names. Reuse below means preserving
the useful semantic fields or prompt rules, not importing `agent/` at runtime.

Planned product packages:

| Node ID | Type | Package below `workflows/nodes/` |
|---|---|---|
| `automation_idea` | LLM | `automation_idea/` (replace the empty `automation_requirements/` placeholder) |
| `process_principles` | LLM, per-step fan-out | `process_principles/` |
| `automation_concept_synthesis` | LLM | `automation_concept/` (replace the empty `automation_variants/` placeholder) |
| `automation_concept_evaluation` | LLM | `automation_concept_evaluation/` |
| `production_planning_basis` | LLM extraction plus deterministic calculations | `production_planning_basis/` |
| `station_planning` | LLM plus deterministic balancing validation | `station_planning/` |
| `automation_layout_planning` | LLM | `layout_planning/` |
| `automation_layout_rendering` | deterministic | `layout_rendering/` |
| `cost_catalog_ingestion` | deterministic | `cost_estimation/catalog.py` |
| `investment_cost_estimation` | deterministic with optional bounded LLM mapping | `cost_estimation/` |
| `dfa_measures` | optional LLM branch | `dfa_measures/` |

#### Node A: `automation_idea`

Purpose: create the high-level idea that the user and agent discuss before
detailed step planning.

Inputs:

| Input | Required | Selection |
|---|---:|---|
| `planning_instruction` | yes | Exact current user message supplied as tool-scoped text. |
| `assembly_sequence` | yes | `assembly_name`, `assembly_description`, and compact `steps[]` identity/description/process fields from the active approved revision. |
| `ffa_report` | yes | Executive summary, findings, recommendations, and their source references. |
| `ffa_scores` | yes | Overall and per-step/subprocess scores from the active revision. |
| `prior_idea` | revision only | Previous complete planning brief. |
| `dfa_scenario` | no | Only accepted measures selected by stable scenario ID. |
| `planning_context` | no | Relevant accepted automation-planning facts; not the entire conversation. |

Output schema: new `AutomationPlanningBrief`, as defined above, plus
`concept_direction`, `human_role`, `material_flow_intent`, `expected_benefits`,
`ffa_conflicts`, and `decisions_required`. Step IDs and source revision IDs are
validated against inputs. The node produces one immutable idea revision.

Prompt resources:

- new `automation_idea_system_v1`, adapted from legacy
  `automation_initial_requirements_system_v1` and the evidence/assumption rules
  in `automation_variant_generator_system_v1`;
- new `automation_idea_human_v1`, containing only the task statement; configured
  inputs are appended by `build_prompt`;
- instruct the model to translate user intent into policy, not to generate
  grippers, station counts, coordinates, cycle times, or prices; distinguish FfA
  potential from selected automation mode; preserve uncertainty and exact user
  constraints; and cover every active sequence step using an explicit default
  such as `planner_choice`.

Reuse decision: replace the top-level legacy `InitialeAnforderungsklaerung`
schema because it lacks explicit step/subprocess policy and provenance. Reuse
the ideas behind `InitialeAnforderungMontageschritt`—step, parts, provisioning,
qualitative FfA, risks—and derive them from current flat artifacts.

#### Node B: `process_principles`

Purpose: fine-plan exactly one assembly step. The workflow invokes this node for
all steps in parallel, comparable to current monopart fan-out.

Inputs per invocation:

| Input | Required | Selection |
|---|---:|---|
| `assembly_step` | yes | Exactly one active sequence step selected by `step_id`. |
| `step_policy` | yes | Exactly one policy from the accepted automation idea. |
| `base_part` | when present | Bounded BOM record for the base instance's unique part. |
| `joining_parts` | yes | Bounded BOM records for all joining instances. |
| `interaction_analysis` | yes | Matching per-step interaction artifact. |
| `ffa_assessment` | yes | Matching per-step four-subprocess assessment. |
| `ffa_scores` | yes | Matching per-step/subprocess scores. |
| `report_findings` | no | Findings/recommendations whose `step_ids` or `part_ids` match this step. |
| `dfa_measures` | no | Accepted measures targeting this step or its parts. |
| `step_planning_feedback` | revision only | Feedback explicitly scoped to this step. |

Output schema: new `StepAutomationPlan`:

```text
step_id
policy_reference
process_objective
subprocesses
  separation
  handling
  positioning
  joining
  inspection
  transfer
each subprocess:
  execution_mode
  technical_solution[]
  actor_or_equipment_functions[]
  inputs_and_outputs[]
  evidence_refs[]
  assumptions[]
  required_measures[]
  residual_risks[]
equipment_requirements[]
interface_requirements[]
open_questions[]
```

Prompt resources:

- migrate legacy `automation_process_principles_system_v1` to local
  `process_principles/prompts.yaml` as `system_v1`;
- keep its six-subprocess definitions and engineering-specificity rules;
- remove the instruction to generate three strategies and instead require exact
  compliance with the supplied step/subprocess policy;
- add explicit evidence references, stable equipment-requirement IDs, no
  station allocation, no unsupported cycle times, and no alternative solutions
  hidden inside one selected concept;
- local `human_v1` says to fine-plan the supplied single step and resolve any
  conflict between requested mode and FfA as measures/risks, not by changing the
  requested mode.

Reuse decision: reuse the semantics of `AutomationPlannerSubprozess`,
`AutomationPlannerSubprozesse`, `AutomationPlannerMeasure`, and
`AutomationPlannerEquipment`. Replace `ProzessprinzipErgebnis` because its
`prozessprinzipien` field mandates exactly three whole-step strategies and lacks
evidence/provenance fields.

Deterministic validation checks step identity, required subprocess coverage,
policy compliance, evidence-reference syntax, unique requirement IDs, and
nonempty manual/automatic responsibility.

#### Node C: `automation_concept_synthesis`

Purpose: consolidate all accepted `StepAutomationPlan` artifacts into one
station-independent end-to-end automation concept.

Inputs:

| Input | Required | Selection |
|---|---:|---|
| `automation_idea` | yes | Accepted idea revision in full. |
| `assembly_sequence` | yes | Active approved sequence in full. |
| `step_automation_plans` | yes | One validated plan for every sequence step, ordered deterministically. |
| `assembly_overview` | yes | Name, primary function, and assembly description. |
| `global_report_findings` | no | Assembly-level findings and recommendations only. |
| `concept_feedback` | revision only | Feedback affecting cross-step flow or named step plans. |

Output schema: new `AutomationConcept`:

```text
concept_id and revision
source_idea_id and source revisions
title and concept_summary[]
automation_boundary
human_machine_collaboration[]
step_realizations[]
  step_id
  ordered_operation_ids[]
operations[]
  operation_id, step_id, subprocess
  actor_or_equipment_function, action, object, resulting_state
equipment_requirements[]
material_supply_and_flow[]
assembly_state_transitions[]
transfer_and_buffer_requirements[]
inspection_and_process_control[]
safety_and_ergonomic_requirements[]
cross_step_measures[]
residual_risks[]
planning_assumptions[]
open_questions[]
```

Prompt resources:

- migrate the continuity, assembly-state, material-flow, interface, specificity,
  and assumption rules from legacy `automation_variant_generator_system_v1`;
- remove global `manuell/halbautomatisiert/vollautomatisiert` strategy selection,
  station grouping, coordinates, and station-equipment output;
- require one coherent solution, exact sequence/step coverage, stable reference
  preservation, and no rewriting of accepted step-level technical principles;
- new local `human_v1`: consolidate the supplied accepted idea and all step plans
  into one station-independent concept.

Reuse decision: reuse the intent of `MontageablaufEintrag`,
`EintragEquipment`, `AutomationPlannerMeasure`, and the legacy generator prompt.
Replace `AutomatisierungsGesamtkonzept`, because its mandatory `strategie` and
`stationen` fields combine decisions that now belong to different phases.

#### Deferred node: `automation_concept_validation` (deterministic)

This is not part of the first implementation. The initial version relies on
Pydantic structured-output validation, stable IDs, and direct user review after
concept synthesis. A later hardening phase can add this node to reject or
annotate cross-artifact structural contradictions before a concept is presented.
It makes no LLM call and has no prompts.

Inputs: accepted automation idea, active sequence, all step plans, synthesized
concept, and referenced FfA finding IDs.

Output: `AutomationConceptValidation` with `valid`, errors, warnings, exact
step/operation/policy coverage, unresolved FfA risks, broken references, and
source hashes. Hard errors prevent manifest publication as a reviewable concept;
warnings remain visible in the concept review.

Implementation reuse: follow the explicit validators in
`sequence_generation/validation.py` and legacy `_validate_layout_plan`; do not
delegate identity/coverage checks to prompts.

#### Node E: `automation_concept_evaluation`

Purpose: produce a technical critique after synthesis or on demand when the user
wants comparison/recommendation.

Inputs: synthesized concept, idea, relevant report findings/recommendations, and
FfA scores. A deterministic validation report may be added as an optional input
when the deferred validation node exists. Production basis is optional and must
be clearly distinguished when absent.

Output schema: evolve legacy `Variantenbewertung` into
`AutomationConceptEvaluation` with strengths, weaknesses, addressed and
unaddressed finding IDs, feasibility gates, recommended measures, open
validation tasks, and `recommendation_for_next_phase`. Do not include monetary
judgments without cost results.

Prompts: migrate `automation_variant_evaluator_system_v1` and
`automation_variant_evaluator_human_v1`; add source-reference requirements,
explicit treatment of user-selected low-FfA automation, and prohibition on
inventing production economics.

#### Node F: `production_planning_basis`

Purpose: convert user/organization production requirements into the validated
inputs needed for station balancing. It may run repeatedly during agent
discussion until blocking values are known or explicitly treated as scenarios.

Inputs: exact production-planning instruction, optional uploaded production
documents, accepted concept, and optional prior basis revision.

Output: `ProductionPlanningBasis` containing the fields listed in the station
planning section, units and provenance for every value, calculated target takt,
scenario assumptions, blocking missing inputs, and nonblocking open questions.

Prompts: new `production_planning_basis_system_v1` and `human_v1`. Require the
model to extract only supplied values, normalize units, never invent cycle time
or OEE, and identify which missing values block station-count decisions.
Takt/calendar arithmetic and unit conversion are deterministic post-processing,
not LLM output.

Reuse decision: no adequate legacy schema exists. The legacy station prompt
mentions stations and material flow but does not model production capacity or
ergonomics quantitatively.

#### Node G: `station_planning`

Purpose: assign the accepted concept's operations to one or more stations and
define what happens at each station.

Inputs:

| Input | Required | Selection |
|---|---:|---|
| `automation_concept` | yes | Accepted concept revision. |
| `production_planning_basis` | yes | Validated basis/scenario revision. |
| `operation_time_basis` | yes | Measured, catalog, user-estimated, or explicitly estimated durations with provenance/confidence. |
| `part_and_assembly_constraints` | yes | Focused handling, interaction, stability, and transfer constraints referenced by the concept. |
| `station_feedback` | revision only | User changes scoped to station formation or allocation. |

Output schema: new `StationPlan`, reusing and extending legacy station concepts:

```text
station_plan_id and revision
concept_id and production_basis_id
line_form
target_takt_seconds
stations[]
  station_id, name, purpose
  operation_ids[] and step_ids[]
  ordered_station_actions[]
  manual_work_content_seconds
  automatic_work_content_seconds
  station_cycle_time_seconds
  operator_tasks[]
  equipment_ids[] and shared_resource_ids[]
  ergonomic_measures[]
  input_state, output_state, handover
  buffers_and_capacity
  bottlenecks_and_open_tasks[]
cross_station_resources[]
line_balancing_summary
capacity_result
assumptions[] and open_questions[]
```

Prompts: substantially extend legacy `automation_station_planner_system_v1` and
`human_v1`. Preserve its station/line, orientation, carrier, transport, buffer,
material-flow, and handover scope. Add exact operation coverage, precedence,
takt/cycle balancing, ergonomic allocation, shared-resource conflicts, and
provenance rules. The prompt may propose grouping; deterministic validation
calculates loads and detects overloads after generation.

Reuse decision: reuse `StationsMontageschritt`, `Station`, and
`Stationskonzept` concepts, but replace their schemas because they lack stable
operation/equipment IDs, production basis, cycle load, ergonomics, buffers, and
capacity results. Legacy workplace-detail fields can be incorporated here or
added later as a separate station-detail node only if users need that decision
point.

#### Node H: `automation_layout_planning`

Purpose: assign schematic station-local and overall coordinates without
changing the accepted station plan.

Inputs: accepted `StationPlan`, structured equipment/resource records,
footprints when known, layout constraints supplied by the user, and optional
prior layout feedback.

Output schema: evolve `LayoutPlanerErgebnis` into `AutomationLayoutPlan` with
`station_id`/`equipment_id` references, X/Y, width/depth, rotation, safety
envelope, unit, and value basis (`user_input`, `catalog_data`, or
`visual_default`). It also contains flow paths, access zones, warnings, and an
explicit schematic/not-engineering-validated status.

Prompts: migrate legacy `automation_layout_planer_system_v1` and `human_v1`.
Keep coordinate-system, access, material-flow, spacing, complete-coverage, and
non-overwrite rules. Replace name-based joins with IDs and remove the universal
30 x 18 cm assumption when catalog or supplied footprints exist.

Deterministic validation is adapted from legacy `_validate_layout_plan`: exact
station/equipment coverage, unique IDs and coordinates, finite dimensions,
reference integrity, overlap warnings, and fixed coordinate units.

#### Node I: `automation_layout_rendering` (deterministic)

Purpose: render the validated layout into station and overall SVG/PNG images.

Inputs: `AutomationLayoutPlan`, accepted station plan, renderer settings, and
optional icon/category assignments.

Outputs: station SVG/PNG files, overall SVG/PNG, and
`rendering_manifest.json` with source hashes, bounds, defaults, warnings, and
renderer version. There is no prompt and no LLM requirement in the MVP.

Reuse decision: extract the algorithms and configurable visual rules from
`agent/layout_generator.py`. Replace joins on `equipment_name` with stable
`equipment_id`. Preserve honest overlap warnings and never auto-move planned
coordinates during rendering.

#### Node J: `cost_catalog_ingestion` (deterministic)

Purpose: validate and normalize the external price list before any calculation.

Inputs: user-authorized CSV, XLSX, or JSON plus optional column mapping and
default currency/unit conventions.

Output: versioned `CostCatalog` with stable item IDs, descriptions, categories,
units, unit costs or ranges, currency, validity dates, vendor/source metadata,
and ingestion warnings. Invalid/missing prices are retained as unresolved rows,
not coerced to zero. No prompt is required; reuse the document-ingestion
infrastructure for authorized file handling but apply a strict cost schema.

#### Node K: `investment_cost_estimation`

Purpose: map station-plan equipment/resources to catalog items and calculate
investment cost independently of layout.

Inputs: accepted station plan, structured concept equipment requirements,
versioned cost catalog, deterministic calculation rules/factors, and optional
reviewed mapping overrides.

Output: `InvestmentCostEstimate` with stable estimate ID, station-plan and
catalog revisions, currency/date, line items, catalog mapping and confidence,
quantity, unit cost/range, subtotal, engineering/integration/commissioning
factors, contingency, totals by station/category, overall total/range,
unresolved equipment, exclusions, and assumptions.

Prompts: use no LLM when exact catalog IDs or deterministic mappings exist. For
unresolved descriptions, an optional `cost_catalog_mapping_system_v1` receives
only unmatched equipment and allowed catalog candidates and returns candidate
item IDs with confidence/reasoning. It cannot output or modify prices,
quantities, factors, or totals. Low-confidence/ambiguous mappings remain
unresolved for user review. All arithmetic is deterministic and tested.

Reuse decision: this is new functionality; no adequate legacy cost node exists.

#### Node L: `dfa_measures` (optional and independent)

Purpose, inputs, and output follow the DfA contract above. Inputs are active
report findings/recommendations, targeted FfA drawbacks, focused part records,
the exact user instruction, and an optional prior scenario. New prompts
`dfa_measures_system_v1`/`human_v1` require evidence references, expected but
unverified effects, trade-offs, and validation needs. This node never edits CAD
or rewrites baseline assessment artifacts.

### Node dependency graph

```text
automation_idea                         dfa_measures (optional)
       |                                      |
       +-------------------+------------------+
                           v
             process_principles [per step, parallel]
                           |
                           v
             automation_concept_synthesis
                           |
              user review / concept revision
                           |
          production_planning_basis <-> user dialogue
                           |
                     station_planning
                      /             \
                     v               v
       automation_layout_planning   investment_cost_estimation <--- cost_catalog_ingestion
                     |
       automation_layout_rendering
```

`automation_concept_evaluation` can run after concept synthesis and again after
a material concept revision. The deferred validation node can later be inserted
between synthesis and review without changing the surrounding artifacts. Layout
and cost are siblings: neither consumes the other. Cost depends on station
planning because station count and equipment duplication affect quantities.

### Testing the planning branch on existing App sessions

Existing reorganized App sessions are the preferred integration fixtures. The
planning branch reads the active artifact references from `manifest.json`; it
must not rediscover “latest” files with recursive globs. A session is eligible
when it has an approved active sequence revision and complete interaction, FfA,
score, report, assembly, and BOM artifacts.

The first developer runner accepts:

```text
--session-root data/sessions/<existing-session>
--instruction "Plan steps 1-2 automated and steps 3-4 manual"
--output-root <optional-sidecar-folder>
```

Default behavior writes only additive files below the session's
`automation_planning/` and `runlog/` directories. Assessment artifacts remain
read-only. A node writes to a temporary/revision directory and publishes it only
after successful schema validation, so a failed test cannot replace an active
planning revision. Until the UI and manifest reader understand planning keys,
the runner may keep planning state in
`automation_planning/planning_manifest.json` instead of extending the main
manifest.

`--output-root` provides isolation when testing against a valuable session: the
runner reads source artifacts from `--session-root` but writes every planning
artifact and run record to the sidecar folder. Each output records the source
session ID, active sequence revision, report revision/path, and source hashes.
This also supports a folder-based batch test without copying large rendering
assets.

Initial tests should use two layers:

1. fixture/unit tests with captured current-session JSON and fake structured
   model responses for schemas, configured input selection, fan-out, resume, and
   revision behavior;
2. one opt-in real-model smoke test against an existing completed App session,
   first with a sidecar output and then in-session once artifact publication is
   stable.

### Product artifacts and revision layout

Use English product contracts and the existing product runtime conventions.
Keep execution metadata in `runlog/`, not in domain artifacts:

```text
automation_planning/
  ideas/<idea_id>/planning_brief.json
  process_principles/<concept_id>/steps/step_NNN.json
  concepts/<concept_id>/concept.json
  evaluations/<concept_id>/evaluation.json
  dfa_scenarios/<scenario_id>/measures.json
  production_bases/<production_basis_id>.json
  station_plans/<station_plan_id>/station_plan.json
  layouts/<station_plan_id>/
    layout_plan.json
    rendered/
      station_<station_id>.svg
      station_<station_id>.png
      overall_layout.svg
      overall_layout.png
      rendering_manifest.json
  cost_catalogs/<cost_catalog_id>/catalog.json
  cost_estimates/<cost_estimate_id>/investment_cost.json
runlog/
  automation_planning_brief/
  process_principles/
  automation_concept_synthesis/
  automation_concept_evaluation/
  station_planning/
  automation_layout_planning/
  investment_cost_estimation/
```

The session manifest publishes `active_automation_idea`,
`active_automation_concept`,
`active_station_plan`, `active_cost_estimate`, available revisions, active DfA
scenario, and artifact paths. Each artifact records hashes or revision IDs of
its inputs. Do not overwrite planning artifacts in place: revisions are
immutable, and the manifest selects the active revision.

Dependency behavior:

- changing the sequence or its approval invalidates all dependent concepts;
- regenerating FfA invalidates concept evaluations and flags concepts for
  evidence review, but preserves them as historical revisions;
- changing a planning brief invalidates affected principles and downstream
  concept/evaluation/station/layout/cost artifacts only;
- changing concept operations or equipment requirements invalidates its
  evaluation and all dependent station plans;
- changing a station plan invalidates its layouts and cost estimates;
- changing layout does not invalidate cost, and changing a cost catalog does
  not invalidate concept, station, or layout artifacts; and
- DfA scenario changes invalidate only concepts that reference that scenario.

### Suggested first implementation slice

1. Extract and translate the legacy process-principle and concept schemas into
   `src/assembly_automation/workflows/nodes/`, using stable IDs and current flat
   source artifacts.
2. Implement the reviewable `automation_idea`/planning brief with deterministic
   step-policy validation and tests for mixed-mode requests.
3. Implement per-step `process_principles` fan-out with atomic partial output,
   resume behavior, source hashes, and run records.
4. Implement concept synthesis with its Pydantic output contract; defer the
   dedicated cross-artifact validation node.
5. Add `develop_automation_idea`, `revise_automation_idea`,
   `plan_automation_concept`, `revise_automation_concept`, and bounded
   `read_automation_concept` tools and extend the post-report agent prompt.
6. Add manifest/state support, UI presentation, and concept revision history.
7. Add the production-planning basis and station planner after the concept
   review/revision loop is stable.
8. Add layout planning/rendering and catalog-based investment costing as
   independent branches from an accepted station plan.
9. Add technical comparison and DfA scenarios as separate increments.

Acceptance tests for the first slice must prove that:

- “steps 1-2 automated, steps 3-4 manual” produces exactly those step policies;
- detailed per-step planning does not start before the idea checkpoint is
  accepted;
- unspecified steps are handled according to an explicit default policy rather
  than silently omitted;
- all sequence steps occur exactly once in the concept;
- concept synthesis does not prematurely assign stations;
- the chosen execution mode can differ from FfA potential while the conflict is
  visible as risk/measure/open work;
- revising one step reuses unaffected process-principle artifacts;
- a sequence revision prevents an old concept from being treated as current;
- a station plan assigns every concept operation exactly once and reports takt
  overloads from the supplied production basis;
- cost totals use only versioned catalog values and unresolved equipment remains
  visibly unpriced;
- tool context is bounded by selected step/part evidence, not a full session
  dump; and
- every LLM call writes the standard prompt/input/model/token/timing run record.
