# How to Use LangGraph - Complete Guide

## Overview

LangGraph is a **low-level orchestration framework** for building, managing, and deploying **long-running, stateful agents**. It doesn't abstract prompts or architecture—you have full control.

### Core Benefits
1. **Durable Execution**: Agents persist through failures and resume from where they left off
2. **Human-in-the-Loop**: Inspect and modify agent state at any point
3. **Comprehensive Memory**: Short-term working memory + long-term memory across sessions
4. **Debugging**: Deep visibility with LangSmith trace visualization
5. **Production-Ready Deployment**: Scalable infrastructure for stateful workflows

---

## Core Concepts

### 1. **State** (Persistent Data Structure)
```python
from typing_extensions import TypedDict, Annotated
from langchain.messages import AnyMessage
import operator

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]  # KEY: operator.add appends!
    other_data: str  # Any other data you need
```

**Critical**: `Annotated[list, operator.add]` ensures messages **append** rather than replace.

### 2. **Nodes** (Processing Functions)
Functions that take state, process it, and return updated state:
```python
def my_node(state: MessagesState):
    # Process state
    result = do_something(state)
    return {"key": result}  # Returns dict to be merged into state
```

### 3. **Edges** (Connections)
- **Direct edges**: `graph.add_edge("node_a", "node_b")`
- **Conditional edges**: `graph.add_conditional_edges("node_a", should_continue, ["node_b", END])`

### 4. **StateGraph** (Builder Pattern)
```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(MessagesState)
graph.add_node("my_node", my_node)
graph.add_edge(START, "my_node")
graph.add_edge("my_node", END)
compiled_agent = graph.compile()
```

---

## Workflow Patterns

### Pattern 1: **Prompt Chaining**
Sequential LLM calls where output becomes input to next call.
```
START → LLM_Call_1 → Gate_Check → LLM_Call_2 → LLM_Call_3 → END
                          ↓
                       Improve_Path
```
**Use case**: Translation with verification, multi-step reasoning

### Pattern 2: **Parallelization**
Multiple independent tasks run simultaneously.
```
START → Task_1 → Aggregator → END
     → Task_2 ↗
     → Task_3 ↗
```
**Use case**: Generate multiple outputs (joke, story, poem) in parallel

### Pattern 3: **Routing**
LLM decides which path to take based on input classification.
```
START → Router_LLM → Conditional_Edge → Path_A → END
                                    → Path_B → END
                                    → Path_C → END
```
**Use case**: Customer service routing (pricing/refunds/returns)

### Pattern 4: **Orchestrator-Worker** (Dynamic Task Distribution)
Orchestrator breaks down work, dynamically creates worker instances.
```
START → Orchestrator → Send(worker_1, data_1)
                    → Send(worker_2, data_2) → Synthesizer → END
                    → Send(worker_n, data_n)
```
**Use case**: Unknown number of subtasks (multi-file updates, report generation)

**Key**: Uses `Send()` API for dynamic parallel work.

### Pattern 5: **Evaluator-Optimizer** (Iterative Refinement)
Generate response, evaluate quality, iterate if needed.
```
START → Generator → Evaluator → ✓ Good? → END
                        ↓
                     ✗ Bad + Feedback
                        ↑
        ← ← ← ← ← ← ← ← ←
```
**Use case**: Translation with quality requirements, joke generation

---

## Agent Pattern (Tool-Using Agents)

### Tools Definition
```python
from langchain.tools import tool

@tool
def my_tool(param: str) -> str:
    """Tool description for LLM - this appears in tool schema."""
    return result

tools = [my_tool]
model_with_tools = llm.bind_tools(tools)  # Critical: bind_tools!
```

### Two Core Nodes
```python
def llm_node(state: MessagesState):
    """LLM decides what to do, possibly calling a tool."""
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def tool_node(state: MessagesState):
    """Execute tool calls from LLM."""
    results = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        results.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": results}
```

### Routing Logic
```python
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    if state["messages"][-1].tool_calls:
        return "tool_node"  # Call tools
    return END  # Done
```

### Build Agent
```python
agent_graph = StateGraph(MessagesState)
agent_graph.add_node("llm", llm_node)
agent_graph.add_node("tools", tool_node)
agent_graph.add_edge(START, "llm")
agent_graph.add_conditional_edges("llm", should_continue, ["tools", END])
agent_graph.add_edge("tools", "llm")  # Loop back after tool execution
agent = agent_graph.compile()
```

### Result
The agent **loops**:
1. LLM sees conversation + tools
2. LLM decides to call tool(s) or reply
3. If tools called: execute, add results to messages, loop back to LLM
4. If reply: END

---

## Human-in-the-Loop

LangGraph supports **breakpoints** to pause execution and let humans intervene:
```python
# Add breakpoints before specific nodes
graph.add_node("human_review", always_use_breakpoint(human_review_node))

# Edit state and resume
compiled_graph.invoke(
    state, 
    {"configurable": {"thread_id": "thread_1"}},
    interrupt_before="human_review"
)
```

---

## Persistence & Sessions

Save state to database for resumable conversations:
```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver(conn=sqlite3.connect(":memory:"))
compiled_graph = graph.compile(checkpointer=checkpointer)

# Use thread_id to resume
result = compiled_graph.invoke(
    state,
    {"configurable": {"thread_id": "user_123"}}
)
```

---

## Key Takeaways

| Concept | Purpose |
|---------|---------|
| **State** | Persistent data throughout execution |
| **Nodes** | Processing steps |
| **Edges** | Flow control |
| **Conditional Edge** | Decision-based routing |
| **operator.add** | Append vs replace for lists |
| **bind_tools()** | Give LLM access to tools |
| **Tool Node** | Execute tool calls |
| **Breakpoints** | Human intervention points |
| **Checkpointer** | Session persistence |

---

## Installation
```bash
pip install -U langgraph
```

## Import Pattern
```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from typing_extensions import TypedDict, Annotated
import operator
```
