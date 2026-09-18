# App V3 code reorganization plan

Date: 2026-09-18. Status: incremental rebuild started; existing implementation remains active.

## Rebuild approach and current progress

Build the target package alongside the existing implementation. Start with clean
interfaces, inspect each old responsibility in full, and extract only the domain
logic/resources it needs. Do not reproduce the old monolithic modules behind a
new directory layout. Adapters are temporary compatibility tools, not the final
architecture. Optimize redundant reads, payload construction, merging, and rerun
work after identifying their consumers and preserving behavior.

Created the installable package foundation, module/node directories, an explicit
recursive configuration loader, and a draft `configs/appsettingsv3.yaml` for the
first node. Existing launchers/configs remain active. Prompt/schema IDs in the
draft are reserved; it is not an executable replacement config yet.

Next extraction: inspect `analyse_assembly_img` and its image-describer call chain
in full; bring over the active assembly prompts and `AssemblyAnalysis` schema;
implement its input builder and pure result contract. Then implement monopart
analysis, copy/BOM merging, sequence generation/revision, sequence rendering,
interaction analysis, FfA classification/scoring, and reporting in that order.
Connect the user agent and UI after their workflow/data interfaces are available.

Structural deletion waits until the replacement has passed its relevant checks.
The current shell has no `python`, `py`, or `conda` on PATH, and the checked-in
venv references another machine. Subsequent inspection found a Python 3.14
interpreter at `C:/Users/Mika/miniconda3/python.exe`, but it lacks PyYAML.
Runtime checks still require the actual project environment before claiming parity.

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
user_agent:
  system_prompt: system_v1
nodes:
  assembly_analysis:
    enabled: true
    prompts:
      system: system_v1
      human: human_v1
    structured_output: assembly_analysis_v1
    model:
      id: "5.4"
      max_completion_tokens: 8000
    inputs:
      assembly_metadata:
        enabled: true
        fields: [total_parts, unique_parts, bounding_box]
      assembly_images:
        enabled: true
        views: [iso1, iso1_exploded]
        limit: 2
        downscale_factor: 0.7
      user_context:
        enabled: true
        max_chars: 12000
    execution:
      max_retries: 2
```

A vanilla LLM node declares required artifact inputs, builds a configured prompt payload, resolves local prompt/schema IDs, executes via shared infrastructure, validates its output, and returns a structured result plus artifact references. Runtime saves actual token usage, elapsed time, model identity, prompt texts/hashes, schema version, effective settings, selected inputs/revisions, and failure details. Config specifies token budgets; actual usage is measured.

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

The consolidated BOM becomes authoritative for unique-part geometry, detailed surfaces and placed instances; no separate part-metadata files are required. Assembly metadata and spatial relations belong in `assembly.json`. Preserve geometry-vs-instance relationships and copied instances. Keep original CAD facts as source evidence; user corrections are explicit overrides rather than destructive changes to original metadata.

Both direct UI edits and agent edits use one validated revision service. Preserve previous values, author/source, reason, and dependency provenance. Prevent stale edits and writes to results currently being regenerated. Mark affected descendants outdated; rerun only the affected dependency closure. Revoke sequence approval when the sequence changes. Keep report discussion grounded in the active result revisions.

Structured results and context are editable. Images/PDFs are viewable/downloadable and regenerated from edited source data. Preserve atomic partial interaction-analysis writes and their removal after final completion. Keep assessment/report artifacts tied to the sequence revision that produced them.

Replace process-global `APA_EXPERIMENT_OUTPUT_DIR`, `APA_EXPERIMENT_YAML`, and STEP/input-path routing with explicit execution/session context. Preprocessing currently copies results into shared `data/processed/stepparser`; remove that dependency only after sequence rendering accepts explicit session-local inputs. Concurrent sessions must not share output paths or configuration.

## Implementation phases and inspection checklist

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
