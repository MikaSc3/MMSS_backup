"""
PM Agent - Process Manager Agent for Interactive Annotation Workflow

Responsibilities:
- Interact with user to gather context
- Call workflow wrapper at appropriate times
- Maintain conversation history and decisions
- Manage session state and checkpointing
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Annotated
from datetime import datetime
import json

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph.message import add_messages
except ImportError:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph.message import add_messages

try:
    from agent.workflow_wrapper import build_interactive_workflow, run_workflow_until
    from agent.prompt_store import load_experiment_settings, get_prompt_template
    from agent.tools import _get_experiment_output_dir
    from agent.utils import wprint as _wprint
except ImportError:
    from workflow_wrapper import build_interactive_workflow, run_workflow_until
    from prompt_store import load_experiment_settings, get_prompt_template
    from tools import _get_experiment_output_dir
    from utils import wprint as _wprint


# ============================================================================
# STATE SCHEMA
# ============================================================================

class PMAgentState(dict):
    """State schema for PM Agent"""
    # Messaging
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Session context
    thread_id: str
    assembly_name: str
    datasource_root: str
    config_file: Optional[str]
    
    # Current workflow phase
    current_phase: Literal["phase_1", "phase_2", "phase_3", "end"]
    next_action: Literal["ask_user", "call_workflow", "reflect", "end"]
    
    # User responses
    assembly_function: str
    sub_assemblies: List[str]
    handling_constraints: List[str]
    sequence_remarks: str
    
    # Workflow state
    workflow_state: Dict[str, Any]
    workflow_nodes_executed: List[str]
    
    # Session management
    session_start_time: str
    last_checkpoint_time: str
    decisions_log: Annotated[List[Dict[str, Any]], lambda x: x]  # Accumulate log


def create_pm_agent_state(
    assembly_name: str,
    datasource_root: str,
    config_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Create initial PM agent state"""
    return {
        "messages": [],
        "thread_id": str(uuid.uuid4()),
        "assembly_name": assembly_name,
        "datasource_root": str(Path(datasource_root).expanduser()),
        "config_file": config_file,
        "current_phase": "phase_1",
        "next_action": "ask_user",
        "assembly_function": "",
        "sub_assemblies": [],
        "handling_constraints": [],
        "sequence_remarks": "",
        "workflow_state": {},
        "workflow_nodes_executed": [],
        "session_start_time": datetime.now().isoformat(),
        "last_checkpoint_time": datetime.now().isoformat(),
        "decisions_log": [],
    }


# ============================================================================
# INFORMATION EXTRACTION FROM WORKFLOW STATE
# ============================================================================

def extract_assembly_info(workflow_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract assembly analysis info from workflow state"""
    return {
        "assembly_description": workflow_state.get("assembly_description", ""),
        "primary_function": workflow_state.get("primary_function", ""),
        "partslist": workflow_state.get("partslist", []),
        "assembly_name_guess": workflow_state.get("assembly_name_guess", ""),
    }


def extract_sequence_info(workflow_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract assembly sequence from workflow state"""
    return {
        "sequence_path": workflow_state.get("assembly_sequence_path", ""),
        "sequence_data": workflow_state.get("assembly_sequence", {}),
        "renderings_path": workflow_state.get("assembly_renderings_path", ""),
    }


# ============================================================================
# PM AGENT NODES
# ============================================================================

def node_initialize(state: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize the PM agent"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_ENDPOINT_4O") or os.getenv("AZURE_ENDPOINT"),
        api_key=os.getenv("API_KEY_GPT_4"),
        api_version="latest",
        deployment_name="gpt-4o",
        temperature=0.0,
    )
    
    # Initial greeting
    greeting = f"Hello! I'm the PM (Process Manager) Agent. I'll guide you through the annotation of the assembly: {state['assembly_name']}\n\nLet's start by analyzing it. I'll ask you some clarifying questions."
    
    state["messages"].append(AIMessage(content=greeting))
    state["next_action"] = "call_workflow"
    
    return state


def node_call_workflow_phase_1(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call workflow wrapper: Phase 1 (Assembly Analysis)"""
    print(f"\n[PM Agent] Starting Phase 1: Assembly Analysis...")
    
    # Build and run workflow
    workflow_app = build_interactive_workflow()
    
    try:
        workflow_state = run_workflow_until(
            workflow_app,
            state["datasource_root"],
            "phase_1_stop",
            state["thread_id"],
            config_file=state.get("config_file"),
        )
        
        state["workflow_state"] = workflow_state
        state["workflow_nodes_executed"] = workflow_state.get("nodes_executed", [])
        state["current_phase"] = "phase_1"
        state["next_action"] = "ask_user"
        
        # Log decision
        state["decisions_log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "call_workflow",
            "phase": "phase_1",
            "nodes": state["workflow_nodes_executed"],
        })
        
        print(f"[PM Agent] Phase 1 complete. {len(state['workflow_nodes_executed'])} nodes executed.")
        
    except Exception as e:
        print(f"[PM Agent] ERROR in Phase 1: {e}")
        state["messages"].append(AIMessage(
            content=f"Sorry, I encountered an error during phase 1: {e}\n\nPlease check your input data and try again."
        ))
        state["next_action"] = "end"
    
    return state


def node_ask_assembly_questions(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ask user clarifying questions about the assembly"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_ENDPOINT_4O") or os.getenv("AZURE_ENDPOINT"),
        api_key=os.getenv("API_KEY_GPT_4"),
        api_version="latest",
        deployment_name="gpt-4o",
        temperature=0.0,
    )
    
    # Load settings (config_file might be in state if provided)
    config_file = state.get("config_file")
    if config_file:
        os.environ["APA_EXPERIMENT_YAML"] = str(Path(config_file).resolve())
    settings = load_experiment_settings()
    assembly_info = extract_assembly_info(state["workflow_state"])
    
    # Get prompts
    system_prompt_id = settings.get("PM_assembly_analyst_system_prompt_id", "PM_AssemblyAnalyst_system_v1")
    user_prompt_id = settings.get("PM_assembly_analyst_human_prompt_id", "PM_AskAssemblyQuestions_v1")
    
    system_prompt = get_prompt_template(system_prompt_id)
    user_prompt_template = get_prompt_template(user_prompt_id)
    
    # Fallback prompts if not found
    if not system_prompt:
        system_prompt = "You are an expert assembly analyst. Help refine the assembly sequence and answer questions about the assembly structure."
    if not user_prompt_template:
        user_prompt_template = "Based on the assembly analysis, please provide feedback on the assembly structure, function, and constraints."
    
    # Format assembly info into prompt
    assembly_info_text = json.dumps(assembly_info, indent=2)
    user_prompt = f"{user_prompt_template}\n\n---\n\nCURRENT ASSEMBLY ANALYSIS:\n{assembly_info_text}"
    
    # Get agent response
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    response = llm.invoke(messages)
    agent_msg = AIMessage(content=response.content)
    state["messages"].append(agent_msg)
    
    # Add placeholder for user response
    print(f"\n[PM Agent] Waiting for user input...\n{response.content}\n")
    
    # Simulate user input for now (in real implementation, this would be interactive)
    # For testing: default responses
    user_response = input("Your response: ").strip()
    if user_response:
        state["messages"].append(HumanMessage(content=user_response))
    
    # Parse and save responses (simplified for now)
    state["assembly_function"] = user_response or settings.get("test_assembly_function", "")
    state["sub_assemblies"] = []
    state["handling_constraints"] = []
    
    # Log decision
    state["decisions_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action": "ask_user",
        "phase": "phase_1",
        "question": "Assembly analysis",
        "response": user_response,
    })
    
    state["current_phase"] = "phase_1_complete"
    state["next_action"] = "call_workflow"
    
    return state


def node_call_workflow_phase_2(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call workflow wrapper: Phase 2 (Initial Sequence Generation)"""
    print(f"\n[PM Agent] Starting Phase 2: Sequence Generation...")
    
    workflow_app = build_interactive_workflow()
    
    try:
        workflow_state = run_workflow_until(
            workflow_app,
            state["datasource_root"],
            "phase_2_stop",
            state["thread_id"],
            config_file=state.get("config_file"),
        )
        
        state["workflow_state"] = workflow_state
        state["workflow_nodes_executed"] = workflow_state.get("nodes_executed", [])
        state["current_phase"] = "phase_2"
        state["next_action"] = "ask_user"
        
        state["decisions_log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "call_workflow",
            "phase": "phase_2",
            "nodes": state["workflow_nodes_executed"],
        })
        
        print(f"[PM Agent] Phase 2 complete. Sequence generated.")
        
    except Exception as e:
        print(f"[PM Agent] ERROR in Phase 2: {e}")
        state["messages"].append(AIMessage(
            content=f"Sorry, I encountered an error during sequence generation: {e}"
        ))
        state["next_action"] = "end"
    
    return state


def node_ask_sequence_corrections(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ask user for sequence corrections/remarks"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_ENDPOINT_4O") or os.getenv("AZURE_ENDPOINT"),
        api_key=os.getenv("API_KEY_GPT_4"),
        api_version="latest",
        deployment_name="gpt-4o",
        temperature=0.0,
    )
    
    # Load settings (config_file might be in state if provided)
    config_file = state.get("config_file")
    if config_file:
        os.environ["APA_EXPERIMENT_YAML"] = str(Path(config_file).resolve())
    settings = load_experiment_settings()
    sequence_info = extract_sequence_info(state["workflow_state"])
    
    # Get prompts
    system_prompt_id = settings.get("PM_sequence_analyst_system_prompt_id", "PM_SequenceAnalyst_system_v1")
    user_prompt_id = settings.get("PM_sequence_analyst_human_prompt_id", "PM_ValidateSequence_v1")
    
    system_prompt = get_prompt_template(system_prompt_id)
    user_prompt_template = get_prompt_template(user_prompt_id)
    
    # Fallback prompts if not found
    if not system_prompt:
        system_prompt = "You are an expert assembly sequence analyst. Review and validate the generated assembly sequence."
    if not user_prompt_template:
        user_prompt_template = "Please review the generated assembly sequence and provide feedback on feasibility and completeness."
    
    # Format sequence info into prompt
    sequence_info_text = json.dumps(sequence_info, indent=2, default=str)
    user_prompt = f"{user_prompt_template}\n\n---\n\nGENERATED SEQUENCE:\n{sequence_info_text}"
    
    # Get agent response
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    
    response = llm.invoke(messages)
    agent_msg = AIMessage(content=response.content)
    state["messages"].append(agent_msg)
    
    # Get user remarks
    print(f"\n[PM Agent] Please review the sequence and provide any corrections:\n{response.content}\n")
    
    user_remarks = input("Your remarks (or press Enter to accept): ").strip()
    if user_remarks:
        state["messages"].append(HumanMessage(content=user_remarks))
        state["sequence_remarks"] = user_remarks
    
    # Log decision
    state["decisions_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action": "ask_user",
        "phase": "phase_2",
        "question": "Sequence corrections",
        "response": user_remarks,
    })
    
    state["current_phase"] = "phase_2_complete"
    state["next_action"] = "call_workflow"
    
    return state


def node_call_workflow_phase_3(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call workflow wrapper: Phase 3 (Full Analysis with User Remarks)"""
    print(f"\n[PM Agent] Starting Phase 3: Full Analysis (with your feedback)...")
    
    workflow_app = build_interactive_workflow()
    
    try:
        # Pass user remarks to workflow
        workflow_state = run_workflow_until(
            workflow_app,
            state["datasource_root"],
            "phase_3_stop",
            state["thread_id"],
            remarks=state.get("sequence_remarks", ""),
            config_file=state.get("config_file"),
        )
        
        state["workflow_state"] = workflow_state
        state["workflow_nodes_executed"] = workflow_state.get("nodes_executed", [])
        state["current_phase"] = "phase_3"
        state["next_action"] = "call_workflow"
        
        state["decisions_log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "call_workflow",
            "phase": "phase_3",
            "nodes": state["workflow_nodes_executed"],
            "remarks_included": len(state.get("sequence_remarks", "")) > 0,
        })
        
        print(f"[PM Agent] Phase 3 complete. Final analysis running...")
        
    except Exception as e:
        print(f"[PM Agent] ERROR in Phase 3: {e}")
        state["messages"].append(AIMessage(
            content=f"Sorry, I encountered an error during final analysis: {e}"
        ))
        state["next_action"] = "end"
    
    return state


def node_call_workflow_final(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call workflow wrapper: Final (Interaction Analysis + FFA Assessment)"""
    print(f"\n[PM Agent] Running final analysis (Interaction + FFA Assessment)...")
    
    workflow_app = build_interactive_workflow()
    
    try:
        workflow_state = run_workflow_until(
            workflow_app,
            state["datasource_root"],
            "end",
            state["thread_id"],
            config_file=state.get("config_file"),
        )
        
        state["workflow_state"] = workflow_state
        state["workflow_nodes_executed"] = workflow_state.get("nodes_executed", [])
        state["current_phase"] = "end"
        state["next_action"] = "reflect"
        
        state["decisions_log"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "call_workflow",
            "phase": "end",
            "nodes": state["workflow_nodes_executed"],
        })
        
        print(f"[PM Agent] All analyses complete!")
        
    except Exception as e:
        print(f"[PM Agent] ERROR in final phase: {e}")
        state["next_action"] = "end"
    
    return state


def node_reflect_and_summarize(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reflect on the session and summarize findings"""
    summary = f"""
📋 SESSION SUMMARY
==================

Assembly: {state['assembly_name']}
Session ID: {state['thread_id']}
Duration: {datetime.now().isoformat()} (started at {state['session_start_time']})

Workflow Phases Completed:
✓ Phase 1: Assembly Analysis
✓ Phase 2: Sequence Generation & User Review
✓ Phase 3: Final Analysis (Interaction + FFA)

Total Nodes Executed: {len(state['workflow_nodes_executed'])}
Nodes: {', '.join(state['workflow_nodes_executed'])}

User Responses:
- Assembly Function: {state.get('assembly_function', 'N/A')}
- Sub-assemblies: {', '.join(state.get('sub_assemblies', [])) or 'N/A'}
- Sequence Remarks: {state.get('sequence_remarks', 'No changes requested') }

Output Locations:
- Assembly metadata: data/session/{state['assembly_name']}/output/
- Assembly sequence: assembly_sequence.json
- FFA Assessment: ffa_assessment/ffa_assessment.json
- Interaction Analysis: interaction_analysis.json

Decisions Made: {len(state['decisions_log'])}
"""
    
    state["messages"].append(AIMessage(content=summary))
    print(summary)
    
    state["next_action"] = "end"
    state["last_checkpoint_time"] = datetime.now().isoformat()
    
    return state


# ============================================================================
# AGENT BUILDER
# ============================================================================

def build_pm_agent():
    """Build the PM Agent using LangGraph"""
    
    graph = StateGraph(dict)
    
    # Add nodes
    graph.add_node("initialize", node_initialize)
    graph.add_node("call_workflow_phase_1", node_call_workflow_phase_1)
    graph.add_node("ask_assembly_questions", node_ask_assembly_questions)
    graph.add_node("call_workflow_phase_2", node_call_workflow_phase_2)
    graph.add_node("ask_sequence_corrections", node_ask_sequence_corrections)
    graph.add_node("call_workflow_phase_3", node_call_workflow_phase_3)
    graph.add_node("call_workflow_final", node_call_workflow_final)
    graph.add_node("reflect_and_summarize", node_reflect_and_summarize)
    
    # Define routing
    def route_from_phase_1(state):
        return "ask_assembly_questions"
    
    def route_from_questions(state):
        return "call_workflow_phase_2"
    
    def route_from_phase_2(state):
        return "ask_sequence_corrections"
    
    def route_from_remarks(state):
        return "call_workflow_phase_3"
    
    def route_from_phase_3(state):
        return "call_workflow_final"
    
    def route_from_final(state):
        return "reflect_and_summarize"
    
    def route_end(state):
        if state.get("next_action") == "end":
            return END
        return "reflect_and_summarize"
    
    # Add edges
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "call_workflow_phase_1")
    graph.add_edge("call_workflow_phase_1", "ask_assembly_questions")
    graph.add_edge("ask_assembly_questions", "call_workflow_phase_2")
    graph.add_edge("call_workflow_phase_2", "ask_sequence_corrections")
    graph.add_edge("ask_sequence_corrections", "call_workflow_phase_3")
    graph.add_edge("call_workflow_phase_3", "call_workflow_final")
    graph.add_edge("call_workflow_final", "reflect_and_summarize")
    graph.add_conditional_edges("reflect_and_summarize", route_end)
    
    # Compile with in-memory checkpointing
    checkpointer = InMemorySaver()
    
    return graph.compile(checkpointer=checkpointer)
