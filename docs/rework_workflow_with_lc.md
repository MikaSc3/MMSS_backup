# Workflow and agent rework with LangChain / LangGraph

## Scope

This is an assessment of the application as it exists on 2026-10-02. It is not an implementation plan that changes runtime behaviour yet.

The aim is to identify where the current nodes, workflows, agent, persistence, and UI bridge duplicate capabilities that LangChain and LangGraph can provide. The goal is not to replace sound domain logic merely because it is custom.

## Executive finding

The domain layer is in good shape: individual LLM nodes have typed structured outputs, deterministic post-processing exists where it should, artifacts are persisted, and the two workflows already encode useful business capabilities.

The orchestration layer is the weak point. The application implements an agent loop, tool selection policy, state transitions, review checkpoints, fan-out, progress reporting, and recovery across several separate mechanisms:

- the large user-agent prompt;
- a hand-written LangChain message/tool loop;
- workflow service methods and callbacks;
- session and planning manifests;
- user-agent JSON state, feedback, and conversation files;
- Streamlit controller and event-normalisation code.

This duplication is the likely source of the observed missed tool calls, unwanted reruns, stale-state confusion, repeated self-narration, and difficult recovery after a partial workflow run. The central rework should therefore make workflow state and allowed transitions explicit in code, while retaining the existing node contracts and session artifacts.

## Current architecture

```text
Streamlit UI
  -> SessionController command queue
    -> UserFacingAgent
      -> manual LLM / tool-call loop
        -> WorkflowAgentTools
          -> AssemblyAssessmentWorkflow
          -> AutomationPlanningWorkflow
            -> typed LLM nodes + deterministic renderers/calculators
              -> session artifacts and manifests
```

### Node layer

The node modules are relatively well isolated. `run_llm_node` constructs a prompt, invokes the model with Pydantic structured output, persists the output artifact, and records the node run. The runtime also supports node-local LLM tools and manually resolves their tool-call loop before parsing the final structured result.

This is useful domain infrastructure. Simple nodes do not need to become LangGraph graphs just to be “more LangChain”. Their schemas, prompts, artifact paths, and deterministic helpers should be preserved.

### Assembly-assessment workflow

`AssemblyAssessmentWorkflow` imperatively coordinates preprocessing, assembly analysis, monopart analysis, BOM merge, sequence generation/rendering, interaction analysis, FfA assessment/scoring, and report synthesis/rendering. It owns manual stage updates, review waiting states, artifact revisions, parallel work via `ThreadPoolExecutor`, and callback emission.

The workflow exposes helpful domain entry points such as `prepare_through_sequence` and `complete_from_sequence`, but execution state is implicit in method order and persisted files rather than expressed as a graph state and transitions.

### Automation-planning workflow

`AutomationPlanningWorkflow` has the desired macro-to-detail shape:

1. generate an automation idea;
2. plan detailed automation for assembly steps in parallel;
3. aggregate and synthesize the automation concept;
4. optionally create/revise layout and calculate cost.

It currently manages its own planning manifest, fan-out, revision behaviour, and rendering/calculation calls independently of the assessment workflow.

### User-facing agent and tools

`UserFacingAgent` uses LangChain message types and structured tools, but it is not a LangChain agent runtime. On every user turn it reloads persisted history, calls a model bound to every tool, manually loops over tool calls, manually creates `ToolMessage` objects, appends messages to JSON history, and decides when to stop.

`WorkflowAgentTools` exposes a broad, flat tool list: session inspection, artifact reads and edits, assessment actions, sequence actions, and automation planning/layout/cost actions. Tool eligibility and expected next actions are mostly described in the system prompt instead of being enforced by the tool surface available for the current state.

### Persistence and UI bridge

There are several valid but separate state stores:

| Store | Current role |
| --- | --- |
| `manifest.json` | Assessment artifacts, revisions, and workflow stages |
| `automation_planning/planning_manifest.json` | Automation-planning artifacts and state |
| user-agent state / feedback / conversation JSON | Conversation and agent-specific state |
| Streamlit session state | UI interaction and presentation state |

The Streamlit controller serialises commands in a worker queue. UI progress is assembled from workflow callbacks, agent callbacks, session snapshots, and captured stdout/stderr. This works, but it is a custom event protocol rather than one execution stream with durable state.

## Strengths to retain

- Pydantic structured-output schemas and their field descriptions.
- Existing artifact formats, revision history, and atomic manifest writes.
- Deterministic steps such as rendering, layout drawing, and cost arithmetic.
- The existing workflow entry points and prerequisite checks during migration.
- The separation of macro automation idea, per-step planning, synthesis, layout, and cost estimation.
- Session-folder compatibility: existing completed sessions should remain readable and usable.
- The UI event envelope and progress display as a compatibility boundary while the execution engine is migrated.

## Confirmed problems and LangChain/LangGraph opportunities

| Current condition | Effect | Potential rework |
| --- | --- | --- |
| Hand-written outer tool loop | Reimplements agent execution, message management, error handling, and stop logic. | Use `create_agent` for the outer conversational agent. |
| All tools are bound all the time | The model must infer which of many actions is legal from prose. It can announce an action without calling it or select an action from the wrong phase. | Dynamically expose only state-appropriate capability tools using middleware. |
| Workflow order is encoded in a long prompt | Prompt wording becomes a hidden state machine. “Do not forget to call the tool” is a symptom, not an enforcement mechanism. | Put prerequisites and transitions in compiled workflow graphs and tool guards; keep the prompt focused on communication and judgement. |
| Mutable `current_user_message` bridge | Tool validation depends on transient agent object state rather than an explicit invocation context. | Pass session/user-turn context through `ToolRuntime` and typed runtime context. |
| Several independently-mutated state files | Stale flags, approvals, and recovery can disagree across layers. | Define one typed execution state and explicit projections to existing manifests/artifacts. |
| Manual fan-out with `ThreadPoolExecutor` | Parallel work, aggregation, failure handling, and retries are bespoke. | Use LangGraph fan-out (`Send`) / reducers for map-reduce style step and part planning. |
| No graph checkpoint model | A partial run depends on manually reconstructed status rather than resumable graph state. | Add a local checkpointer after state contracts are stable. |
| Full conversation history is reconstructed each turn | Context grows unnecessarily and requires JSON bookkeeping. | Let agent state/checkpoints own messages; retain a concise domain/session summary and artifact references. |
| Custom callbacks plus stdout/stderr capture | Progress is fragile and can be duplicated; global stdout capture is especially risky in threaded execution. | Stream graph updates and custom progress events; adapt them to the current UI event envelope. |
| Direct tool side effects with ad-hoc error strings | Retrying and user-facing recovery are inconsistent. | Use typed tool results, retry policies for safe node calls, and explicit failure transitions. |
| No LangGraph dependency or version contract | The intended architecture cannot be reliably implemented or tested yet. | Add pinned `langchain` / `langgraph` dependencies with a small compatibility test. |

## Important distinction: use LangChain where it helps

LangChain should not be introduced as an extra layer around every function. The valuable changes are:

- `@tool` wrappers for user-invocable *capabilities*;
- `create_agent` for the conversational tool-calling loop;
- middleware for dynamic system context and state-dependent tool exposure;
- `StateGraph` for durable, multi-stage workflows with branching and fan-out;
- checkpointing, streaming, retries, and tracing around those graphs.

The LLM node runtime can remain a focused abstraction. Deterministic layout generation and cost calculations should remain deterministic functions called from graph nodes, not be delegated to an agent.

## Target architecture

```text
Streamlit UI
  -> controller (command serialisation and UI adaptation only)
    -> LangChain create_agent
       AgentState: messages + concise session/planning references
       Runtime context: session root, user turn, services, permissions
       Middleware: dynamic prompt + allowed tools
         -> coarse capability tools (@tool)
           -> compiled LangGraph workflows
             -> existing domain nodes / deterministic services
             -> artifacts + manifests (domain record)
             -> graph checkpointer (execution record)
```

Artifacts/manifests remain the durable engineering record and support backward-compatible session inspection. Graph state/checkpoints describe execution position, pending work, message state, and resumability. The agent decides how to discuss and invoke permitted capabilities; it does not manually maintain the workflow state machine.

## Recommended graph boundaries

Do not begin with one graph that contains the entire product journey. Use small compiled graphs whose inputs and outputs are explicit.

| Graph | Responsibilities | Human review boundary |
| --- | --- | --- |
| Assessment preparation | Preprocess, assembly analysis, monoparts, BOM merge, sequence generation/rendering | Present sequence for review |
| Final FfA assessment | Interaction analysis, FfA fan-out, scoring, report synthesis/rendering | Runs only after approved sequence |
| Automation concept planning | Idea generation, per-step detailed planning fan-out, aggregation, concept synthesis | Present idea before detailed plan; present final concept after synthesis |
| Layout planning | Produce equipment coordinate list, deterministic layout rendering, minor list revisions | Present/revise layout |
| Cost estimation | Classify/map equipment, retrieve cost-list rows, calculate investment range | Present/revise assumptions |

At first, user review can remain outside a running graph: a graph completes at a review artifact, and a later tool starts the next graph after validation. This is simpler and safer than immediately using graph interrupts. Interrupts can be introduced once UI resume semantics and checkpoint persistence are proven.

## Tool design after rework

Expose capabilities, not every internal node. The agent should normally see a small set selected from the current session state.

| Session state | Candidate agent tools |
| --- | --- |
| No usable session input | Inspect session, ingest documents / explain requirements |
| Ready for assessment preparation | Start assessment preparation |
| Sequence awaiting review | Read sequence, revise sequence, approve sequence |
| FfA report available | Read report, start automation idea, optionally discuss DFA |
| Automation idea awaiting decision | Read idea, revise idea constraints, start detailed concept plan |
| Concept available | Read/revise concept, create/revise layout, create cost estimate |

Read-only artifact tools can remain available where useful, but should return compact projections by default. Internal operations such as “run one monopart node” should not be conversational tools unless there is a real user-facing reason to expose them.

## Rework sequence to plan next

## Implementation status — 2026-10-02

Completed in the first migration slice:

- Declared and installed compatible `langchain` and `langgraph` runtime dependencies.
- Replaced the production outer-agent execution path with `create_agent` for real LangChain chat models. The former manual loop remains only as a transitional fallback for injected legacy/test models.
- Converted the bound workflow methods to LangChain `@tool` definitions.
- Added middleware that filters the model-visible tools from the current session/artifact state, plus middleware that emits existing application tool events.
- Added a typed per-turn `AgentRuntimeContext` for the allowed tool set and current user message.
- Routed the approved-sequence final-assessment tool through a compiled LangGraph capability with an explicit input validation node.
- Routed approved automation-idea execution through a compiled LangGraph capability with an explicit session-owned idea validation node; its existing parallel detailed planning and concept synthesis remain cohesive domain work.
- Routed the assessment workflow through three explicit review-boundary graph capabilities: assembly analysis, monopart/BOM analysis, and sequence generation. Each completes at its respective HITL checkpoint, where the user can rerun, change, or approve the artifact.
- Grouped the agent tools by product capability (`session_context`, `assessment_review`, `artifact_review`, `automation_planning`, and `layout_and_cost`) while preserving state-based dynamic exposure.
- Added a per-session SQLite LangGraph checkpoint database for production chat-model agent state, including safe connection release when a Streamlit controller changes or stops a session.
- Removed global stdout/stderr interception from the Streamlit controller. The UI activity console now relies on the established structured workflow and tool events.
- Moved phase eligibility, effects, HITL boundaries, and rerun guidance out of the large agent prompt into the descriptions of grouped capability tools. The remaining prompt governs concise communication, evidence discipline, and non-rerun rules.
- Centralized stale-state invalidation/current-artifact transitions in `user_agent/state_transitions.py`; context changes, artifact edits, reruns, sequence changes, and final completion now use the same policy.
- Removed sequence approval as a separate capability. When the agent observes that the user has accepted the current sequence, it calls `ffa_evaluation` directly; no approval artifact or hidden expensive side effect is required.
- Reduced overlapping conversational tools: `change_artifact` is the only agent-driven edit capability, while exact JSON/field edits remain internal UI actions; `read_artifact` now reads both assessment and automation artifacts.
- Added a network-free real-LangChain-agent integration test. It verifies middleware-filtered tool binding at different checkpoints and SQLite checkpoint resume across a new agent instance.
- Replaced production use of the mutable active-message bridge with `ToolRuntime` context injection in tool-call middleware. Added typed, backward-compatible `AgentSessionState`/`StaleArtifacts` persistence for eligibility and transition state.

Not migrated yet:

- The final-assessment graph's execution node deliberately delegates to the existing cohesive workflow implementation. Rendering, interaction analysis, FfA fan-out, scoring, and reporting are dependent stages and will remain one product capability rather than being split into graph nodes without a user-facing benefit.
- Agent conversation JSON remains as a backward-compatible UI/history projection; LangGraph checkpoints are now the durable execution record for production agent turns.
- Streamlit still receives the established callback/event protocol. It is now structured workflow/tool progress only; fine-grained LangGraph stream events can be added later if the UI needs more detail.

The focused user-agent and automation-planning tests pass after this slice.

### Phase 0 — establish a safe baseline

1. Add compatible, pinned `langchain` and `langgraph` dependencies.
2. Add small tests for existing session states and tool preconditions.
3. Define the artifact/manifest compatibility contract: existing files remain authoritative domain output during the migration.
4. Define a single product event envelope that the UI continues to consume.

### Phase 1 — define explicit state and context

Create typed models for agent message state and concise session references; workflow state (stage, selected revisions, pending review, failures); runtime context (session root, service registry, user turn, permissions); and typed tool result/error payloads.

Decide which existing manifest fields are graph-state projections and centralise stale invalidation in one transition function.

### Phase 2 — replace the outer manual agent loop

Introduce `create_agent` with the existing model and a minimal set of wrapped capability tools. Use middleware to add current session status and concise artifact context to the prompt, filter tools by legal next actions, and enforce structured, non-self-narrating interaction behaviour.

Initially, these tools may delegate to the current workflow service methods. That limits migration risk while eliminating manual assistant/tool message handling and the mutable current-message bridge.

### Phase 3 — migrate a contained workflow first

The **final FfA assessment** remains a single cohesive graph capability with a clear approved-sequence input and a single report result.

Migrate **automation concept planning** next, where per-step detailed planning is the strongest candidate for graph fan-out and aggregation.

### Phase 4 — migrate review-oriented preparation

Move assessment preparation through sequence generation into its own graph. Keep explicit tool calls at review boundaries. Only consider graph interrupts after the simple start/complete/resume model is reliable.

### Phase 5 — unify streaming, persistence, and observability

1. Replace stdout capture for workflow progress with graph update/custom event streaming.
2. Add a local checkpointer keyed by session/thread ID.
3. Map graph events to the existing Streamlit event interface.
4. Add optional LangSmith tracing/evaluation with appropriate handling of proprietary CAD/session data.

## Decisions needed before implementation planning

- **Confirmed — state authority:** existing artifacts and manifests remain the durable domain record during the migration. Graph state/checkpoints are an execution-layer record alongside them, not a replacement.
- **Confirmed — review semantics:** begin with completed graphs at review points. A later, validated tool call starts the following graph; resumable graph interrupts are deferred.
- **Checkpoint store:** local SQLite is the natural first option; confirm location and retention policy.
- **Tool granularity:** confirm the small capability-tool surface versus retaining advanced internal/debug tools separately.
- **Cost data access:** decide whether the shared price list is read-only CSV, Excel ingestion into a normalized catalog, or a database-backed catalog.
- **Tracing policy:** decide whether external trace storage is permitted for session prompts, artifact excerpts, and images.

## Definition of success

The rework is successful when:

- an agent cannot call a phase-inappropriate workflow capability because that tool is not exposed or its graph guard rejects it;
- accepting a sequence starts final assessment exactly once without relying on a particular phrase in the prompt;
- a normal user disagreement does not invalidate or rerun FfA unless an explicit artifact-changing action requires it;
- interrupted runs can be inspected and resumed from a durable, typed state;
- the UI receives structured progress while long fan-out work is running;
- existing session artifacts remain readable; and
- prompt text becomes a communication policy, not the only definition of workflow behaviour.

## First planning workshop

Before coding the rework, choose the Phase 1 state contract and the first migration slice. The recommended first slice is:

```text
approved sequence
  -> final FfA assessment graph
  -> persisted FfA report
  -> existing UI event envelope
```

It is narrow enough to validate the approach, yet exercises the main benefits needed by the product: explicit prerequisites, parallel processing, durable state, controlled retries, and observable progress.
