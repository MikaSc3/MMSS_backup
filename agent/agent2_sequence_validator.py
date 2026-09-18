# -*- coding: utf-8 -*-
"""
agent2_sequence_validator.py

Agent 2: Sequence Validator with LangGraph

Responsibilities:
- Load generated assembly sequence from Phase 2
- Present sequence to user in clear language
- Get user feedback: approve or request revisions
- If approved → proceed to Phase 4
- If revisions requested → trigger Phase 2f regeneration with remarks
- Optional: Compare with reference PDF via InfoExtractionAgent (future)
"""

import json
import queue
from pathlib import Path
from typing import Dict, Any, List, Annotated, Literal, Optional, Callable
from typing_extensions import TypedDict

from langchain_core.messages import (
    AnyMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from langgraph.graph import StateGraph, START, END
from langchain.tools import tool
import operator


# ============================================================================
# Agent 2 State Definition
# ============================================================================

class Agent2State(TypedDict):
    """State for Agent 2 sequence validator.
    
    Attributes:
        messages: Conversation history (auto-appends via operator.add)
        sequence_json: Current assembly sequence (JSON dict)
        assembly_name: Name of assembly being validated
        system_prompt: System instructions for LLM
        approval_granted: Flag set when user approves sequence
        revision_remarks: User feedback for regeneration (if not approved)
    """
    messages: Annotated[List[AnyMessage], operator.add]
    sequence_json: dict
    assembly_name: str
    system_prompt: str
    approval_granted: bool
    revision_remarks: str


# ============================================================================
# Agent 2 Tools
# ============================================================================

@tool
def approve_sequence() -> str:
    """Approve the current assembly sequence.
    
    Call this tool when:
    - Sequence looks correct and feasible
    - No changes or improvements needed
    - Ready to proceed to Phase 4 (rendering + FFA assessment)
    
    Returns:
        Confirmation that sequence is approved
    """
    return "Sequence approved. Proceeding to Phase 4 (rendering and quality assessment)..."


@tool
def request_revision(remarks: str) -> str:
    """Request sequence revision with specific feedback.
    
    Call this tool when:
    - Sequence has issues that need fixing
    - User provided specific feedback or changes
    - Need to regenerate with updated constraints
    
    Args:
        remarks: Detailed feedback describing what needs to change
                (e.g., "Steps 3 and 4 are in wrong order", "Part X cannot be inserted at step 2")
    
    Returns:
        Confirmation that feedback will be used for regeneration
    """
    return f"Revision requested. Regenerating sequence with feedback: {remarks[:100]}..."


AGENT2_TOOLS = [approve_sequence, request_revision]


# ============================================================================
# Agent 2 (LangGraph-based Sequence Validator)
# ============================================================================

class Agent2:
    """Agent 2: Assembly Sequence Validator
    
    Validates generated assembly sequences and handles user approval/revision loop.
    
    Architecture:
    - StateGraph with llm_node + tool_node
    - LLM presents sequence and asks for feedback
    - LLM calls tools to signal approval or request revision
    - Loop until approval or max turns reached
    """
    
    def __init__(self, llm_model: str = "5.4"):
        """Initialize Agent 2.
        
        Args:
            llm_model: LLM model (default: "5.4")
        """
        self.llm_model = llm_model
        self.llm = None
        self.graph = None
        self.assembly_name = ""
        self.sequence_json = {}
        self._last_messages = []
        self._initialize_llm()
        self._build_graph()
    
    def _initialize_llm(self):
        """Initialize LLM with proper config."""
        from agent.tools import _get_img_describer_llm
        
        try:
            self.llm = _get_img_describer_llm(
                max_completion_tokens=2000,
                llm_model_override=self.llm_model
            )
            print(f"[Agent2] [OK] LLM initialized ({self.llm_model})")
        except Exception as e:
            print(f"[Agent2] ⚠ LLM init failed: {e}")
            self.llm = None
    
    def _build_graph(self):
        """Build LangGraph StateGraph for Agent 2 with tool support.
        
        Graph structure:
            START → llm_node ⇄ tool_node → END
        
        The llm_node:
        - Presents sequence to user
        - Asks for approval or feedback
        - LLM can call approve_sequence or request_revision tools
        
        The tool_node:
        - Sets approval_granted or revision_remarks flags
        - Returns tool execution result
        
        Routing:
        - If LLM called tool → go to tool_node
        - If LLM just replied → END (wait for user input)
        """
        if not self.llm:
            print("[Agent2] ⚠ Cannot build graph: LLM not initialized")
            return
        
        def llm_node(state: Agent2State) -> Dict[str, Any]:
            """Invoke LLM with sequence context and tool access."""
            system_prompt = state.get("system_prompt", "")
            messages = state.get("messages", [])
            
            try:
                # Bind tools to LLM
                llm_with_tools = self.llm.bind_tools(AGENT2_TOOLS)
                
                # Invoke LLM with full conversation history
                response = llm_with_tools.invoke([
                    SystemMessage(content=system_prompt),
                    *messages,
                ])
                
                # Return as new message (auto-appends)
                return {
                    "messages": [AIMessage(
                        content=response.content, 
                        tool_calls=getattr(response, 'tool_calls', None)
                    )]
                }
            
            except Exception as e:
                print(f"[Agent2] ⚠ LLM call failed: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "messages": [AIMessage(content=f"[LLM error: {str(e)[:100]}]")]
                }
        
        def tool_node(state: Agent2State) -> Dict[str, Any]:
            """Execute tool calls from LLM."""
            results = []
            last_message = state["messages"][-1]
            
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                for tool_call in last_message.tool_calls:
                    tool_name = tool_call.get("name") or tool_call.get("type")
                    tool_input = tool_call.get("args") or tool_call.get("input", {})
                    
                    try:
                        # Execute tool
                        if tool_name == "approve_sequence":
                            observation = approve_sequence.invoke({})
                            results.append({
                                "messages": [
                                    ToolMessage(
                                        content=observation,
                                        tool_call_id=tool_call.get("id", "approve_sequence"),
                                        name="approve_sequence"
                                    )
                                ],
                                "approval_granted": True,
                                "revision_remarks": ""
                            })
                        
                        elif tool_name == "request_revision":
                            remarks = tool_input.get("remarks", "")
                            observation = request_revision.invoke({"remarks": remarks})
                            results.append({
                                "messages": [
                                    ToolMessage(
                                        content=observation,
                                        tool_call_id=tool_call.get("id", "request_revision"),
                                        name="request_revision"
                                    )
                                ],
                                "approval_granted": False,
                                "revision_remarks": remarks
                            })
                        
                        else:
                            observation = f"Unknown tool: {tool_name}"
                            results.append({
                                "messages": [
                                    ToolMessage(
                                        content=observation,
                                        tool_call_id=tool_call.get("id", tool_name)
                                    )
                                ]
                            })
                    
                    except Exception as e:
                        print(f"[Agent2] ⚠ Tool execution failed: {e}")
                        results.append({
                            "messages": [
                                ToolMessage(
                                    content=f"Tool error: {str(e)}",
                                    tool_call_id=tool_call.get("id", "error")
                                )
                            ]
                        })
            
            # Merge results
            merged = {
                "messages": [],
                "approval_granted": any(r.get("approval_granted", False) for r in results),
                "revision_remarks": next((r.get("revision_remarks", "") for r in results if r.get("revision_remarks")), "")
            }
            for result in results:
                merged["messages"].extend(result.get("messages", []))
            
            return merged if merged["messages"] else {}
        
        def should_continue(state: Agent2State) -> Literal["tools", END]:
            """Route based on whether LLM called a tool."""
            last_message = state["messages"][-1]
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                return "tools"
            return END
        
        # Build graph
        graph_builder = StateGraph(Agent2State)
        graph_builder.add_node("llm", llm_node)
        graph_builder.add_node("tools", tool_node)
        graph_builder.add_edge(START, "llm")
        graph_builder.add_conditional_edges("llm", should_continue, {
            "tools": "tools",
            END: END
        })
        graph_builder.add_edge("tools", "llm")  # Loop back after tool execution
        
        self.graph = graph_builder.compile()
        print("[Agent2] [OK] StateGraph built with tool support")
    
    def load_sequence(self, sequence_json: dict, assembly_name: str) -> None:
        """Load sequence to validate.
        
        Args:
            sequence_json: Assembly sequence (dict or JSON)
            assembly_name: Name of assembly
        """
        self.sequence_json = sequence_json if isinstance(sequence_json, dict) else json.loads(sequence_json)
        self.assembly_name = assembly_name
        print(f"[Agent2] [OK] Loaded sequence for: {assembly_name}")
    
    def _format_sequence_for_display(self) -> str:
        """Format sequence in clear, readable language for presentation."""
        if not self.sequence_json:
            return "No sequence loaded"
        
        sequence = self.sequence_json
        
        # Extract steps if in standard format
        steps = sequence.get("steps", sequence.get("assembly_sequence", []))
        
        if not steps:
            return json.dumps(sequence, indent=2)
        
        formatted = "ASSEMBLY SEQUENCE:\n\n"
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                step_desc = step.get("description", step.get("step", str(step)))
                part = step.get("part", "")
                action = step.get("action", "assemble")
                formatted += f"Step {i}: {action.upper()} '{part}' - {step_desc}\n"
            else:
                formatted += f"Step {i}: {step}\n"
        
        return formatted
    
    def run(
        self,
        system_prompt: str,
        sequence_json: dict,
        assembly_name: str,
        max_turns: int = 10,
        input_queue = None,
        ui_callback = None
    ) -> Dict[str, Any]:
        """Run sequence validation loop.
        
        Flow:
        1. Load sequence
        2. Present to user (agent explains sequence)
        3. Get feedback (approve or revise)
        4. If approve → approval_granted=True, return
        5. If revise → revision_remarks set, return
        6. Loop until approval or max_turns
        
        Args:
            system_prompt: System instructions
            sequence_json: Sequence to validate
            assembly_name: Assembly name
            max_turns: Max conversation turns (default: 10)
        
        Returns:
            Dict with approval_granted and revision_remarks
        """
        if not self.graph:
            print("[Agent2] ⚠ Graph not initialized")
            return {"approval_granted": False, "revision_remarks": ""}
        
        self.load_sequence(sequence_json, assembly_name)
        
        # Build initial prompt
        sequence_display = self._format_sequence_for_display()
        initial_prompt = f"""Please validate the following assembly sequence for: **{assembly_name}**

{sequence_display}

Review this sequence carefully. Check for:
1. Correct part ordering
2. Assembly feasibility
3. Dependency constraints
4. Any potential issues

If the sequence looks correct, call approve_sequence() tool.
If you see issues or need changes, call request_revision() tool with specific feedback."""
        
        state: Agent2State = {
            "messages": [HumanMessage(content=initial_prompt)],
            "sequence_json": self.sequence_json,
            "assembly_name": assembly_name,
            "system_prompt": system_prompt,
            "approval_granted": False,
            "revision_remarks": "",
        }
        
        print(f"\n{'='*80}")
        print(f"AGENT 2: SEQUENCE VALIDATOR")
        print(f"{'='*80}\n")
        
        if ui_callback:
            ui_callback("message", role="system", content="🤖 Agent 2: Sequence Validator starting...")
        
        # Initial turn: present sequence
        result = self.graph.invoke(state)
        state = result
        
        # Display agent response
        initial_response = state["messages"][-1].content
        print(initial_response)
        
        if ui_callback:
            ui_callback("message", role="agent", content=initial_response)
        
        # Show instructions
        print(f"\n{'─'*80}")
        print(f"[Agent 2] You can provide feedback or ask questions about the sequence.")
        print(f"{'─'*80}\n")
        
        # Auto-mode check: if no input_queue, auto-approve
        if input_queue is None:
            print(f"[Agent 2] Running in auto-approve mode (no user input queue)")
            state["approval_granted"] = True
        
        # Multi-turn loop
        turn = 0
        while not state.get("approval_granted", False) and turn < max_turns:
            turn += 1
            
            print(f"\n{'-'*80}")
            print(f"Turn {turn}/{max_turns}")
            print(f"{'-'*80}\n")
            
            try:
                # Read from queue if available, otherwise use input()
                if input_queue is not None:
                    if ui_callback:
                        ui_callback(
                            "input_waiting",
                            agent="agent2",
                            prompt="Agent 2 is waiting for your sequence feedback. Approve it, ask a question, or describe corrections.",
                        )
                    user_input = input_queue.get(timeout=60).strip()
                    if ui_callback:
                        ui_callback("input_received", agent="agent2")
                else:
                    user_input = input("You: ").strip()
            except queue.Empty:
                print("[Agent2] No user input (timeout), proceeding with current sequence")
                if ui_callback:
                    ui_callback("status", content="Agent 2 timed out waiting for input; proceeding with the current sequence.")
                state["approval_granted"] = True
                break
            except EOFError:
                print("[Agent2] No input (EOF)")
                break
            
            if user_input == "":
                continue
            
            # Add user message
            state["messages"].append(HumanMessage(content=user_input))
            
            if ui_callback:
                ui_callback("message", role="user", content=user_input)
            
            print(f"\nAgent: Thinking...\n")
            
            if ui_callback:
                ui_callback("status", content="⏳ Agent 2: Processing your feedback...")
            
            # Invoke graph
            result = self.graph.invoke(state)
            state = result
            
            # Check if approved
            if state.get("approval_granted", False):
                print(f"\n[Agent2] Sequence approved!")
                if ui_callback:
                    ui_callback("message", role="system", content="✓ Sequence approved by Agent 2")
                break
            
            # Check if revisions requested
            if state.get("revision_remarks"):
                print(f"\n[Agent2] Revisions requested: {state['revision_remarks'][:100]}...")
                if ui_callback:
                    ui_callback("message", role="system", content=f"⚠️ Revisions needed: {state['revision_remarks']}")
                break
            
            # Display response
            if state["messages"]:
                last_msg = state["messages"][-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    print(last_msg.content)
                    if ui_callback:
                        ui_callback("message", role="agent", content=last_msg.content)
        
        # Store messages
        self._last_messages = state["messages"]
        
        print(f"\n{'='*80}")
        print(f"[Agent2] Validation complete")
        print(f"{'='*80}\n")
        
        return {
            "assembly_name": assembly_name,
            "approval_granted": state.get("approval_granted", False),
            "revision_remarks": state.get("revision_remarks", ""),
            "messages": state["messages"],
            "status": "complete",
        }
    
    def save_conversation(self, filepath: Path) -> None:
        """Save validation conversation to text file.
        
        Args:
            filepath: Where to save
        """
        try:
            messages = self._last_messages
            
            if not messages:
                print(f"[Agent2] ⚠ No messages to save")
                return
            
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            conversation_text = f"""AGENT 2: SEQUENCE VALIDATOR CONVERSATION
{'='*80}

Assembly: {self.assembly_name}
Approval Granted: {messages[-1].get("approval_granted", False) if isinstance(messages[-1], dict) else "Unknown"}

{'='*80}
VALIDATION HISTORY:
{'='*80}

"""
            
            for i, msg in enumerate(messages):
                if hasattr(msg, 'type'):
                    msg_type = msg.type
                    msg_content = msg.content
                else:
                    msg_type = msg.get("role", "unknown")
                    msg_content = msg.get("content", "")
                
                if i == 0:
                    conversation_text += f"\n[Sequence Loaded & Presented]\n"
                elif msg_type in ["ai", "assistant"]:
                    conversation_text += f"\n{'-'*80}\nAgent Response:\n{'-'*80}\n{msg_content}\n"
                elif msg_type in ["human", "user"]:
                    conversation_text += f"\n{'-'*80}\nUser Feedback:\n{'-'*80}\n{msg_content}\n"
            
            conversation_text += f"\n{'='*80}\nValidation Complete\n"
            
            filepath.write_text(conversation_text, encoding="utf-8")
            print(f"[Agent2] [OK] Saved conversation to {filepath}")
            
        except Exception as e:
            print(f"[Agent2] ⚠ Failed to save conversation: {e}")
            import traceback
            traceback.print_exc()
