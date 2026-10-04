# LangChain and LangGraph utilities for the future agent

This note distills `docs/langchain.md` for the assembly-automation application.
It is a migration guide, not an implementation plan for the current change set.

## Current position

The application currently uses `langchain-core` for messages, structured tools,
model binding, and tool-result messages. `UserFacingAgent.invoke()` implements a
complete manual model/tool loop, so it is not a binding-only implementation.
However, it also manually owns conversation reconstruction, tool dispatch,
round limits, error conversion, progress events, and state inspection.

The assembly and automation-planning workflows are deterministic Python
orchestrators, not LangGraph graphs. Durable business state is spread across the
session manifest, planning manifest, agent state, feedback, and conversation
JSON files. The installed project dependencies currently include
`langchain-core` and `langchain-openai`, but not `langchain` or `langgraph`.

## Target boundary

Use LangGraph for mandatory workflows and a LangChain agent for conversational
choice between complete business capabilities:

```text
domain nodes -> compiled workflow graphs -> coarse workflow tools -> outer agent
```

The outer model should choose capabilities such as:

- inspect the current session;
- analyze the assembly and parts;
- generate or revise a sequence;
- approve a sequence and complete the FfA assessment;
- generate/revise an automation concept;
- generate/revise a layout;
- calculate catalogue-backed costs.

It should not decide whether mandatory internal workflow stages, validation,
artifact publication, or stale-state propagation run. Those belong inside the
workflow graph or domain service.

## Core utilities we should adopt

### `create_agent`

Use `langchain.agents.create_agent` with an **unbound** model and the registered
tools passed separately. It supplies the standard model/tool execution loop and
removes most of the custom dispatch code in `UserFacingAgent.invoke()`.

Do not bind tools manually and then pass that bound model to `create_agent`.

### Typed agent state

Extend `AgentState` with a small trusted projection of application state, for
example:

- session ID and active sequence revision;
- approved revision;
- current checkpoint;
- artifact availability and stale flags;
- active idea, concept, layout, and cost revisions;
- pending review/approval information.

Do not copy complete CAD, BOM, report, or concept artifacts into agent state.
Keep the existing session files as business truth and store stable references,
hashes, and revisions in the agent state.

### Invocation context and `ToolRuntime`

Define an application context containing trusted values that the model must not
generate: session root, user/session identity, permissions, workflow services,
event sink, and configuration. Inject this through `ToolRuntime` rather than
exposing it as tool arguments.

### `@tool` with bounded argument schemas

Expose coarse business operations with Pydantic argument schemas, enums,
length limits, and descriptions that explain prerequisites and intended use.
Keep internal nodes private. Tool execution must enforce prerequisites again;
model-side tool visibility is not an authorization or correctness boundary.

### `Command(update=...)`

Workflow tools should return `Command` when they need to update parent agent
state. Include a `ToolMessage` using the runtime-provided tool-call ID. This
replaces direct mutation of fields such as `current_user_message` and avoids
requiring the model to rediscover state by repeatedly calling `inspect_session`.

### Dynamic prompt and tool filtering middleware

Use `dynamic_prompt` to expose a compact trusted checkpoint summary. Use
`wrap_model_call` to show only tools valid for the current state, while keeping
all known tools registered with the agent.

Examples:

- before assembly analysis: assembly workflow tools only;
- after BOM review: sequence generation, not final assessment;
- at sequence review: revise or approve sequence;
- after the report: DFA discussion or automation idea generation;
- after concept review: concept revision or layout planning;
- after layout: minor layout revision or cost planning.

Execution code must still reject an invalid direct call.

### Compiled `StateGraph` workflows

Convert mandatory orchestration progressively rather than rewriting domain
nodes. Good graph boundaries are:

1. assessment preparation through assembly/BOM/sequence review;
2. approved-sequence rendering through interaction, FfA, scoring, and report;
3. automation idea -> parallel detailed step plans -> concept consolidation;
4. layout placement -> deterministic rendering;
5. catalogue matching -> deterministic cost calculation.

Use explicit input/output/state schemas. Nodes return partial state updates.
Use `Send` or explicit fan-out for independent per-part and per-step calls, with
reducers that detect conflicting results instead of silently overwriting them.

### Checkpointing and interrupts

Use a stable, access-controlled thread ID per product session. A checkpointer can
replace manual conversation replay and support pause/resume. Review checkpoints
are candidates for LangGraph `interrupt()` only when replay and idempotency have
been designed carefully.

An interrupted node restarts when resumed. Therefore, external writes and costly
workflow calls must occur after approval or use stable operation IDs and
idempotent publication. Start with per-invocation child graphs; persistent child
state should be an explicit later decision.

### Limits, retries, and error classes

Use separate budgets for model calls, tool calls, graph recursion, and provider
requests. Apply node retry policies only to classified transient failures.
Validation, authorization, domain failures, and programming bugs must not be
blindly retried. Avoid stacking retries at the model, tool, graph, and HTTP
layers without calculating the total attempt count.

### Streaming and tracing

Prefer graph/agent streaming over process-wide stdout interception:

- `updates` for workflow/node completion;
- `messages` for optional token streaming;
- `custom` for CAD rendering and application progress.

Normalize the chosen event format before the Streamlit layer consumes it. Use
LangSmith traces for model/tool trajectories, nested workflow timing, failures,
and evaluation, subject to the product's data policy.

## State and persistence policy

During migration, session manifests and artifacts should remain authoritative.
LangGraph state coordinates execution; it should not become a second competing
business database. A practical split is:

| Concern | Owner |
| --- | --- |
| Messages and current route | Agent checkpointer |
| Node execution state | Workflow graph/checkpointer |
| Published product artifacts and revisions | Existing session files/manifests |
| Feedback audit and catalogue sources | Existing durable stores |
| Authentication and permissions | Invocation context/application |
| Cross-session preferences | Optional LangGraph store or external database |

Use SQLite for a local durable prototype and consider Postgres only when the
deployment requires multi-process durability. An in-memory saver is suitable
for tests and examples, not durable sessions.

## Recommended migration sequence

1. Pin and record compatible `langchain`, `langgraph`, provider, and saver
   versions before changing runtime code.
2. Define typed `AgentState` and application context as projections over the
   existing session truth.
3. Wrap the existing coarse `WorkflowAgentTools` capabilities with `@tool` and
   `ToolRuntime`; keep their domain validation intact.
4. Replace the manual outer loop with `create_agent`, dynamic prompt/tool
   filtering, and model/tool call limits.
5. Move one stable orchestration path at a time into compiled graphs, starting
   with the final FfA pipeline or automation concept pipeline.
6. Add checkpointer-backed continuity and only then consider graph interrupts for
   review checkpoints.
7. Replace ad-hoc progress/stdout capture with normalized graph streaming.
8. Add LangSmith trajectory tests/evaluations after privacy and trace retention
   are decided.

## Non-negotiable tests

- Tool availability matches every checkpoint.
- Direct invalid tool execution is rejected even if middleware fails.
- Every AI tool call receives its corresponding `ToolMessage`.
- Dependent tools cannot execute in the same parallel batch.
- A new source/revision invalidates only the correct downstream artifacts.
- A resumed thread retains intended state and cannot access another session.
- Approval interrupts resume once without duplicating writes or model calls.
- Independent fan-out rejects conflicting result keys.
- Model/tool/graph limits terminate unproductive loops.
- Streaming events preserve stable types consumed by the UI.

## Decisions required before implementation

- Whether to use `create_agent` or a custom outer `StateGraph`; default to
  `create_agent` unless UI routing requires graph-level control.
- Which review checkpoints genuinely need `interrupt()` versus the existing
  explicit user-turn/tool pattern.
- The durable checkpointer backend and thread ownership rules.
- Whether provider parallel tool calls must be disabled globally or only where
  tool dependencies exist.
- Which artifact summaries enter dynamic prompts and which remain available only
  through bounded read tools.
- LangSmith tracing scope, redaction, retention, and cost limits.

The guiding rule is: let the agent choose among meaningful business workflows;
keep ordering, validation, state transitions, and deterministic calculations out
of model discretion.
