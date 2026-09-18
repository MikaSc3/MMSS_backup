# APP Rework V3

Working spec and change log for the proposed `app_workflow_v3`.

Last updated: 2026-06-11

## Goal

Create a new workflow architecture around a **content agent**.

The content agent should:

- Communicate with the end user.
- Ask for STEP data and additional supporting data.
- Ingest and screen user-provided documents.
- Tell the user what it understood before running heavy workflow steps.
- Call workflow subprocesses as tools.
- Pass an additional content block into LLM-based workflow nodes.
- Preserve the same output structure as `scripts/app_workflow_v2.py` and `1_run_app_workflow_terminal.py`.
- Work from the VS Code terminal and from a Streamlit app. A new Streamlit app is acceptable.

## Current V2 Workflow Understanding

Current implementation:

```text
1_run_app_workflow_terminal.py
  -> scripts/app_workflow_v2.py
```

Main v2 state machine:

```text
PHASE_1
  -> PHASE_2a
  -> AGENT_1
  -> PHASE_2b
  -> AGENT_2_LOOP
  -> PHASE_4
  -> AGENT_3
  -> DONE
```

Main v2 functions:

```text
scripts/app_workflow_v2.py
  setup_session()
  load_config()
  load_prompt_library()
  run_phase_1()
  run_phase_2a_only()
  run_phase_2b_onwards()
  run_agent_1()
  run_agent_2_loop()
  run_phase_4()
  run_agent_3()
  run_app_workflow_v2()
```

Important reused workflow nodes:

```text
agent.workflow._node_resolve_paths
agent.workflow._node_run_assembly
agent.workflow._node_list_parts
agent.workflow._node_run_monoparts
agent.workflow._node_merge_copy_part_data
agent.workflow._node_merge_bom
agent.workflow._node_generate_assembly_sequence
agent.workflow._node_generate_assembly_sequence_v2_agent_feedback
agent.workflow._node_render_assembly_steps
agent.workflow._node_interaction_analysis
agent.workflow._node_assess_ffa
agent.workflow._node_ffa_reporter
agent.workflow._node_ffa_post_processing
```

V2 output structure to preserve:

```text
session_root/
  input/
  preprocessing/
  Agent_txt_files/
  enriched_parts/
  assembly_sequence_run1/
    assembly_sequence.json
    sequence_renderings/
    interaction_analysis.json
  assembly_sequence_runN/
    assembly_sequence.json
    sequence_renderings/
    interaction_analysis.json
  ffa_assessment/
    ffa_assessment.json
  ffa_report/
```

The new workflow must keep this structure compatible so downstream exporters, evaluation scripts, and UI artifact loading still work.

## Proposed V3 Workflow

V3 should shift from a hard-coded phase driver to an agent-controlled workflow with callable tools.

High-level flow:

```text
User
  -> Content Agent conversation
  -> document ingestion and summary
  -> user confirmation of interpreted context
  -> auto: preprocess STEP + resolve paths
  -> tool: analyse assembly
  -> content-agent presents assembly understanding
  -> optional user correction/additional context
  -> optional tool rerun: analyse assembly with updated context
  -> tool: analyse monoparts + merge enriched data/BOM
  -> tool: generate or revise assembly sequence
  -> content/sequence feedback loop
  -> tool: render sequence + interaction analysis + FFA assessment + report
  -> final presentation to user
```

Proposed v3 state machine:

```text
SETUP_SESSION
  -> CONTENT_COLLECTION
  -> DOCUMENT_INGESTION
  -> CONTENT_UNDERSTANDING_REVIEW
  -> PREPROCESS_AND_ANALYSE
  -> MONOPART_AND_SEQUENCE
  -> SEQUENCE_FEEDBACK_LOOP
  -> RENDER_INTERACTION_FFA
  -> FINAL_REPORT_AGENT
  -> DONE
```

The content agent controls when to call the tools, but the tools should remain deterministic wrappers around existing v2 functions and nodes.

Reduced tool-call flow:

```text
User activates processing
  -> auto setup_session
  -> auto run_stepparser_and_resolve_paths
  -> ingest_user_documents_tool
  -> build_content_understanding_tool
  -> user confirms/corrects understanding
  -> analyse_assembly_tool
  -> content agent presents assembly understanding
  -> user can add important input
  -> analyse_assembly_tool reruns if needed
  -> analyse_monoparts_and_merge_tool
  -> generate_or_revise_sequence_tool
  -> user confirms/revises sequence
  -> generate_or_revise_sequence_tool as needed
  -> run_final_assessment_pipeline_tool
  -> final presentation/downloads
```

## Content Agent Responsibilities

The content agent should ask the user for:

- Assembly name.
- STEP file.
- Optional PDF, Word, CSV, Excel, TXT, Markdown, JSON files.
- Any manual assembly order, remarks, requirements, known constraints, or manufacturing context.
- Confirmation that the agent understood the added context correctly.

The content agent should produce:

```text
additional_context_block
```

This should be a concise but information-rich Markdown/text block that can be injected into downstream LLM prompts.

Suggested structure:

```markdown
## User Provided Assembly Context

### User Intent
...

### Uploaded Document Summary
...

### Assembly Constraints
...

### Manual Assembly Knowledge
...

### Part/Step Hints
...

### Uncertainties
...
```

This block should be stored in state as:

```python
state["additional_context_block"]
```

It should also be persisted to disk:

```text
session_root/Agent_txt_files/content_agent_understanding.md
session_root/Agent_txt_files/additional_context_block.md
```

## Document Ingestion

Required formats:

```text
PDF
Word / DOCX
CSV
Excel
TXT
Markdown
JSON
```

Recommended ingestion strategy:

### MarkItDown

Use MarkItDown as the default simple converter.

Good when the flow is:

```text
uploaded file -> markdown/text -> content agent summary -> additional_context_block
```

Supported formats include PDF, PowerPoint, Word, Excel, images, HTML, CSV, JSON, XML, ZIP, and more.

### Docling

Use Docling when PDFs or Word documents contain important layout-sensitive information:

- Tables.
- Figures.
- Technical drawings.
- Assembly instructions.
- Manufacturing process descriptions.
- Structured engineering documents.

Docling is better for rich document structure and table/layout preservation.

### Direct Readers

Use direct readers where structure matters:

```text
CSV / Excel -> pandas
JSON        -> json / pydantic
TXT / MD    -> pathlib read_text()
```

Recommended implementation:

```text
agent/content_ingestion.py
  ingest_documents(paths) -> DocumentBundle
  convert_with_markitdown(path) -> IngestedDocument
  convert_with_docling(path) -> IngestedDocument
  read_csv_or_excel(path) -> IngestedDocument
  read_json(path) -> IngestedDocument
  read_text(path) -> IngestedDocument
```

Suggested data model:

```python
class IngestedDocument(BaseModel):
    source_path: str
    file_name: str
    file_type: str
    extraction_backend: str
    text: str
    tables: list[dict] = []
    warnings: list[str] = []

class DocumentBundle(BaseModel):
    documents: list[IngestedDocument]
    combined_markdown: str
    warnings: list[str] = []
```

## Tool Boundaries For V3

Create deterministic tool wrappers around v2 subprocesses. These should be callable by the content agent and reusable by terminal and Streamlit workflows.

The tools should be grouped by meaningful agent decision points. Do not expose tiny mechanical steps as separate tools when the content agent cannot add useful information or make a useful decision between them.

Recommended module:

```text
agent/app_workflow_v3_tools.py
```

Recommended grouped tools:

```text
ingest_user_documents_tool
build_content_understanding_tool
analyse_assembly_tool
analyse_monoparts_and_merge_tool
generate_or_revise_sequence_tool
run_final_assessment_pipeline_tool
```

The tools should operate on one shared workflow state dict and should return updated state.

`setup_session` is not an agent tool. It is automatically triggered when the user activates processing in terminal or Streamlit mode. The agent should not need to decide whether to create the session.

`run_stepparser` and path resolution are also not agent tools. They are automatically triggered after session setup, before the first assembly analysis. The content agent should not decide whether geometry preprocessing happens; it only decides how to use the resulting information.

### Tool 1: `ingest_user_documents_tool`

Purpose:

- Read uploaded files.
- Convert documents into text/Markdown/structured snippets.
- Return a `DocumentBundle`.
- Save raw ingestion artifacts under `Agent_txt_files/ingested_documents/`.

This is a real tool because the content agent can inspect, summarize, and ask follow-up questions about the ingested content.

### Tool 2: `build_content_understanding_tool`

Purpose:

- Combine user conversation and ingested document summaries.
- Produce the final `additional_context_block`.
- Save:

```text
Agent_txt_files/content_agent_understanding.md
Agent_txt_files/additional_context_block.md
```

This is a real tool because the agent should present its understanding to the user before running expensive CAD/LLM workflow steps.

### Tool 3: `analyse_assembly_tool`

Runs assembly analysis after automatic preprocessing.

```text
analyse_assembly
```

Wrapped v2 calls:

```text
agent.workflow._node_run_assembly
```

The assembly analyser receives `additional_context_block` as `CONTENT_AGENT_CONTEXT` in its human prompt.

Important interaction:

- After this tool runs, the content agent must present its understanding of the assembly to the user.
- If the user adds important input, corrections, missing constraints, or document interpretation fixes, the content agent should update `additional_context_block` and rerun `analyse_assembly_tool`.
- This rerun should overwrite/update assembly enriched metadata in the same v2-compatible location.

Automatic preconditions:

```text
setup_session
run_stepparser
resolve_paths
```

Reason for keeping assembly analysis as a separate tool:

- The assembly understanding is the first meaningful LLM interpretation of the CAD data.
- The user may know important context that changes this interpretation.
- The content agent needs a clean rerun point after user feedback.

### Tool 4: `analyse_monoparts_and_merge_tool`

Bundles previous steps 9 and 10:

```text
analyse_monoparts
merge_copy_part_data
merge_bom
```

Wrapped v2 calls:

```text
agent.workflow._node_list_parts
agent.workflow._node_run_monoparts
agent.workflow._node_merge_copy_part_data
agent.workflow._node_merge_bom
```

The monopart analyser receives `additional_context_block` as `CONTENT_AGENT_CONTEXT` in its human prompt.

Reason for grouping:

- Monopart analysis and merge are a unit of work.
- Merge steps are purely mechanical.
- The agent should only see the final enriched-part/BOM result.

### Tool 5: `generate_or_revise_sequence_tool`

Represents previous step 11 and revision regeneration.

Wrapped v2 calls:

```text
agent.workflow._node_generate_assembly_sequence
agent.workflow._node_generate_assembly_sequence_v2_agent_feedback
```

The sequence generator receives `additional_context_block` as `CONTENT_AGENT_CONTEXT` in its human prompt.

Inputs:

```text
additional_context_block
optional revision remarks from user/content agent
current sequence_run_counter
```

Outputs:

```text
assembly_sequence_runN/assembly_sequence.json
state["assembly_sequence_path"]
state["assembly_sequence_data"]
```

Reason for keeping this separate:

- Sequence generation is a major decision point.
- The content agent must show the sequence to the user.
- The user may request revisions before final assessment.

### Tool 6: `run_final_assessment_pipeline_tool`

Bundles previous steps 14, 15, 16, and 17:

```text
render_assembly_steps
interaction_analysis
ffa_assessment
ffa_report
ffa_post_processing
```

Wrapped v2 calls:

```text
agent.workflow._node_render_assembly_steps
agent.workflow._node_interaction_analysis
agent.workflow._node_assess_ffa
agent.workflow._node_ffa_reporter
agent.workflow._node_ffa_post_processing
```

The interaction analyst receives `additional_context_block` as `CONTENT_AGENT_CONTEXT` in its human prompt.

Reason for grouping:

- Once the sequence is approved, these steps are the final deterministic pipeline.
- Rendering, interaction analysis, FFA assessment, and report generation are not useful separate user decision points.
- The agent can present final artifacts after the grouped call.

Important rule:

Do not invent a new output layout unless absolutely necessary. Tool wrappers should call existing v2 nodes/functions and write to the same folders as v2.

## Prompt-Building Changes

The following LLM-based nodes must accept the content-agent block:

```text
Assembly Analyser
Monopart Analyser
Assembly Sequence Generator
Interaction Analyst
```

Affected functions:

```text
agent.tools.analyse_assembly_img()
agent.tools.analyse_monopart_img()
agent.tools._describe_images_in_dir_impl()
agent.Assembly_sequence_generation.generate_assembly_sequence()
agent.Assembly_sequence_generation.generate_assembly_sequence_from_gt()
agent.Interaction_analysis.analyze_step_interaction()
agent.Interaction_analysis.analyze_assembly_sequence_interactions()
```

Affected workflow nodes:

```text
agent.workflow._node_run_assembly
agent.workflow._node_run_monoparts
agent.workflow._node_generate_assembly_sequence
agent.workflow._node_generate_assembly_sequence_v2_agent_feedback
agent.workflow._node_generate_assembly_sequence_from_gt
agent.workflow._node_interaction_analysis
```

Suggested parameter name:

```python
additional_context_block: Optional[str] = None
```

Conceptual rule:

The content agent passes the context block when calling a grouped tool. The context is tool-call scoped.

Example:

```python
analyse_assembly_tool(
    state=state,
    context_block="Context relevant for assembly-level understanding...",
)
```

The wrapper may temporarily place this into the copied state passed to existing v2 nodes, but the design should not depend on one permanent global context block.

Suggested prompt injection label:

```text
CONTENT_AGENT_CONTEXT
```

Example human prompt addition:

```text
=== CONTENT_AGENT_CONTEXT ===
The following context was collected from the user and uploaded documents.
Use it as supporting information. Prefer geometry/renderings/BOM when conflicts exist,
but use this context to interpret unclear parts, constraints, and assembly intent.

{context_block}
```

Important:

- The content block should be appended to the human message, not the system message.
- It should be available in prompt previews/stats.
- It should be truncated with a configurable max character length.
- It should not silently override structured geometry/BOM data.

Recommended settings:

```yaml
content_agent:
  enabled: true
  max_context_chars: 12000
  save_ingested_markdown: true
  ingestion_backend: "markitdown"  # markitdown | docling | auto

AAI_use_content_agent_context: true
AMI_use_content_agent_context: true
ASG_use_content_agent_context: true
IA_use_content_agent_context: true
```

## Content Agent Design

Recommended module:

```text
agent/content_agent.py
```

Responsibilities:

- Conduct an initial conversation.
- Ask for missing input.
- Summarize uploaded documents.
- Identify useful assembly hints.
- Ask the user to confirm or correct the understanding.
- Build context blocks for specific tool calls.
- Store the user-approved content understanding for traceability.
- Then orchestrate tool calls.

Recommended methods:

```python
class ContentAgent:
    def collect_inputs(...)
    def ingest_documents(...)
    def summarize_understanding(...)
    def ask_user_confirmation(...)
    def build_additional_context_block(...)
    def run_workflow_tools(...)
```

Terminal mode can use `input()`.

Streamlit mode should use queues/callbacks, like v2:

```text
input_queue
ui_callback
```

## Terminal Entrypoint

Create:

```text
7_run_app_workflow_AGENT_terminal.py
```

Expected behavior:

- Ask for assembly name and STEP path if not provided.
- Ask for additional files.
- Run content-agent understanding.
- Ask user to approve/correct.
- Run tool-based workflow.
- Write same output structure as v2.

Suggested command:

```powershell
python 7_run_app_workflow_AGENT_terminal.py
```

Optional arguments:

```text
--assembly
--step-file
--additional-file
--auto
--config
--session-root
```

## Streamlit V3 App

The current Streamlit app does not need to be modified if a new app is easier.

Recommended new app:

```text
ui/app_v3.py
```

Recommended launcher:

```text
8_open_streamlit_app_v3.py
```

V3 Streamlit app should support:

- STEP upload.
- Multiple additional document uploads.
- Chat with content agent.
- Display of content-agent understanding.
- Approve/edit context.
- Run subprocess tools.
- Sequence feedback/revision loop.
- Artifact display/download.

The app should still write session data under:

```text
data/sessions/{timestamp}_{assembly_name}/
```

## Compatibility Requirements

V3 must remain compatible with:

```text
2_export_assy_sequence_ground_truth.py
3_run_experiments_sequence_gt.py
4_prepare_ffa_report_ground_truth_from_run.py
5_run_evaluation.py
```

Therefore preserve:

```text
assembly_sequence_runN/assembly_sequence.json
assembly_sequence_runN/sequence_renderings/
assembly_sequence_runN/interaction_analysis.json
ffa_assessment/ffa_assessment.json
ffa_report/
Agent_txt_files/
```

## Implementation Plan

### Phase 1: Spec And Refactor Boundaries

- Keep `scripts/app_workflow_v2.py` stable.
- Add v3 files beside it rather than modifying v2 heavily.
- Identify exact prompt-construction points.
- Add a single state key: `additional_context_block`.

### Phase 2: Prompt Context Plumbing

- Add optional `additional_context_block` parameter to assembly analysis.
- Add optional `additional_context_block` parameter to monopart analysis.
- Add optional `additional_context_block` parameter to sequence generation.
- Add optional `additional_context_block` parameter to interaction analysis.
- Pass the state key through the matching workflow nodes.
- Add prompt preview/stats entries for context label and char length.

### Phase 3: Document Ingestion

- Create `agent/content_ingestion.py`.
- Implement direct readers for TXT/MD/JSON/CSV/Excel.
- Add MarkItDown support as default converter.
- Add Docling as optional backend for layout-heavy files.
- Save ingested markdown/text under:

```text
session_root/Agent_txt_files/ingested_documents/
```

### Phase 4: Content Agent

- Create `agent/content_agent.py`.
- Implement terminal-friendly user interaction.
- Implement UI-friendly `input_queue` / `ui_callback` interaction.
- Produce `content_agent_understanding.md`.
- Produce `additional_context_block.md`.

### Phase 5: Tool Wrappers

- Create `agent/app_workflow_v3_tools.py`.
- Wrap v2 nodes and functions in deterministic tools.
- Keep all tool outputs in v2-compatible locations.

### Phase 6: Terminal V3 Workflow

- Create `scripts/app_workflow_v3.py` or `scripts/app_workflow_v3_orchestrator.py`.
- Create root launcher `7_run_app_workflow_AGENT_terminal.py`.
- Verify output compatibility with the existing exporters.

### Phase 7: Streamlit V3 Workflow

- Create `ui/app_v3.py`.
- Create root launcher `8_open_streamlit_app_v3.py`.
- Support document upload and content-agent confirmation.
- Reuse v2 event style where practical.

### Phase 8: Tests And Smoke Checks

- Unit-test ingestion functions on sample TXT/JSON/CSV.
- Smoke-test MarkItDown if installed.
- Compile-check new modules.
- Run one small terminal workflow on a simple STEP file.
- Verify output folders match v2.
- Verify `2_export_assy_sequence_ground_truth.py` can consume v3 output.

## Open Design Decisions

- Should content-agent context be global state or passed per tool call?
  - Decision: pass context per grouped tool call. The content agent provides the relevant `context_block` argument when calling `analyse_assembly_tool`, `analyse_monoparts_and_merge_tool`, `generate_or_revise_sequence_tool`, or `run_final_assessment_pipeline_tool`.
  - Wrappers may temporarily adapt this into copied state for existing v2 nodes, but the mental model and public API are tool-call scoped.

- Should V3 use LangGraph tool-calling for all subprocesses, or a simpler explicit orchestrator with agent decision points?
  - Initial recommendation: deterministic orchestrator with content-agent decision points. This is easier to debug and safer for CAD/LLM workflows.

- Should Docling be a hard dependency?
  - Initial recommendation: no. Use MarkItDown/default readers first. Add Docling as optional backend.

- Should the content agent be allowed to skip workflow tools?
  - Initial recommendation: only with user confirmation. Heavy CAD workflows should remain predictable.

## Risks

- Prompt context can become too large. Use max length settings and summaries.
- Uploaded documents may conflict with geometry/BOM. Prompts must say geometry/renderings/BOM win when conflicts exist.
- PDF/Word ingestion quality may vary. Store warnings and show them to the user.
- Tool-calling agents can become hard to debug. Keep deterministic wrappers and explicit state transitions.
- Streamlit threading/input queues are fragile. Reuse v2 patterns where possible.

## First Concrete Coding Tasks

The v3 implementation should be additive first. Do not replace v2 until v3 has a successful terminal smoke run and output compatibility check.

### Safety Guardrails

- Keep `1_run_app_workflow_terminal.py` working exactly as it does now.
- Keep `scripts/app_workflow_v2.py` stable; avoid editing v2 orchestration unless a tiny shared hook is clearly needed.
- Add v3 in new files first:

```text
agent/content_ingestion.py
agent/content_agent.py
agent/app_workflow_v3_tools.py
scripts/app_workflow_v3.py
7_run_app_workflow_AGENT_terminal.py
ui/app_v3.py
8_open_streamlit_app_v3.py
```

- Preserve the v2 output layout:

```text
assembly_sequence_runN/
ffa_assessment/
ffa_report/
Agent_txt_files/
enriched_parts/
```

- Do not remove or rename existing v2 folders, config keys, prompt IDs, or schema classes.
- Gate all new prompt-context behavior behind optional function parameters.
- If no `context_block` is passed, existing nodes must behave like before.
- Use focused compile checks after every implementation step.
- Before touching shared prompt-building code, make the smallest possible signature change.

### TODO 1: Add Context Injection Plumbing

Add optional `additional_context_block: Optional[str] = None` to low-level LLM functions:

```text
agent.tools.analyse_assembly_img
agent.tools.analyse_monopart_img
agent.tools._describe_images_in_dir_impl
agent.Assembly_sequence_generation.generate_assembly_sequence
agent.Assembly_sequence_generation.generate_assembly_sequence_from_gt
agent.Interaction_analysis.analyze_step_interaction
agent.Interaction_analysis.analyze_assembly_sequence_interactions
```

Required behavior:

- Default is `None`.
- Existing callers do not need to change.
- When present, inject as `CONTENT_AGENT_CONTEXT` in the human message.
- Truncate with a configurable max length.
- Record context label and char length in prompt stats where stats exist.
- Do not require a global state key.

Validation:

```powershell
python -m py_compile agent\tools.py agent\Assembly_sequence_generation.py agent\Interaction_analysis.py
```

### TODO 2: Add Context Adapters In Workflow Nodes

Add optional context adapters in:

```text
agent.workflow._node_run_assembly
agent.workflow._node_run_monoparts
agent.workflow._node_generate_assembly_sequence
agent.workflow._node_generate_assembly_sequence_v2_agent_feedback
agent.workflow._node_generate_assembly_sequence_from_gt
agent.workflow._node_interaction_analysis
```

Required behavior:

- Read `state.get("_tool_context_block")` or equivalent internal wrapper key only when v3 wrappers provide it.
- Pass it only to functions that accept it.
- If absent, behavior remains unchanged.
- Keep this key internal to v3 wrappers; do not make it a public workflow contract.

Validation:

```powershell
python -m py_compile agent\workflow.py
python -m py_compile 1_run_app_workflow_terminal.py scripts\app_workflow_v2.py
```

### TODO 3: Implement Document Ingestion

Create:

```text
agent/content_ingestion.py
```

Required behavior:

- TXT/MD via `Path.read_text`.
- JSON via `json`.
- CSV/Excel via pandas.
- MarkItDown as default optional converter if installed.
- Docling optional, not a hard dependency.
- Return warnings instead of crashing when optional backends are unavailable.
- Save extracted text under:

```text
session_root/Agent_txt_files/ingested_documents/
```

Validation:

```powershell
python -m py_compile agent\content_ingestion.py
```

### TODO 4: Implement Content Agent

Create:

```text
agent/content_agent.py
```

Required behavior:

- Terminal-compatible interaction.
- Streamlit-compatible interaction via `input_queue` and `ui_callback`.
- Builds tool-specific context blocks when calling grouped tools.
- Presents content understanding to the user before running assembly analysis.
- Presents assembly understanding after `analyse_assembly_tool`.
- Allows the user to add important input and rerun `analyse_assembly_tool`.
- Saves:

```text
Agent_txt_files/content_agent_understanding.md
Agent_txt_files/additional_context_block.md
```

Validation:

```powershell
python -m py_compile agent\content_agent.py
```

### TODO 5: Implement Grouped Tool Wrappers

Create:

```text
agent/app_workflow_v3_tools.py
```

Agent-facing tools:

```text
ingest_user_documents_tool
build_content_understanding_tool
analyse_assembly_tool
analyse_monoparts_and_merge_tool
generate_or_revise_sequence_tool
run_final_assessment_pipeline_tool
```

Automatic, not agent-facing:

```text
setup_session
run_stepparser
resolve_paths
```

Required behavior:

- Wrap existing v2 nodes/functions.
- Use the same session/output paths as v2.
- Return updated state.
- Accept `context_block: str | None = None` on LLM-relevant grouped tools.
- Pass the context block to existing nodes through a copied/internal state adapter, not by permanently mutating global workflow state.
- Do not hide errors silently; return structured warnings/errors.

Validation:

```powershell
python -m py_compile agent\app_workflow_v3_tools.py
```

### TODO 6: Build Terminal V3 First

Create:

```text
scripts/app_workflow_v3.py
7_run_app_workflow_AGENT_terminal.py
```

Required behavior:

- Auto setup session.
- Auto run stepparser + resolve paths.
- Let content agent ingest and summarize data.
- Let user confirm/correct context.
- Run grouped tools with tool-call-scoped context blocks.
- Preserve output structure.

Validation:

```powershell
python -m py_compile scripts\app_workflow_v3.py 7_run_app_workflow_AGENT_terminal.py
```

Manual smoke test:

```powershell
python 7_run_app_workflow_AGENT_terminal.py --assembly "SmallTestAssembly" --auto
```

### TODO 7: Verify Compatibility With Current Pipeline

After a successful v3 terminal run, verify:

- `assembly_sequence_runN/assembly_sequence.json` exists.
- `assembly_sequence_runN/sequence_renderings/` exists after final pipeline.
- `ffa_assessment/ffa_assessment.json` exists.
- `ffa_report/` exists.
- `2_export_assy_sequence_ground_truth.py` can read the v3 output.

Compile current workflows again:

```powershell
python -m py_compile 1_run_app_workflow_terminal.py 2_export_assy_sequence_ground_truth.py 3_run_experiments_sequence_gt.py 4_prepare_ffa_report_ground_truth_from_run.py 5_run_evaluation.py
python -m py_compile scripts\app_workflow_v2.py scripts\full_workflow_experiments.py
```

### TODO 8: Build Streamlit V3 After Terminal Works

Create:

```text
ui/app_v3.py
8_open_streamlit_app_v3.py
```

Required behavior:

- Upload STEP file.
- Upload additional documents.
- Show content-agent understanding.
- Let user edit/approve context.
- Show assembly understanding after `analyse_assembly_tool`.
- Let user add input and rerun `analyse_assembly_tool`.
- Show sequence proposal and support revision loop.
- Run final grouped assessment pipeline.
- Show/download final artifacts.

Validation:

```powershell
python -m py_compile ui\app_v3.py 8_open_streamlit_app_v3.py
```

### TODO 9: Regression Checklist

Before considering v3 ready:

- Run compile checks on all touched files.
- Run current v2 terminal workflow on a tiny assembly or at least compile it.
- Confirm `6_open_streamlit_app.py` still launches the current UI.
- Confirm v3 writes no unexpected files into project root.
- Confirm `data/checkpoints` is not recreated by normal workflows.
- Update this spec change log.

### Deferred / Optional

- Make Docling an optional install extra.
- Add ingestion unit tests with small fixture files.
- Add a v3 config section in `configs/appconfig/appconfig.yaml`.
- Add a UI history browser for previous content-agent understanding files.
- Add per-node context blocks later if the single global block proves too blunt.

## Change Log

- 2026-06-11: Implemented terminal-first V3 scaffold: document ingestion, content-agent understanding/context files, grouped V3 workflow tools, `scripts/app_workflow_v3.py`, and root launcher `7_run_app_workflow_AGENT_terminal.py`.
- 2026-06-11: Added implementation TODOs, regression gates, and safety guardrails to protect current v2 workflows during v3 development.
- 2026-06-11: Initial V3 rework spec created. Captures content-agent concept, ingestion plan, tool boundaries, prompt-context plumbing, terminal/UI requirements, and compatibility constraints.
