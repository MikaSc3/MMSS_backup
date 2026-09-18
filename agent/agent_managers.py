# -*- coding: utf-8 -*-
"""
agent_managers.py

LangGraph-based agent managers for workflow orchestration.

Each agent:
- Uses StateGraph for state management
- Maintains conversation history with proper Message types
- Supports multi-turn LLM interaction
- Extensible with tools via LangGraph patterns
"""

import json
import os
import queue
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Annotated, Literal, Callable
from typing_extensions import TypedDict

from langchain_core.messages import (
    AnyMessage, BaseMessage, HumanMessage, 
    AIMessage, SystemMessage, ToolMessage
)
from langgraph.graph import StateGraph, START, END
import operator


# ============================================================================
# Agent 1 State Definition (LangGraph)
# ============================================================================

class Agent1State(TypedDict):
    """State for Agent 1 assembly analyst.
    
    Attributes:
        messages: Conversation history (auto-appends via operator.add)
        assembly_data: Loaded assembly overview + BOM
        assembly_name: Name of the assembly being analyzed
        system_prompt: System instructions for LLM
        continue_requested: Flag set when agent decides to proceed to Phase 2b
    """
    messages: Annotated[List[AnyMessage], operator.add]
    assembly_data: dict
    assembly_name: str
    system_prompt: str
    continue_requested: bool


# ============================================================================
# Agent 1 Tools
# ============================================================================

from langchain.tools import tool

@tool
def continue_process() -> str:
    """Signal that assembly analysis is complete and ready to proceed to Phase 2b.
    
    Call this tool when:
    - You have analyzed the assembly in sufficient detail
    - User feedback has been incorporated
    - You are satisfied with the analysis
    
    Returns:
        Confirmation message that workflow will proceed to Phase 2b
    """
    return "Assembly analysis complete. Proceeding to Phase 2b (sequence generation)..."


AGENT1_TOOLS = [continue_process]


# ============================================================================
# Agent 1 (LangGraph-based)
# ============================================================================

class Agent1:
    """Agent 1: Assembly Analyst using LangGraph.
    
    Uses StateGraph for proper state management and message handling.
    
    Architecture:
    - Loads enriched assembly data (Overview_Enriched.json + BOM.json)
    - Builds StateGraph with llm_node
    - Runs multi-turn conversation (20 turns max)
    - Saves full conversation to text file
    
    Features:
    - Auto-appending messages via Annotated[list, operator.add]
    - Proper LangChain message types (HumanMessage, AIMessage)
    - Extensible for tools (add tool_node + conditional_edges later)
    - Full conversation context at each turn (LLM sees entire history)
    """
    
    def __init__(self, llm_model: str = "5.4"):
        """Initialize Agent 1.
        
        Args:
            llm_model: LLM model to use (default: "5.4", options: "4o", "4.1", "5.4")
        """
        self.llm_model = llm_model
        self.llm = None
        self.graph = None
        self.assembly_data = {}
        self.assembly_name = ""
        self._last_messages = []  # Store messages from last run
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
            print(f"[Agent1] [OK] LLM initialized ({self.llm_model})")
        except Exception as e:
            print(f"[Agent1] ⚠ LLM init failed: {e}")
            self.llm = None
    
    def _build_graph(self):
        """Build LangGraph StateGraph for Agent 1 with tool support.
        
        Graph structure:
            START → llm_node ⇄ tool_node → END
        
        The llm_node:
        - Takes current state (messages + context)
        - Invokes LLM with full conversation history + tools
        - LLM can call continue_process tool when ready
        
        The tool_node:
        - Executes continue_process if LLM called it
        - Sets continue_requested flag
        - Returns tool execution result
        
        Routing:
        - If LLM called a tool → go to tool_node
        - If LLM just replied → END (wait for user input)
        """
        if not self.llm:
            print("[Agent1] ⚠ Cannot build graph: LLM not initialized")
            return
        
        # Define the LLM node with tools
        def llm_node(state: Agent1State) -> Dict[str, Any]:
            """Invoke LLM with full conversation context and tool access.
            
            The LLM can:
            - Reply to user (normal response)
            - Call continue_process() to signal completion
            
            Returns new message which gets appended to state["messages"]
            """
            system_prompt = state.get("system_prompt", "")
            messages = state.get("messages", [])
            
            try:
                # Bind tools to LLM
                llm_with_tools = self.llm.bind_tools(AGENT1_TOOLS)
                
                # Invoke LLM with system prompt + full message history
                response = llm_with_tools.invoke([
                    SystemMessage(content=system_prompt),
                    *messages,
                ])
                
                # Return as new message (auto-appends via operator.add)
                return {
                    "messages": [AIMessage(content=response.content, tool_calls=getattr(response, 'tool_calls', None))]
                }
            
            except Exception as e:
                print(f"[Agent1] ⚠ LLM call failed: {e}")
                import traceback
                traceback.print_exc()
                error_msg = f"[LLM error: {str(e)[:100]}]"
                return {
                    "messages": [AIMessage(content=error_msg)]
                }
        
        # Define the tool node
        def tool_node(state: Agent1State) -> Dict[str, Any]:
            """Execute tool calls from LLM."""
            results = []
            last_message = state["messages"][-1]
            
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                for tool_call in last_message.tool_calls:
                    tool_name = tool_call.get("name") or tool_call.get("type")
                    tool_input = tool_call.get("args") or tool_call.get("input", {})
                    
                    try:
                        # Execute the tool
                        if tool_name == "continue_process":
                            observation = continue_process.invoke({})
                            # Set flag to indicate user wants to proceed
                            results.append({
                                "messages": [
                                    ToolMessage(
                                        content=observation,
                                        tool_call_id=tool_call.get("id", "continue_process"),
                                        name="continue_process"
                                    )
                                ],
                                "continue_requested": True
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
                        print(f"[Agent1] ⚠ Tool execution failed: {e}")
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
                "continue_requested": any(r.get("continue_requested", False) for r in results)
            }
            for result in results:
                merged["messages"].extend(result.get("messages", []))
            
            return merged if merged["messages"] else {"continue_requested": False}
        
        # Define routing logic
        def should_continue(state: Agent1State) -> Literal["tools", END]:
            """Route based on whether LLM called a tool."""
            last_message = state["messages"][-1]
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                return "tools"
            return END
        
        # Build graph
        graph_builder = StateGraph(Agent1State)
        graph_builder.add_node("llm", llm_node)
        graph_builder.add_node("tools", tool_node)
        graph_builder.add_edge(START, "llm")
        graph_builder.add_conditional_edges("llm", should_continue, {
            "tools": "tools",
            END: END
        })
        graph_builder.add_edge("tools", "llm")  # Loop back after tool execution
        
        self.graph = graph_builder.compile()
        print("[Agent1] [OK] StateGraph built with tool support")
    
    def load_assembly_data(
        self,
        assembly_name: str,
        session_root: Path,
        workspace_root: Path
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Load enriched overview and BOM for assembly.
        
        Args:
            assembly_name: Name of assembly
            session_root: Session root directory
            workspace_root: Workspace root for fallback search
        
        Returns:
            Tuple of (overview_data, bom_data)
        """
        self.assembly_name = assembly_name
        
        overview_file = None
        bom_file = None
        
        # Search in session root first
        for pattern in [
            session_root / f"assembly_{assembly_name}_Overview_Enriched.json",
            session_root / f"{assembly_name}_BOM.json",  # Stepparser output
            session_root / f"preprocessing/stepparser/{assembly_name}/assembly_{assembly_name}/{assembly_name}_BOM.json",
        ]:
            if pattern.exists():
                if "Overview" in pattern.name:
                    overview_file = pattern
                elif "BOM" in pattern.name:
                    bom_file = pattern
        
        # Fallback: search in data/processed & preprocessing
        if not overview_file or not bom_file:
            base_processed = workspace_root / "data" / "processed"
            base_preprocessing = session_root / "preprocessing" / "stepparser"
            
            # Search processed data first
            if base_processed.exists():
                for root, dirs, files in os.walk(str(base_processed)):
                    for f in files:
                        if f"assembly_{assembly_name}_Overview_Enriched.json" in f and not overview_file:
                            overview_file = Path(root) / f
                        if f"{assembly_name}_BOM.json" in f and not bom_file:
                            bom_file = Path(root) / f
            
            # Search preprocessing (stepparser output)
            if base_preprocessing.exists():
                for root, dirs, files in os.walk(str(base_preprocessing)):
                    for f in files:
                        if f"{assembly_name}_BOM.json" in f and not bom_file:
                            bom_file = Path(root) / f
        
        # Load data
        overview_data = {}
        bom_data = {}
        
        if overview_file and overview_file.exists():
            try:
                with open(overview_file, "r", encoding="utf-8") as f:
                    overview_data = json.load(f)
                print(f"[Agent1] [OK] Loaded: {overview_file.name}")
            except Exception as e:
                print(f"[Agent1] ⚠ Could not load overview: {e}")
        else:
            print(f"[Agent1] ⚠ Overview file not found")
        
        if bom_file and bom_file.exists():
            try:
                with open(bom_file, "r", encoding="utf-8") as f:
                    bom_data = json.load(f)
                print(f"[Agent1] [OK] Loaded: {bom_file.name}")
            except Exception as e:
                print(f"[Agent1] ⚠ Could not load BOM: {e}")
        else:
            print(f"[Agent1] ⚠ BOM file not found (not critical)")
        
        self.assembly_data = {
            "overview": overview_data,
            "bom": bom_data,
            "assembly_name": assembly_name,
        }
        
        return overview_data, bom_data
    
    def _build_context_prompt(self) -> str:
        """Build assembly context for LLM."""
        assembly_name = self.assembly_data.get("assembly_name", "unknown")
        overview = self.assembly_data.get("overview", {})
        bom = self.assembly_data.get("bom", {})
        
        context = f"""ASSEMBLY: {assembly_name}

OVERVIEW:
{json.dumps(overview, indent=2)[:2000]}

BOM (Parts):
{json.dumps(bom, indent=2)[:1000]}"""
        
        return context
    
    def run(
        self,
        system_prompt: str,
        max_turns: int = 20,
        input_queue: Optional[queue.Queue] = None,
        ui_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Run multi-turn assembly analysis conversation using StateGraph with tools.
        
        Flow:
        1. Initialize state with assembly context
        2. Create initial prompt and invoke graph
        3. Loop through turns:
           - Send AI response to UI via callback
           - If LLM calls continue_process → break loop
           - Otherwise wait for user input from input_queue
           - Append HumanMessage to state
           - Invoke graph (llm_node sees full history + tools)
        4. Agent decides when ready via continue_process tool
        
        Agent Control:
        - Agent can call continue_process() tool when analysis is complete
        - This sets continue_requested flag and exits conversation loop
        - No max_turns limit applies once tool is called
        
        Args:
            system_prompt: System prompt from library
            max_turns: Maximum conversation turns (default: 20)
            input_queue: Optional queue.Queue for reading user input (if None, skips multi-turn)
            ui_callback: Optional callback(event: dict) for UI updates
        
        Returns:
            Dict with conversation summary (Phase 2b triggers automatically)
        """
        if not self.graph:
            print("[Agent1] ⚠ Graph not initialized, cannot run")
            return {"status": "error"}
        
        # Build initial state
        context = self._build_context_prompt()
        initial_prompt = f"""{context}

---

Please describe this assembly in exactly 3 sentences.
Then clearly state: "Function: [assembly function]"

You have access to a 'continue_process' tool. Call this tool when you've gathered enough information and are ready to proceed to Phase 2b (sequence generation)."""
        
        state: Agent1State = {
            "messages": [HumanMessage(content=initial_prompt)],
            "assembly_data": self.assembly_data,
            "assembly_name": self.assembly_name,
            "system_prompt": system_prompt,
            "continue_requested": False,
        }
        
        self._emit_ui("status", "→ Agent 1: Initial analysis...", ui_callback)
        
        # Initial turn: invoke graph with initial prompt
        result = self.graph.invoke(state)
        state = result  # Update state with LLM response
        
        # Extract and display initial response
        initial_response = state["messages"][-1].content
        self._emit_ui("message", initial_response, "agent1", ui_callback)
        
        # If no input_queue provided, auto-proceed (UI-less mode)
        if not input_queue:
            self._emit_ui("status", "✓ Agent 1 complete (auto-mode, no user interaction)", ui_callback)
            self._last_messages = state["messages"]
            return {
                "assembly_name": self.assembly_name,
                "messages": state["messages"],
                "status": "complete",
            }
        
        # Multi-turn conversation loop with user input from queue
        turn = 0
        while not state.get("continue_requested", False) and turn < max_turns:
            turn += 1
            
            try:
                # Wait for user input from queue (blocking)
                # Timeout = 60s to prevent infinite hang
                if ui_callback:
                    ui_callback(
                        "input_waiting",
                        agent="agent1",
                        prompt="Agent 1 is waiting for assembly feedback. Ask a question, add constraints, or leave it until timeout to proceed.",
                    )
                user_input = input_queue.get(timeout=60).strip()
                if ui_callback:
                    ui_callback("input_received", agent="agent1")
            
            except queue.Empty:
                self._emit_ui("status", "[Agent1] No user input (timeout), ending conversation", ui_callback)
                break
            except Exception as e:
                self._emit_ui("status", f"[Agent1] Error reading input: {e}", ui_callback)
                break
            
            if user_input == "":
                # Empty input, just continue listening
                continue
            
            # Emit user message to UI
            self._emit_ui("message", user_input, "user", ui_callback)
            
            # Add user message to state
            state["messages"].append(HumanMessage(content=user_input))
            
            self._emit_ui("status", "→ Agent 1: Thinking...", ui_callback)
            
            # Invoke graph (llm_node will see full message history + tools)
            result = self.graph.invoke(state)
            state = result  # Update state with new messages + potentially continue_requested
            
            # Check if agent called continue_process
            if state.get("continue_requested", False):
                self._emit_ui("status", "✓ Agent 1 ready to proceed", ui_callback)
                break
            
            # Extract and display LLM response (if not a tool call)
            if state["messages"]:
                last_msg = state["messages"][-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    self._emit_ui("message", last_msg.content, "agent1", ui_callback)
        
        self._emit_ui("status", "✓ Agent 1 conversation complete", ui_callback)
        
        # Store messages for save_conversation
        self._last_messages = state["messages"]
        
        return {
            "assembly_name": self.assembly_name,
            "messages": state["messages"],
            "status": "complete",
        }
    
    def _emit_ui(self, event_type: str, content: str = "", role: str = "system", ui_callback: Optional[Callable] = None):
        """Emit event to UI via callback (or print if no callback).
        
        Args:
            event_type: "message" or "status"
            content: Message content
            role: "system", "agent1", "user" (for message type)
            ui_callback: Optional callback function
        """
        if ui_callback:
            try:
                if event_type == "message":
                    ui_callback(event_type, role=role, content=content)
                else:
                    ui_callback(event_type, content=content)
            except Exception as e:
                print(f"[Agent1] UI callback error: {e}")
        else:
            # Fallback: print to console
            if event_type == "message":
                print(f"[{role.upper()}] {content}")
            else:
                print(f"[Agent1] {content}")
    
    
    def save_conversation(self, filepath: Path) -> None:
        """Save full conversation to text file.
        
        Converts LangChain message objects to readable text format.
        Uses messages stored from last run() call.
        
        Args:
            filepath: Where to save conversation
        """
        try:
            messages = self._last_messages
            
            if not messages:
                print(f"[Agent1] ⚠ No messages to save")
                return
            
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            conversation_text = f"""AGENT 1: ASSEMBLY ANALYST CONVERSATION
{'='*80}

Assembly: {self.assembly_name}

{'='*80}
CONVERSATION HISTORY:
{'='*80}

"""
            
            # Track which message is the initial system analysis
            for i, msg in enumerate(messages):
                # Handle both LangChain Message objects and dicts
                if hasattr(msg, 'type'):  # LangChain message object
                    msg_type = msg.type
                    msg_content = msg.content
                else:  # dict format (older format)
                    msg_type = msg.get("role", "unknown")
                    msg_content = msg.get("content", "")
                
                # Format output
                if msg_type == "human":
                    conversation_text += f"You: {msg_content}\n\n"
                elif msg_type == "ai":
                    conversation_text += f"AI: {msg_content}\n\n"
                elif msg_type == "tool":
                    conversation_text += f"[Tool Result]: {msg_content}\n\n"
            
            # Write file
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(conversation_text)
            
            print(f"[Agent1] [OK] Conversation saved to: {filepath}")
        
        except Exception as e:
            print(f"[Agent1] ⚠ Error saving conversation: {e}")
            import traceback
            traceback.print_exc()


# ============================================================================
# Agent 3 State Definition (LangGraph)
# ============================================================================

class Agent3State(TypedDict):
    """State for Agent 3 FFA Explainer.
    
    Attributes:
        messages: Conversation history (auto-appends via operator.add)
        ffa_assessment: Full FFA assessment data
        assembly_name: Name of the assembly
        sequence_data: Assembly sequence for context
        system_prompt: System instructions for LLM
    """
    messages: Annotated[List[AnyMessage], operator.add]
    ffa_assessment: dict
    ffa_report: dict
    assembly_name: str
    sequence_data: dict
    system_prompt: str


# ============================================================================
# Agent 3 (LangGraph-based FFA Explainer)
# ============================================================================

class Agent3:
    """Agent 3: FFA Explainer using LangGraph.
    
    Presents FFA (Fitness for Automation) assessment results to user.
    Explains:
    - Which processes can be automated
    - Which should not be automated
    - Suggestions for improvement
    
    Architecture:
    - Loads full FFA assessment JSON (not stripped)
    - Builds context from assembly, sequence, interactions
    - Runs multi-turn conversation with user
    - Saves summary to text file
    """
    
    def __init__(self, llm_model: str = "5.4"):
        """Initialize Agent 3.
        
        Args:
            llm_model: LLM model to use (default: "5.4")
        """
        self.llm_model = llm_model
        self.llm = None
        self.graph = None
        self.ffa_assessment = {}
        self.ffa_report = {}
        self.assembly_name = ""
        self._last_messages = []
        self._initialize_llm()
        self._build_graph()
    
    def _initialize_llm(self):
        """Initialize LLM with proper config."""
        from agent.tools import _get_img_describer_llm
        
        try:
            self.llm = _get_img_describer_llm(
                max_completion_tokens=3000,
                llm_model_override=self.llm_model
            )
            print(f"[Agent3] [OK] LLM initialized ({self.llm_model})")
        except Exception as e:
            print(f"[Agent3] ⚠ LLM init failed: {e}")
            self.llm = None
    
    def _build_graph(self):
        """Build LangGraph StateGraph for Agent 3."""
        if not self.llm:
            print("[Agent3] ⚠ Cannot build graph: LLM not initialized")
            return
        
        def llm_node(state: Agent3State) -> Dict[str, Any]:
            """Invoke LLM with FFA assessment context."""
            system_prompt = state.get("system_prompt", "")
            messages = state.get("messages", [])
            
            try:
                # Don't bind tools for Agent 3 (simpler conversation)
                response = self.llm.invoke([
                    SystemMessage(content=system_prompt),
                    *messages,
                ])
                
                return {
                    "messages": [AIMessage(content=response.content)]
                }
            
            except Exception as e:
                print(f"[Agent3] ⚠ LLM call failed: {e}")
                import traceback
                traceback.print_exc()
                error_msg = f"[LLM error: {str(e)[:100]}]"
                return {
                    "messages": [AIMessage(content=error_msg)]
                }
        
        def should_continue(state: Agent3State):
            """Agent 3 always proceeds (no early termination tools)."""
            return END
        
        # Build graph
        graph_builder = StateGraph(Agent3State)
        graph_builder.add_node("llm", llm_node)
        graph_builder.add_edge(START, "llm")
        graph_builder.add_edge("llm", END)
        
        self.graph = graph_builder.compile()
        print("[Agent3] [OK] StateGraph built for FFA explanation")
    
    def load_ffa_assessment(
        self,
        session_root: Path,
        assembly_name: str
    ) -> Dict[str, Any]:
        """Load FFA assessment from session.
        
        Args:
            session_root: Session root directory
            assembly_name: Name of assembly
        
        Returns:
            FFA assessment data
        """
        self.assembly_name = assembly_name
        
        ffa_file = session_root / "ffa_assessment" / "ffa_assessment.json"
        
        if not ffa_file.exists():
            print(f"[Agent3] ⚠ FFA assessment not found: {ffa_file}")
            return {}
        
        try:
            with open(ffa_file, "r", encoding="utf-8") as f:
                self.ffa_assessment = json.load(f)
            print(f"[Agent3] [OK] FFA assessment loaded: {ffa_file.name}")
            return self.ffa_assessment
        except Exception as e:
            print(f"[Agent3] ⚠ Error loading FFA assessment: {e}")
            return {}
    
    def load_ffa_report(
        self,
        session_root: Path,
        assembly_name: str,
        report_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Load synthesized FFA report from session."""
        self.assembly_name = assembly_name

        report_dir = Path(report_dir) if report_dir is not None else (session_root / "ffa_report")
        candidates = [
            report_dir / f"{assembly_name}_ffa_report.json",
            report_dir / "ffa_report.json",
        ]
        report_file = next((path for path in candidates if path.exists()), None)

        if report_file is None:
            print(f"[Agent3] Warning: FFA report not found in {report_dir}")
            self.ffa_report = {}
            return {}

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                self.ffa_report = json.load(f)
            print(f"[Agent3] [OK] FFA report loaded: {report_file.name}")
            return self.ffa_report
        except Exception as e:
            print(f"[Agent3] Warning: Error loading FFA report: {e}")
            self.ffa_report = {}
            return {}

    def _build_ffa_context_prompt(self, interaction_summary: str = "") -> str:
        """Build FFA context for system prompt injection.
        
        Args:
            interaction_summary: Optional interaction analysis summary
        
        Returns:
            Formatted FFA context for system prompt
        """
        if not self.ffa_assessment:
            return "No FFA assessment available."
        
        context = f"""ASSEMBLY: {self.assembly_name}

FFA ASSESSMENT RESULTS:
{'='*80}

Total Steps Assessed: {self.ffa_assessment.get('total_steps', 0)}
Assessed Steps: {self.ffa_assessment.get('assessed_steps', 0)}

STEP-BY-STEP FFA BREAKDOWN:
"""
        
        for step in self.ffa_assessment.get('step_assessments', []):
            step_id = step.get('step_id', '?')
            description = step.get('step_description', 'Unknown')
            base_part = step.get('base_part_id', '?')
            joining_parts = step.get('joining_part_id', [])
            joining_process = step.get('joining_process', 'Unknown')
            
            context += f"\n--- STEP {step_id}: {description} ---\n"
            context += f"Base Part: {base_part}\n"
            context += f"Joining Parts: {joining_parts}\n"
            context += f"Joining Process: {joining_process}\n"
            
            assessment = step.get('assessment', {})
            if assessment:
                # Separation
                sep = assessment.get('separation', {})
                if sep:
                    context += f"\nSeparation:\n"
                    context += f"  - Nature of Provision: {sep.get('nature_of_provision', '?')}\n"
                    context += f"  - Automatable: {sep.get('automatable', '?')}\n"
                    context += f"  - Reasoning: {sep.get('automatable_reasoning', '')[:200]}...\n"
                
                # Handling
                hdl = assessment.get('handling', {})
                if hdl:
                    context += f"\nHandling:\n"
                    context += f"  - Part Rigidity: {hdl.get('part_rigidity', '?')}\n"
                    context += f"  - Gripping Areas: {hdl.get('gripping_areas', '?')}\n"
                    context += f"  - Orientation Features: {hdl.get('orientation_features', '?')}\n"
                    context += f"  - Surface Sensibility: {hdl.get('surface_sensibility', '?')}\n"
                    context += f"  - Automatable: {hdl.get('automatable', '?')}\n"
                
                # Positioning
                pos = assessment.get('positioning', {})
                if pos:
                    context += f"\nPositioning:\n"
                    context += f"  - Accuracy: {pos.get('accuracy_of_target_position', '?')}\n"
                    context += f"  - Positioning Aids: {pos.get('positioning_aids', '?')}\n"
                    context += f"  - Additional Orientation: {pos.get('additional_orientation_by_rotation', '?')}\n"
                    context += f"  - Automatable: {pos.get('automatable', '?')}\n"
                
                # Joining
                joi = assessment.get('joining', {})
                if joi:
                    context += f"\nJoining:\n"
                    context += f"  - Joining Method: {joi.get('joining_method', '?')}\n"
                    context += f"  - Joining Force: {joi.get('joining_force', '?')}\n"
                    context += f"  - Joining Tolerance: {joi.get('joining_tolerance', '?')}\n"
                    context += f"  - Automatable: {joi.get('automatable', '?')}\n"
            
            context += "\n"
        
        if interaction_summary:
            context += f"\nDETECTED INTERACTIONS:\n{interaction_summary}\n"

        if self.ffa_report:
            context += "\nSYNTHESIZED FFA REPORT:\n"
            context += json.dumps(self.ffa_report, indent=2, ensure_ascii=False)
            context += "\n"
        
        return context
    
    def run(
        self,
        system_prompt: str,
        interaction_summary: str = "",
        pdf_report_path: str = "",
        max_turns: int = 15,
        input_queue = None,
        ui_callback = None
    ) -> Dict[str, Any]:
        """Run FFA presenter with automatic introduction + user questions.
        
        Flow:
        1. Present FFA results summary (Agent-initiated, Turn 0)
        2. Listen for user questions (Turn 1+)
        3. Answer questions based on FFA assessment data
        
        Args:
            system_prompt: System prompt template
            interaction_summary: Optional interaction context
            max_turns: Maximum conversation turns
            input_queue: Optional queue.Queue for user input from UI
            ui_callback: Optional callback for UI updates
        
        Returns:
            Dict with conversation summary
        
        Note:
            Call load_ffa_assessment() before calling run()
        """
        if not self.graph:
            print("[Agent3] ⚠ Graph not initialized, cannot run")
            return {"status": "error"}
        
        if not self.ffa_assessment:
            print("[Agent3] ⚠ No FFA assessment loaded. Call load_ffa_assessment() first.")
            return {"status": "error"}
        
        # Build FFA context for system prompt
        ffa_context = self._build_ffa_context_prompt(interaction_summary)
        
        # Combine system prompt with FFA context
        combined_system_prompt = f"""{system_prompt}

{ffa_context}

---

Available report artifact:
- PDF report path: {pdf_report_path or 'not available'}

Your Task:
1. Introduce the FFA assessment results in clear, non-technical language
2. Briefly summarize automation fitness (high-level overview)
3. Highlight 2-3 key challenges and opportunities
4. Use the synthesized FFA report whenever it provides better wording or higher-level structure
5. Then answer user questions about specific steps, report content, or design improvements"""
        
        state: Agent3State = {
            "messages": [],
            "ffa_assessment": self.ffa_assessment,
            "ffa_report": self.ffa_report,
            "assembly_name": self.assembly_name,
            "sequence_data": {},
            "system_prompt": combined_system_prompt,
        }
        
        print(f"\n{'='*80}")
        print(f"[Agent 3] FFA Assessment Presenter")
        print(f"Assembly: {self.assembly_name}")
        print(f"{'='*80}\n")
        
        if ui_callback:
            ui_callback("message", role="system", content="🤖 Agent 3: FFA Explainer starting...")
        
        # TURN 0: Agent presents FFA results (auto-initiated)
        initial_prompt = "Present the FFA assessment results for this assembly."
        state["messages"].append(HumanMessage(content=initial_prompt))
        
        result = self.graph.invoke(state)
        state = result
        
        # Display initial presentation
        if state["messages"]:
            last_msg = state["messages"][-1]
            if hasattr(last_msg, 'content') and last_msg.content:
                print(f"AI: {last_msg.content}\n")
                if ui_callback:
                    ui_callback("message", role="agent3", content=last_msg.content)
        
        print(f"{'─'*80}")
        print(f"[Agent 3] Ask questions about automation fitness, design changes, or specific steps.")
        print(f"{'─'*80}\n")
        
        # Auto-mode check: if no input_queue, skip further turns
        if input_queue is None:
            print(f"[Agent 3] Running in auto-mode (no user input queue)")
        
        # TURN 1+: Multi-turn conversation (user-driven questions)
        turn = 1
        while turn < max_turns and input_queue is not None:
            try:
                if ui_callback:
                    ui_callback(
                        "input_waiting",
                        agent="agent3",
                        prompt="Agent 3 is waiting for questions about the FFA report. Type done when you are finished.",
                    )
                user_input = input_queue.get(timeout=60).strip()
                if ui_callback:
                    ui_callback("input_received", agent="agent3")
            except queue.Empty:
                if ui_callback:
                    ui_callback(
                        "message",
                        role="system",
                        content="⏸ Agent 3 is waiting for your questions about the FFA report. Type `done` when you are finished.",
                    )
                continue
            except EOFError:
                print("[Agent3] No input (EOF), ending session")
                break
            
            if user_input.lower() in ["exit", "quit", "done", "finished"]:
                print("[Agent3] Session ended")
                if ui_callback:
                    ui_callback("message", role="system", content="✓ FFA explanation session ended")
                break
            
            if user_input == "":
                continue
            
            turn += 1
            
            # Add user message
            state["messages"].append(HumanMessage(content=user_input))
            
            if ui_callback:
                ui_callback("message", role="user", content=user_input)
            
            if ui_callback:
                ui_callback("status", content="⏳ Agent 3: Processing your question...")
            
            # Invoke graph
            result = self.graph.invoke(state)
            state = result
            
            # Display response
            if state["messages"]:
                last_msg = state["messages"][-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    print(f"\nAI: {last_msg.content}\n")
                    if ui_callback:
                        ui_callback("message", role="agent3", content=last_msg.content)
        
        print(f"\n{'='*80}")
        print(f"[Agent3] FFA session complete")
        print(f"{'='*80}\n")
        
        # Store for saving
        self._last_messages = state["messages"]
        
        return {
            "assembly_name": self.assembly_name,
            "messages": state["messages"],
            "status": "complete",
        }
    
    def save_conversation(self, filepath: Path) -> None:
        """Save FFA explanation conversation to text file.
        
        Args:
            filepath: Where to save conversation
        """
        try:
            messages = self._last_messages
            
            if not messages:
                print(f"[Agent3] ⚠ No messages to save")
                return
            
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            conversation_text = f"""AGENT 3: FFA EXPLAINER CONVERSATION
{'='*80}

Assembly: {self.assembly_name}

{'='*80}
FFA EXPLANATION & USER QUESTIONS:
{'='*80}

"""
            
            for msg in messages:
                if hasattr(msg, 'type'):
                    msg_type = msg.type
                    msg_content = msg.content
                else:
                    msg_type = msg.get("role", "unknown")
                    msg_content = msg.get("content", "")
                
                if msg_type == "human":
                    conversation_text += f"You: {msg_content}\n\n"
                elif msg_type == "ai":
                    conversation_text += f"AI: {msg_content}\n\n"
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(conversation_text)
            
            print(f"[Agent3] [OK] Conversation saved to: {filepath}")
        
        except Exception as e:
            print(f"[Agent3] ⚠ Error saving conversation: {e}")
            import traceback
            traceback.print_exc()
            
            # Write file
            filepath.write_text(conversation_text, encoding="utf-8")
            print(f"[Agent1] [OK] Saved conversation to {filepath}")
            
        except Exception as e:
            print(f"[Agent1] ⚠ Failed to save conversation: {e}")
            import traceback
            traceback.print_exc()

