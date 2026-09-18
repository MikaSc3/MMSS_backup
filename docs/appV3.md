# STEP2FfA Streamlit App V3 Specification

## 1. Purpose

App V3 is the Streamlit interface for the agent-driven workflow in
`scripts/app_workflow_v3.py`.

The app must:

- keep the visual identity and overall layout of the existing Streamlit app;
- accept one STEP assembly and optional supporting documents;
- run the V3 workflow without blocking the Streamlit interface;
- let the content workflow agent conduct the complete user dialogue;
- make tool execution visibly understandable while it is running;
- display generated CAD renderings and final assessment artifacts;
- keep the agent available for questions about the final FFA report.

The existing V2 Streamlit app and V2 workflow must remain operational.

## 2. Existing App Findings

The current app already provides a strong base:

- a restrained STEP2FfA header and Fraunhofer/University branding;
- a horizontal workflow progress indicator;
- a STEP file uploader and start button;
- a two-column workspace;
- conversation on the left and visualization on the right;
- a background worker thread;
- thread-safe event and user-input queues;
- automatic discovery of assembly, monopart, sequence, and section renderings;
- final report download support.

The current layout ratio is approximately one-third conversation and
two-thirds visualization. Its green, orange, cyan, white, and light-grey
appearance should be retained.

The existing UI is connected specifically to `app_workflow_v2`. Its chat model
also assumes three separate workflow agents. V3 instead has one persistent
content workflow agent that controls grouped tools and remains active after the
FFA report has been generated.

## 3. V3 Workflow Findings

The V3 terminal workflow currently performs:

1. Session setup.
2. STEP preprocessing and path resolution.
3. Additional-document ingestion.
4. `Readadditional_Data_tool`.
5. `Set_Content_Context_tool`.
6. `Analyse_Assembly_tool`.
7. Assembly-understanding dialogue and possible reanalysis.
8. `Analyse_Monoparts_And_Merge_tool`.
9. `Generate_Or_Revise_Sequence_tool`.
10. Sequence approval/revision dialogue.
11. `Run_Final_Assessment_Pipeline_tool`.
12. Final FFA report explanation and open user Q&A.
13. `Finish_Workflow_tool` after the user explicitly finishes.

The V3 agent currently writes messages with `print()` and reads replies with
`input()`. Streamlit therefore needs a thin UI adapter that emits structured
events and reads replies from the existing input queue. The underlying grouped
workflow tools and output structure should not be duplicated.

## 4. Proposed Screen

### Header and controls

Keep the current header, logos, color palette, typography, progress bar, and
download location.

The upload area should contain:

- one required STEP file uploader;
- one optional multi-file uploader for PDF, DOCX, CSV, XLSX, TXT, MD, and JSON;
- the detected assembly name;
- a primary `Start Analysis` button;
- a compact list of selected files before processing starts.

The app should create a V3 session and pass the uploaded documents directly to
the document-ingestion stage. It should not depend on users manually placing
files in `data/input/Textbased_Data`.

### Left: agent dialogue

The left column is the single conversation with the content workflow agent.

It should show:

- user and agent messages in chronological order;
- Markdown rendered as readable technical content;
- a clear waiting state when the agent requires user input;
- a permanently usable input after the final report is available;
- approval and revision suggestions as small action buttons where useful;
- errors as conversation-level notices without losing prior messages.

Tool observations should not be inserted as normal agent chat messages. The
agent receives them in its LangChain message history, while the user sees their
structured representation on the right.

The dialogue remains open after final assessment. The workflow is complete only
after `Finish_Workflow_tool` is called in response to an explicit user request.

### Right: visualization and activity

The right column should use four tabs:

1. `Live`
2. `Renderings`
3. `Tool I/O`
4. `Artifacts`

`Live` is the default tab while processing. `Renderings` becomes the preferred
tab when a new image is generated. The user's selected tab must not be changed
automatically.

## 5. Demo Visualization

The `Live` tab should make activity obvious without inventing progress values.
It uses real workflow events to render:

### Current operation

A compact status band shows:

- active tool or dialogue checkpoint;
- running, waiting, completed, or failed state;
- elapsed time;
- a short plain-language description.

Example:

```text
RUNNING
Analyse Monoparts and Merge
8 of 14 part results available
```

### V3 tool pipeline

A vertical activity list shows the grouped V3 operations:

```text
[complete] Read supporting documents
[complete] Analyse assembly
[running ] Analyse monoparts and merge       8 / 14
[queued  ] Generate assembly sequence
[queued  ] Final assessment pipeline
[queued  ] Final report dialogue
```

Each row has a stable status icon, tool name, duration when known, and a short
result summary. Dialogue checkpoints appear as `Waiting for user` rather than
as another processing step.

### Latest visual

Below or beside the activity list, show the newest relevant rendering:

- complete assembly during assembly analysis;
- latest analysed part during monopart analysis;
- latest assembly step during sequence rendering;
- interaction section image during interaction analysis;
- FFA chart or representative step image after assessment.

Before an image exists, the stage shows the current operation and a restrained
loading indicator. It must not display a fake percentage.

This view can initially be developed with a recorded demo event fixture, but
the production app must be driven by real V3 events.

## 6. Renderings Tab

Reuse the current image discovery logic, adapted to the V3 output directory.

Provide a segmented view selector:

- Assembly
- Parts
- Sequence
- Sections
- FFA

The main image uses the existing contained, light-background rendering stage.
A thumbnail strip or previous/next controls allow inspection without changing
the workflow state.

For monoparts, show the current part name or ID and actual completion count.
For sequence images, show the assembly step number and image type.

## 7. Tool I/O Tab

Every tool call should create a structured activity record:

- tool name;
- start and finish timestamp;
- status;
- sanitized arguments;
- context-block character count;
- prompt/input summary;
- full or bounded tool observation;
- generated artifact paths;
- error details, if any.

The tab displays one expandable row per call. The collapsed row is concise:

```text
Analyse_Assembly_tool   Completed   01:42
```

The expanded view contains:

- `Input`: context and revision remarks passed by the content agent;
- `Prompt`: the effective human-message content or a bounded preview;
- `Output`: the ToolMessage returned to the agent;
- `Artifacts`: clickable/downloadable files where supported.

System prompts and secrets must not be exposed by default. A developer-mode
flag may enable full prompt inspection for testing.

## 8. Artifacts Tab

The artifacts view groups outputs by workflow stage:

- document summary and content-agent understanding;
- assembly overview JSON;
- enriched monopart files and merged BOM;
- generated assembly sequence;
- sequence and section renderings;
- interaction analyses;
- FFA assessment JSON;
- synthesized FFA report JSON;
- chart and PDF report.

JSON and Markdown files receive an in-app preview. Images open in the rendering
stage. PDF and JSON outputs have download actions.

After the final pipeline finishes, the synthesized FFA report JSON must remain
in the agent's tool-message history so follow-up questions can be answered.

## 9. Event Contract

V3 should expose an optional `ui_callback` and `input_queue`, following the
working V2 pattern. The terminal path continues using `print()` and `input()`.

Recommended event types:

| Event | Purpose |
| --- | --- |
| `session_created` | Publish session and assembly paths |
| `agent_message` | Add content-agent text to the left dialogue |
| `input_waiting` | Enable user input and identify the checkpoint |
| `input_received` | Clear the waiting state |
| `phase_changed` | Update the high-level progress indicator |
| `tool_started` | Create an active tool record |
| `tool_progress` | Report real item counts, such as analysed parts |
| `tool_completed` | Store ToolMessage, timing, summary, and artifacts |
| `tool_failed` | Show failure details and stop or allow retry |
| `rendering_ready` | Publish a newly generated image |
| `artifacts` | Publish final report and download paths |
| `complete` | Mark the dialogue/workflow as explicitly finished |

The callback must receive plain dictionaries and must never call `st.*` from
the worker thread.

## 10. Proposed File Structure

Create V3-specific UI files first, reusing shared styling and components where
safe:

```text
8_open_streamlit_app_v3.py
ui/
  app_v3.py
  workflow_runner_v3.py
  state_v3.py
  components/
    chat_v3.py
    activity_v3.py
    renderings_v3.py
    tool_io_v3.py
    artifacts_v3.py
```

The implementation should extract shared visual styles only when doing so does
not risk changing the existing app. V2 files remain runnable throughout the V3
implementation.

## 11. Workflow Adapter

Refactor V3 conservatively:

- add an interface for agent output, user input, and workflow events;
- keep terminal behavior as the default for the root terminal launcher;
- use the same V3 tools, prompts, config, session state, and output paths;
- emit tool events around each existing LangChain tool invocation;
- return the actual ToolMessage content to both the agent history and UI event;
- emit artifacts as soon as they become available;
- preserve parallel monopart, interaction, and FFA execution from
  `appconfigV2.yaml`.

The Streamlit runner should:

1. save all uploads inside the V3 session;
2. start V3 in one background worker thread;
3. pass the event queue callback and user input queue;
4. never access Streamlit session state from the worker;
5. keep the agent thread alive during final-report Q&A.

## 12. Progress Model

The existing twelve-step progress bar can be retained with V3 labels:

1. Upload data
2. Preprocess STEP
3. Read documents
4. Analyse assembly
5. Confirm assembly understanding
6. Analyse monoparts
7. Generate sequence
8. Confirm or revise sequence
9. Render and analyse interactions
10. Assess fitness for automation
11. Generate FFA report
12. Discuss report

Only real phase transitions advance the bar. Parallel work reports counts such
as `8 / 14`, not estimated percentages.

## 13. Error and Recovery Behavior

- File-ingestion warnings are shown next to the affected document.
- A failed optional document must not discard a valid STEP upload.
- A failed tool shows its ToolMessage/error and offers a retry where safe.
- User dialogue and completed tool records survive Streamlit reruns.
- Starting a new analysis requires an explicit reset action.
- The existing output folder must not be silently overwritten without showing
  the selected session path.

## 14. Implementation Stages

### Stage 1: V3 UI shell and event bridge

- Copy the existing appearance into a separate V3 app.
- Add STEP plus supporting-document uploads.
- Add a V3 worker adapter, input queue, and event model.
- Connect content-agent messages and user replies.
- Build the `Live` demo visualization using real or recorded events.

### Stage 2: Tool and rendering visibility

- Emit tool start/completion events.
- Add tool input/output expanders.
- Adapt rendering discovery to V3 artifacts.
- Add real part and assembly-step counters.

### Stage 3: final artifacts and report dialogue

- Add artifact previews and downloads.
- Publish the FFA report JSON to the UI and agent.
- Keep final Q&A active until explicit completion.
- Add reset, retry, and failure handling.

## 15. Acceptance Criteria

- The V2 Streamlit app and V2 terminal workflow still run unchanged.
- App V3 accepts STEP and multiple supporting documents.
- The UI remains responsive throughout processing.
- The left column contains one continuous content-agent conversation.
- User input is enabled at assembly, sequence, and final-report checkpoints.
- The right column visibly reflects real tool and rendering activity.
- ToolMessage output is available to both the agent and the Tool I/O view.
- Generated images appear without manually refreshing the page.
- Final FFA JSON and PDF are previewable/downloadable.
- The agent can answer report questions after pipeline completion.
- The app only finishes after the user explicitly ends the dialogue.

## 16. Recommended First Build

Start with a separate `appv3/app.py` and launcher. Reuse the current visual CSS,
header, progress bar, and image-stage behavior. Add the event adapter to V3
before building detailed panels, because agent dialogue and trustworthy live
activity both depend on the same event stream.

## 17. Implemented Initial Version

The first V3 Streamlit implementation now uses:

```text
8_open_streamlit_app_v3.py
appv3/
  app.py
  runner.py
  state.py
```

Implemented behavior:

- separate V3 launcher and UI, without replacing the existing app;
- STEP and multi-document uploads;
- a real content-agent introduction whose AI message is retained as the first
  message in the later workflow conversation;
- agent-controlled STEP preprocessing and document ingestion through
  `Preprocess_Input_Data_tool`;
- background execution of `app_workflow_v3`;
- event and input queues for the content-agent dialogue;
- live grouped-tool states and actual elapsed durations;
- assembly, part, sequence, section, and FFA image discovery;
- ToolMessage inspection in the `Tool I/O` tab;
- generated text, JSON, CSV, and PDF artifact previews/downloads;
- final-report dialogue that remains active until explicit completion.

Run it with:

```powershell
python 8_open_streamlit_app_v3.py
```

## 18. Stage-Aware Visualization

The single visualization box is driven by real generated artifacts rather than
the modification time of any arbitrary image.

| Workflow state | Evidence used | Visual shown |
| --- | --- | --- |
| STEP preprocessing | images below `preprocessing/stepparser` | assembly CAD view and rendering count |
| Document reading | Markdown below `Agent_txt_files/ingested_documents` | assembly view and document count |
| Assembly analysis | `assembly_*_Overview_Enriched.json` | assembly CAD view |
| Monopart analysis | `enriched_parts/part_*_Data_enriched.json` | latest analysed part and analysed/total count |
| Assembly sequence generation | `assembly_sequence_run*/assembly_sequence.json` | assembly view and generated step count |
| Assembly sequence rendering | `sequence_renderings/step_*_iso1_transp_0_0.png` | latest rendered step and rendered/total count |
| Interaction analysis | `interaction_analysis.json` | latest section or assembly-step rendering |
| FfA assessment | `ffa_assessment/ffa_assessment.json` | latest assembly-step rendering |
| Report synthesis | `ffa_report/*_ffa_report.json` | FfA plot when available |
| Complete | FfA report JSON/PDF and plot | final FfA plot and assessed-step count |

The title, short detail, and any count bar are rendered inside the visualization
stage. Counts are shown only when the corresponding total can be obtained from
the BOM or assembly-sequence JSON.

The visualization may also show up to three concise facts extracted from the
current JSON artifact:

- assembly: `assembly_name_guess`, first `primary_function`, `total_parts`, and
  `unique_parts`; assembly review instead uses selected lines from
  `assembly_description` and `partslist`;
- latest part: `part_id`, `part_name_guess`, first
  `geometric_characteristics`, and first `handling_implications`;
- current assembly-step description, joining process, and joining part;
- FfA: most challenging `step_id`/`step_description`, one selected risk from
  `joining_risks`, `positioning_risks`, `handling_risks`, or
  `separation_risks`, and one assembly-level `improvements` item.

These facts are previews only. The content agent remains responsible for the
full explanation and user dialogue. Complete JSON objects and non-whitelisted
keys are never rendered in the visualization.

The right workspace separates these two concerns: the compact JSON-derived
result preview is shown on the left, and the larger CAD, assembly-step, or FfA
image is shown on the right. Sequence confidence is intentionally not shown.

The final assessment pipeline emits explicit `FINAL_RENDERING`,
`FINAL_INTERACTIONS`, `FINAL_FFA`, and `FINAL_REPORT` events. This keeps the
visualization synchronized with the actual internal operation instead of
depending only on filesystem timing.
