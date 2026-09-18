"""Terminal-first orchestrator for the agent-driven app workflow v3."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


from agent.app_workflow_v3_tools import (  # noqa: E402
    analyse_assembly_tool,
    analyse_monoparts_and_merge_tool,
    generate_or_revise_sequence_tool,
    ingest_user_documents_tool,
    run_final_assessment_pipeline_tool,
    run_stepparser_and_resolve_paths,
    setup_session_v3,
)
from agent.content_agent import ContentAgent, ContentUnderstanding, extract_assembly_summary, extract_sequence_summary  # noqa: E402
from scripts.app_workflow_v2 import discover_assembly, load_config, load_prompt_library  # noqa: E402


# ============================================================================
# TERMINAL CONFIGURATION INJECTION SLOTS
#
# Do not edit these here. The root launcher `7_run_app_workflow_AGENT_terminal.py`
# injects the concrete values before calling main().
# ============================================================================

MASTER_STEP_INPUT_FOLDER: Optional[str] = None
STEPPARSER_OUTPUT_FOLDER: Optional[str] = None
LLM_OUTPUT_FOLDER: Optional[str] = None
TEXTBASED_ADDITIONAL_DATA: Optional[str] = None
EXPERIMENT_CONFIG_FOLDER: Optional[str] = None
EXPERIMENT_CONFIG_NAME: Optional[str] = None
TERMINAL_INTERACTIVE: Optional[bool] = None

def run_app_workflow_v3_terminal(
    *,
    config_path: Optional[Path] = None,
    assembly_name: Optional[str] = None,
    step_file: Optional[Path] = None,
    additional_files: Optional[list[Path]] = None,
    user_notes: str = "",
    session_root: Optional[Path] = None,
    auto: bool = False,
    ui_callback: Any = None,
    input_queue: Any = None,
    prompt_for_setup_inputs: bool = True,
    initial_agent_message: str = "",
) -> Dict[str, Any]:
    """Run V3 in a terminal or queue-driven interactive flow."""
    print("\n" + "=" * 80)
    print(
        "APP WORKFLOW V3: CONTENT AGENT TERMINAL"
        if ui_callback is None
        else "APP WORKFLOW V3: CONTENT AGENT STREAMLIT"
    )
    print("=" * 80)

    config = load_config(config_path)
    prompt_library = load_prompt_library("prompts.yaml")

    if step_file and not assembly_name:
        assembly_name = Path(step_file).stem
    if not assembly_name:
        if auto:
            assembly_name = discover_assembly()
        elif prompt_for_setup_inputs:
            discovered = _try_discover_assembly()
            prompt = f"Assembly name [{discovered or 'required'}]: "
            assembly_name = input(prompt).strip() or discovered
            if not assembly_name:
                raise ValueError("Assembly name is required")
        else:
            raise ValueError("assembly_name is required for non-terminal setup")

    if not step_file and not auto and prompt_for_setup_inputs:
        raw_step = input("STEP file path [use data/input/{name}.STEP]: ".format(name=assembly_name)).strip()
        step_file = Path(raw_step) if raw_step else None

    if not additional_files and not auto and prompt_for_setup_inputs:
        raw_files = input("Additional document paths, separated by semicolon [optional]: ").strip()
        additional_files = [Path(p.strip().strip('"')) for p in raw_files.split(";") if p.strip()]
    elif additional_files is None:
        additional_files = []

    state = setup_session_v3(
        assembly_name=assembly_name,
        step_file=step_file,
        session_root=session_root,
        config=config,
        prompt_library=prompt_library,
    )
    _apply_parallel_settings(state, config)
    _emit_ui(
        ui_callback,
        "session_created",
        session_root=str(state["session_root"]),
        assembly_name=state["assembly_name"],
    )

    print(f"\n[SETUP] Session: {state['session_root']}")
    print(
        "[SETUP] Monopart analysis: "
        f"{'parallel' if state.get('parallel') else 'sequential'} "
        f"(max_workers={state.get('max_workers')})"
    )
    if auto:
        print("[PREPROCESS] Running STEP preprocessing and path resolution...")
        state = run_stepparser_and_resolve_paths(state)
        print("[PREPROCESS] Complete")
        print("\n[CONTENT] Ingesting additional documents...")
        state = ingest_user_documents_tool(state, additional_files)
        state["input_preprocessing_complete"] = True

    agent = ContentAgent(
        session_root=state["session_root"],
        assembly_name=state["assembly_name"],
        max_context_chars=int((config.get("content_agent") or {}).get("max_context_chars", 12000)),
    )
    state = _run_agent_controlled_workflow(
        state=state,
        agent=agent,
        user_notes=user_notes,
        auto=auto,
        ui_callback=ui_callback,
        input_queue=input_queue,
        additional_files=additional_files,
        initial_agent_message=initial_agent_message,
    )

    _print_final_outputs(state)
    return state


def _run_agent_controlled_workflow(
    *,
    state: Dict[str, Any],
    agent: ContentAgent,
    user_notes: str,
    auto: bool,
    ui_callback: Any = None,
    input_queue: Any = None,
    additional_files: Optional[list[Path]] = None,
    initial_agent_message: str = "",
) -> Dict[str, Any]:
    """Let the content agent control the grouped V3 workflow tools."""
    if auto:
        return _run_agent_controlled_workflow_auto(state=state, agent=agent, user_notes=user_notes)

    try:
        from langchain.tools import tool
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
        from agent.tools import _get_img_describer_llm
    except Exception as exc:
        print(f"[Content Agent] Tool-calling agent unavailable: {exc}")
        if not state.get("input_preprocessing_complete"):
            state = run_stepparser_and_resolve_paths(state)
            state = ingest_user_documents_tool(state, additional_files or [])
            state["input_preprocessing_complete"] = True
        return _run_agent_controlled_workflow_auto(state=state, agent=agent, user_notes=user_notes)

    memory: Dict[str, str] = {
        "document_summary": "",
        "context_block": "",
        "assembly_summary": "",
        "sequence_summary": "",
    }
    config = state.get("config") or {}
    content_workflow_prompt_id = str(config.get("content_workflow_agent_prompt_id") or "content_workflow_agent_v3")
    readadditional_prompt_id = str(config.get("readadditional_data_tool_prompt_id") or "readadditional_data_tool_v1")

    def _context_or_arg(context_block: str = "") -> str:
        context = (context_block or "").strip() or memory.get("context_block", "")
        if context:
            memory["context_block"] = context
            state["additional_context_block"] = context
        return context

    def _save_understanding() -> None:
        understanding = ContentUnderstanding(
            understanding_markdown=(
                "# Content Agent Workflow Understanding\n\n"
                f"## Document Summary\n\n{memory.get('document_summary') or 'Not read yet.'}\n\n"
                f"## Assembly Summary\n\n{memory.get('assembly_summary') or 'Not analysed yet.'}\n\n"
                f"## Sequence Summary\n\n{memory.get('sequence_summary') or 'Not generated yet.'}\n"
            ),
            additional_context_block=memory.get("context_block", ""),
            document_count=state.get("ingested_document_count", 0),
            warnings=state.get("ingestion_warnings", []),
        )
        agent.save_understanding(understanding)
        state["content_agent_understanding"] = understanding

    @tool("Preprocess_Input_Data_tool")
    def preprocess_input_data_tool() -> str:
        """Preprocess the STEP file, resolve workflow paths, and ingest supporting documents."""
        if state.get("input_preprocessing_complete"):
            return "Input preprocessing has already completed."

        print("\n[AGENT TOOL] Preprocess_Input_Data_tool")
        updated = run_stepparser_and_resolve_paths(state)
        state.update(updated)
        updated = ingest_user_documents_tool(state, additional_files or [])
        state.update(updated)
        state["input_preprocessing_complete"] = True
        doc_list = _format_document_list(state.get("document_bundle"))
        _emit_ui(
            ui_callback,
            "documents_ingested",
            count=state.get("ingested_document_count", 0),
            warnings=state.get("ingestion_warnings", []),
            files=[str(path) for path in additional_files or []],
        )
        return _tool_observation(
            title="Preprocess_Input_Data_tool completed",
            paths=[
                Path(state["preprocessing_dir"]) if state.get("preprocessing_dir") else None,
                Path(state["session_root"]) / "Agent_txt_files" / "ingested_documents",
            ],
            body=(
                "STEP preprocessing, CAD rendering, workflow path resolution, and "
                f"supporting-document ingestion completed.\n\nDocuments:\n{doc_list}"
            ),
        )

    @tool("Readadditional_Data_tool")
    def readadditional_data_tool(focus: str = "all") -> str:
        """Read uploaded/additional files and return a compressed engineering summary."""
        if not state.get("input_preprocessing_complete"):
            return "Call Preprocess_Input_Data_tool before reading additional data."
        doc_list = _format_document_list(state.get("document_bundle"))
        print("\n[AGENT TOOL] Readadditional_Data_tool")
        print(doc_list)
        summary = agent.summarize_documents_with_llm(
            state.get("document_bundle"),
            user_notes=f"{user_notes}\n\nRequested focus: {focus}".strip(),
            prompt_id=readadditional_prompt_id,
        )
        memory["document_summary"] = summary
        _save_understanding()
        return _tool_observation(
            title="Readadditional_Data_tool completed",
            paths=[Path(state["session_root"]) / "Agent_txt_files" / "additional_data_llm_summary.md"],
            body=f"Investigated documents:\n{doc_list}\n\nSummary:\n{summary}",
        )

    @tool("Set_Content_Context_tool")
    def set_content_context_tool(context_block: str) -> str:
        """Set or update the Markdown context block passed into downstream workflow tools."""
        context = agent._truncate_context(context_block or "")
        memory["context_block"] = context
        state["additional_context_block"] = context
        _save_understanding()
        return f"Context block saved ({len(context)} chars)."

    @tool("Analyse_Assembly_tool")
    def analyse_assembly_agent_tool(context_block: str = "") -> str:
        """Run assembly analysis. Use after reading documents and setting context."""
        context = _context_or_arg(context_block)
        print("\n[AGENT TOOL] Analyse_Assembly_tool")
        updated = analyse_assembly_tool(state, context_block=context)
        state.update(updated)
        summary = extract_assembly_summary(state)
        overview_path = Path(state["session_root"]) / f"assembly_{state['assembly_name']}_Overview_Enriched.json"
        memory["assembly_summary"] = summary
        _save_understanding()
        return _tool_observation(
            title="Analyse_Assembly_tool completed",
            paths=[overview_path],
            body=summary,
            extra=_safe_file_excerpt(overview_path, max_chars=3000),
        )

    @tool("Analyse_Monoparts_And_Merge_tool")
    def analyse_monoparts_agent_tool(context_block: str = "") -> str:
        """Run monopart analysis and merge enriched data/BOM. Use after assembly dialogue is resolved."""
        context = _context_or_arg(context_block)
        print("\n[AGENT TOOL] Analyse_Monoparts_And_Merge_tool")
        print(
            "[AGENT TOOL] Monopart execution mode: "
            f"{'parallel' if state.get('parallel') else 'sequential'} "
            f"(max_workers={state.get('max_workers')})"
        )
        updated = analyse_monoparts_and_merge_tool(state, context_block=context)
        state.update(updated)
        session_root = Path(state["session_root"])
        bom_path = session_root / f"{state['assembly_name']}_BOM_enriched.json"
        return _tool_observation(
            title="Analyse_Monoparts_And_Merge_tool completed",
            paths=[session_root / "enriched_parts", bom_path],
            body=(
                f"Execution mode: {'parallel' if state.get('parallel') else 'sequential'} "
                f"(max_workers={state.get('max_workers')})\n"
                f"Part results: {len(state.get('part_results') or [])}\n"
                "Monopart analysis, enriched part copy, and BOM merge completed."
            ),
            extra=_safe_file_excerpt(bom_path, max_chars=3500),
        )

    @tool("Generate_Or_Revise_Sequence_tool")
    def generate_or_revise_sequence_agent_tool(context_block: str = "", revision_remarks: str = "") -> str:
        """Generate or revise the assembly sequence. Provide revision_remarks when user asks for changes."""
        context = _context_or_arg(context_block)
        print("\n[AGENT TOOL] Generate_Or_Revise_Sequence_tool")
        updated = generate_or_revise_sequence_tool(
            state,
            context_block=context,
            revision_remarks=(revision_remarks or None),
        )
        state.update(updated)
        summary = extract_sequence_summary(state)
        memory["sequence_summary"] = summary
        _save_understanding()
        sequence_path = Path(state["assembly_sequence_path"]) if state.get("assembly_sequence_path") else None
        return _tool_observation(
            title="Generate_Or_Revise_Sequence_tool completed",
            paths=[sequence_path] if sequence_path else [],
            body=summary,
            extra=_safe_file_excerpt(sequence_path, max_chars=3500) if sequence_path else "",
        )

    @tool("Run_Final_Assessment_Pipeline_tool")
    def run_final_assessment_agent_tool(context_block: str = "") -> str:
        """Run rendering, interaction analysis, FFA assessment, FFA report, and post-processing."""
        context = _context_or_arg(context_block)
        print("\n[AGENT TOOL] Run_Final_Assessment_Pipeline_tool")
        updated = run_final_assessment_pipeline_tool(
            state,
            context_block=context,
            stage_callback=lambda phase, progress_step: _emit_ui(
                ui_callback,
                "phase_changed",
                phase=phase,
                progress_step=progress_step,
            ),
        )
        state.update(updated)
        ffa_path = _resolve_artifact_file(state.get("ffa_assessment_path"), "ffa_assessment.json")
        ffa_report_json = _find_ffa_report_json(state)
        post = state.get("ffa_post_processing_result") or {}
        state["final_assessment_complete"] = True
        return _tool_observation(
            title="Run_Final_Assessment_Pipeline_tool completed",
            paths=[
                Path(state["assembly_sequence_path"]) if state.get("assembly_sequence_path") else None,
                ffa_path,
                ffa_report_json,
                Path(post["pdf_report"]) if post.get("pdf_report") else None,
            ],
            body=(
                "Rendering, interaction analysis, FFA assessment, report synthesis, and post-processing completed.\n"
                "The synthesized FFA report JSON is included below. Use it to explain results and answer user questions."
            ),
            extra=_safe_file_excerpt(ffa_report_json, max_chars=18000) if ffa_report_json else "",
            max_chars=22000,
        )

    @tool("Finish_Workflow_tool")
    def finish_workflow_tool(final_message: str = "") -> str:
        """Finish only after final assessment and when the user explicitly says they are done."""
        if not state.get("final_assessment_complete"):
            return "Cannot finish yet: the final assessment pipeline has not completed."
        state["agent_workflow_finished"] = True
        return final_message or "Workflow finished."

    tools = [
        preprocess_input_data_tool,
        readadditional_data_tool,
        set_content_context_tool,
        analyse_assembly_agent_tool,
        analyse_monoparts_agent_tool,
        generate_or_revise_sequence_agent_tool,
        run_final_assessment_agent_tool,
        finish_workflow_tool,
    ]

    system_prompt = _load_required_prompt(content_workflow_prompt_id)
    messages: list[Any] = []
    if initial_agent_message.strip():
        messages.append(AIMessage(content=initial_agent_message.strip()))
    messages.append(
        HumanMessage(
            content=(
                f"I have uploaded the assembly **{state.get('assembly_name')}**.\n"
                f"User notes: {user_notes or '(none)'}\n"
                f"Supporting documents uploaded: {len(additional_files or [])}\n\n"
                "Continue our conversation. Explain the next step, then begin the workflow "
                "by calling the required first tool."
            )
        )
    )

    llm = _get_img_describer_llm(max_completion_tokens=2500)
    llm_with_tools = llm.bind_tools(tools)
    transcript: list[Dict[str, Any]] = []

    max_turns = 80
    for _ in range(max_turns):
        response = llm_with_tools.invoke([SystemMessage(content=system_prompt), *messages])
        tool_calls = getattr(response, "tool_calls", None) or []
        messages.append(AIMessage(content=response.content or "", tool_calls=tool_calls))
        transcript.append({"role": "assistant", "content": response.content or "", "tool_calls": tool_calls})

        if response.content:
            print("\n[Content Agent]")
            print(response.content)
            _emit_ui(
                ui_callback,
                "agent_message",
                role="agent",
                content=response.content,
                phase=_agent_phase_from_state(state),
            )

        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call.get("name") or tool_call.get("type")
                tool_input = tool_call.get("args") or {}
                tool_call_id = tool_call.get("id", tool_name)
                tool_obj = {tool.name: tool for tool in tools}.get(tool_name)
                _emit_ui(
                    ui_callback,
                    "tool_started",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    arguments=tool_input,
                    phase=_phase_for_tool(tool_name),
                )
                _emit_ui(
                    ui_callback,
                    "phase_changed",
                    phase=_phase_for_tool(tool_name),
                    progress_step=_progress_for_tool(tool_name),
                )
                tool_started = time.monotonic()
                if tool_obj is None:
                    observation = f"Unknown tool: {tool_name}"
                else:
                    try:
                        observation = tool_obj.invoke(tool_input)
                    except Exception as exc:
                        _emit_ui(
                            ui_callback,
                            "tool_failed",
                            tool_name=tool_name,
                            tool_call_id=tool_call_id,
                            duration_seconds=round(time.monotonic() - tool_started, 2),
                            error=f"{type(exc).__name__}: {exc}",
                        )
                        raise
                messages.append(ToolMessage(content=str(observation), tool_call_id=tool_call_id, name=tool_name))
                transcript.append({"role": "tool", "name": tool_name, "content": str(observation)})
                _emit_ui(
                    ui_callback,
                    "tool_completed",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    duration_seconds=round(time.monotonic() - tool_started, 2),
                    arguments=tool_input,
                    observation=str(observation),
                    phase=_phase_for_tool(tool_name),
                )
            if state.get("agent_workflow_finished"):
                break
            continue

        prompt = _checkpoint_prompt(state)
        _emit_ui(
            ui_callback,
            "input_waiting",
            agent="content_agent",
            prompt=prompt,
            phase=_agent_phase_from_state(state),
        )
        if input_queue is not None:
            user_reply = str(input_queue.get()).strip()
        else:
            user_reply = input("\nYou: ").strip()
        _emit_ui(ui_callback, "input_received", phase=_agent_phase_from_state(state))
        transcript.append({"role": "user", "content": user_reply})
        messages.append(HumanMessage(content=user_reply or "continue"))

    (Path(state["session_root"]) / "Agent_txt_files" / "content_agent_workflow_dialogue.json").write_text(
        __import__("json").dumps(transcript, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _emit_ui(
        ui_callback,
        "artifacts",
        session_root=str(state["session_root"]),
        assembly_sequence_path=state.get("assembly_sequence_path"),
        ffa_assessment_path=state.get("ffa_assessment_path"),
        ffa_report_path=state.get("ffa_report_path"),
        ffa_post_processing_result=state.get("ffa_post_processing_result") or {},
    )
    if state.get("agent_workflow_finished"):
        _emit_ui(ui_callback, "complete")
    return state


def _run_agent_controlled_workflow_auto(
    *,
    state: Dict[str, Any],
    agent: ContentAgent,
    user_notes: str,
) -> Dict[str, Any]:
    """Non-interactive fallback that follows the same required order."""
    config = state.get("config") or {}
    readadditional_prompt_id = str(config.get("readadditional_data_tool_prompt_id") or "readadditional_data_tool_v1")
    doc_summary = agent.summarize_documents_with_llm(
        state.get("document_bundle"),
        user_notes=user_notes,
        prompt_id=readadditional_prompt_id,
    )
    context_block = f"""## User Provided Assembly Context

### User Notes
{user_notes or "No manual notes provided."}

### Uploaded Document Summary
{doc_summary}
"""
    context_block = agent._truncate_context(context_block)
    state["additional_context_block"] = context_block
    agent.save_understanding(
        ContentUnderstanding(
            understanding_markdown="# Auto Content Agent Understanding\n\n" + context_block,
            additional_context_block=context_block,
            document_count=state.get("ingested_document_count", 0),
            warnings=state.get("ingestion_warnings", []),
        )
    )

    print("\n[AGENT AUTO] Analyse_Assembly_tool")
    state = analyse_assembly_tool(state, context_block=context_block)
    print("\n[AGENT AUTO] Analyse_Monoparts_And_Merge_tool")
    print(
        "[AGENT AUTO] Monopart execution mode: "
        f"{'parallel' if state.get('parallel') else 'sequential'} "
        f"(max_workers={state.get('max_workers')})"
    )
    state = analyse_monoparts_and_merge_tool(state, context_block=context_block)
    print("\n[AGENT AUTO] Generate_Or_Revise_Sequence_tool")
    state = generate_or_revise_sequence_tool(state, context_block=context_block)
    print("\n[AGENT AUTO] Run_Final_Assessment_Pipeline_tool")
    state = run_final_assessment_pipeline_tool(state, context_block=context_block)
    state["agent_workflow_finished"] = True
    return state


def _emit_ui(ui_callback: Any, event_type: str, **payload: Any) -> None:
    """Emit a plain event dictionary without coupling the workflow to Streamlit."""
    if ui_callback is None:
        return
    event = {"type": event_type, **payload}
    try:
        ui_callback(event)
    except TypeError:
        ui_callback(event_type, **payload)


def _phase_for_tool(tool_name: str) -> str:
    return {
        "Preprocess_Input_Data_tool": "PREPROCESS",
        "Readadditional_Data_tool": "READ_DOCUMENTS",
        "Set_Content_Context_tool": "SET_CONTEXT",
        "Analyse_Assembly_tool": "ANALYSE_ASSEMBLY",
        "Analyse_Monoparts_And_Merge_tool": "ANALYSE_MONOPARTS",
        "Generate_Or_Revise_Sequence_tool": "GENERATE_SEQUENCE",
        "Run_Final_Assessment_Pipeline_tool": "FINAL_ASSESSMENT",
        "Finish_Workflow_tool": "FINISH",
    }.get(tool_name, "AGENT")


def _progress_for_tool(tool_name: str) -> int:
    return {
        "Preprocess_Input_Data_tool": 1,
        "Readadditional_Data_tool": 2,
        "Set_Content_Context_tool": 2,
        "Analyse_Assembly_tool": 3,
        "Analyse_Monoparts_And_Merge_tool": 5,
        "Generate_Or_Revise_Sequence_tool": 6,
        "Run_Final_Assessment_Pipeline_tool": 8,
        "Finish_Workflow_tool": 11,
    }.get(tool_name, 0)


def _agent_phase_from_state(state: Dict[str, Any]) -> str:
    if state.get("final_assessment_complete"):
        return "REPORT_DIALOGUE"
    if state.get("assembly_sequence_path"):
        return "SEQUENCE_DIALOGUE"
    if state.get("assembly_result"):
        return "ASSEMBLY_DIALOGUE"
    return "CONTENT_AGENT"


def _checkpoint_prompt(state: Dict[str, Any]) -> str:
    phase = _agent_phase_from_state(state)
    if phase == "REPORT_DIALOGUE":
        return "Ask about the FFA report, or say that you are finished."
    if phase == "SEQUENCE_DIALOGUE":
        return "Approve the proposed assembly sequence or describe the required revision."
    if phase == "ASSEMBLY_DIALOGUE":
        return "Confirm the assembly understanding or provide important corrections."
    return "Reply to the content agent."


def _apply_parallel_settings(state: Dict[str, Any], config: Dict[str, Any]) -> None:
    state["parallel"] = bool(config.get("parallel", False))
    state["max_workers"] = max(1, int(config.get("max_workers", 4) or 4))


def _load_required_prompt(prompt_id: str) -> str:
    try:
        from agent.prompt_store import get_prompt_template

        prompt = get_prompt_template(prompt_id)
    except Exception as exc:
        raise RuntimeError(f"Could not load prompt '{prompt_id}' from configs/prompts.yaml: {exc}") from exc
    if not prompt:
        raise ValueError(f"Prompt '{prompt_id}' was not found in configs/prompts.yaml")
    return prompt


def _tool_observation(
    *,
    title: str,
    paths: list[Optional[Path]],
    body: str = "",
    extra: str = "",
    max_chars: int = 9000,
) -> str:
    """Build the compact observation string that the LLM agent receives."""
    existing_paths = [str(path) for path in paths if path]
    sections = [f"# {title}"]
    if existing_paths:
        sections.append("## Saved Artifacts\n" + "\n".join(f"- `{path}`" for path in existing_paths))
    if body:
        sections.append("## Summary Returned To Agent\n" + str(body).strip())
    if extra:
        sections.append("## Saved Artifact Excerpt\n" + str(extra).strip())
    observation = "\n\n".join(sections)
    if len(observation) <= max_chars:
        return observation
    return observation[:max_chars] + "\n\n[Tool observation truncated for agent context.]"


def _format_document_list(bundle: Any) -> str:
    documents = getattr(bundle, "documents", None) or []
    if not documents:
        return "- No additional documents available."
    lines = []
    for index, doc in enumerate(documents, start=1):
        lines.append(
            f"{index}. {getattr(doc, 'file_name', '(unknown)')} "
            f"[{getattr(doc, 'file_type', '') or 'unknown type'} via {getattr(doc, 'extraction_backend', '') or 'unknown backend'}]\n"
            f"   Source: {getattr(doc, 'source_path', '')}"
        )
    return "\n".join(lines)


def _safe_file_excerpt(path: Optional[Path], *, max_chars: int = 3000) -> str:
    """Read a bounded excerpt from an artifact so the agent can inspect tool output."""
    if path is None:
        return ""
    path = Path(path)
    if path.is_dir():
        children = sorted(child.name for child in path.iterdir())[:50]
        return "Directory contents:\n" + "\n".join(f"- {name}" for name in children)
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Could not read artifact excerpt: {exc}"
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Artifact excerpt truncated.]"


def _resolve_artifact_file(path_value: Any, file_name: str) -> Optional[Path]:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_dir():
        return path / file_name
    return path


def _find_ffa_report_json(state: Dict[str, Any]) -> Optional[Path]:
    report_path = state.get("ffa_report_path")
    if not report_path:
        return None
    path = Path(report_path)
    if path.is_file() and path.suffix.lower() == ".json":
        return path
    if not path.is_dir():
        return None

    assembly_name = str(state.get("assembly_name") or "").strip()
    preferred = path / f"{assembly_name}_ffa_report.json"
    if preferred.exists():
        return preferred

    candidates = sorted(path.glob("*_ffa_report.json"))
    return candidates[0] if candidates else None


def _try_discover_assembly() -> Optional[str]:
    try:
        return discover_assembly()
    except Exception:
        return None


def _ensure_terminal_configured() -> None:
    missing = [
        name
        for name, value in {
            "MASTER_STEP_INPUT_FOLDER": MASTER_STEP_INPUT_FOLDER,
            "STEPPARSER_OUTPUT_FOLDER": STEPPARSER_OUTPUT_FOLDER,
            "LLM_OUTPUT_FOLDER": LLM_OUTPUT_FOLDER,
            "TEXTBASED_ADDITIONAL_DATA": TEXTBASED_ADDITIONAL_DATA,
            "EXPERIMENT_CONFIG_FOLDER": EXPERIMENT_CONFIG_FOLDER,
            "EXPERIMENT_CONFIG_NAME": EXPERIMENT_CONFIG_NAME,
            "TERMINAL_INTERACTIVE": TERMINAL_INTERACTIVE,
        }.items()
        if value is None
    ]
    if missing:
        raise RuntimeError(
            "app_workflow_v3.py requires terminal configuration injection from "
            "7_run_app_workflow_AGENT_terminal.py. Missing: " + ", ".join(missing)
        )


def _resolve_workspace_path(path_like: str | Path | None) -> Path:
    if path_like is None:
        raise RuntimeError("Path configuration was not injected by 7_run_app_workflow_AGENT_terminal.py")
    path = Path(path_like)
    if path.is_absolute():
        return path
    return WORKSPACE_ROOT / path


def _resolve_experiment_config() -> Optional[Path]:
    if not EXPERIMENT_CONFIG_NAME or str(EXPERIMENT_CONFIG_NAME).lower() in {"all", "*"}:
        return None

    candidate = Path(EXPERIMENT_CONFIG_NAME)
    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        candidate = candidate.with_suffix(".yaml")

    if not candidate.is_absolute() and len(candidate.parts) == 1:
        candidate = _resolve_workspace_path(EXPERIMENT_CONFIG_FOLDER) / candidate
    elif not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    return candidate


def _get_step_files() -> Dict[str, Path]:
    input_root = _resolve_workspace_path(MASTER_STEP_INPUT_FOLDER)
    if not input_root.exists():
        raise FileNotFoundError(f"MASTER_STEP_INPUT_FOLDER not found: {input_root}")

    step_files = {
        path.stem: path
        for path in sorted(input_root.glob("*.STEP"))
    }
    if not step_files:
        raise FileNotFoundError(f"No .STEP files found in {input_root}")
    return step_files


def _get_textbased_files(assembly_name: str) -> list[Path]:
    assembly_dir = _resolve_workspace_path(TEXTBASED_ADDITIONAL_DATA) / assembly_name
    if not assembly_dir.exists():
        return []
    return [path for path in sorted(assembly_dir.iterdir()) if path.is_file()]


def _create_experiment_session(step_file: Path, assembly_name: Optional[str]) -> tuple[str, Path]:
    """Create an app-compatible session inside LLM_OUTPUT_FOLDER/config/assembly."""
    step_file = _resolve_workspace_path(step_file).resolve()
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    assembly = assembly_name or step_file.stem
    experiment_name = Path(EXPERIMENT_CONFIG_NAME or "app_workflow").stem
    session_root = _resolve_workspace_path(LLM_OUTPUT_FOLDER) / experiment_name / assembly

    for subdir in ["input", "preprocessing", "Agent_txt_files", "enriched_parts", "ffa_assessment"]:
        (session_root / subdir).mkdir(parents=True, exist_ok=True)

    target = session_root / "input" / f"{assembly}.STEP"
    if not target.exists() or step_file.stat().st_mtime > target.stat().st_mtime:
        shutil.copy2(step_file, target)
    return assembly, session_root


def _print_folder_structure(config_path: Optional[Path]) -> None:
    print("\nFolder structure")
    print(f"  MASTER_STEP_INPUT_FOLDER:      {_resolve_workspace_path(MASTER_STEP_INPUT_FOLDER)}")
    print(f"  STEPPARSER_OUTPUT_FOLDER:      {_resolve_workspace_path(STEPPARSER_OUTPUT_FOLDER)}")
    print(f"  LLM_OUTPUT_FOLDER:             {_resolve_workspace_path(LLM_OUTPUT_FOLDER)}")
    print(f"  TEXTBASED_ADDITIONAL_DATA:     {_resolve_workspace_path(TEXTBASED_ADDITIONAL_DATA)}")
    print(f"  EXPERIMENT_CONFIG:             {config_path}")


def _print_final_outputs(state: Dict[str, Any]) -> None:
    session_root = Path(state["session_root"])
    print("\n" + "=" * 80)
    print("V3 WORKFLOW COMPLETE")
    print("=" * 80)
    print(f"Session: {session_root}")
    print(f"Assembly: {state.get('assembly_name')}")
    print(f"Sequence: {state.get('assembly_sequence_path')}")
    print(f"FFA assessment: {state.get('ffa_assessment_path')}")
    print(f"FFA report: {state.get('ffa_report_path')}")
    post = state.get("ffa_post_processing_result") or {}
    if post.get("pdf_report"):
        print(f"PDF report: {post.get('pdf_report')}")
    print(f"Agent files: {session_root / 'Agent_txt_files'}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="App Workflow V3: content-agent terminal runner")
    parser.add_argument("--config", type=Path, default=None, help="Config file path")
    parser.add_argument("--assembly", type=str, default=None, help="Assembly name")
    parser.add_argument("--step-file", type=Path, default=None, help="STEP file path")
    parser.add_argument("--additional-file", type=Path, action="append", default=[], help="Additional document path")
    parser.add_argument("--notes", type=str, default="", help="Manual content-agent notes")
    parser.add_argument("--session-root", type=Path, default=None, help="Existing/new session root")
    parser.add_argument("--interactive", action="store_true", help="Force terminal confirmation prompts")
    parser.add_argument("--auto", action="store_true", help="Run without interactive confirmation prompts")
    parser.add_argument("--setup-only", action="store_true", help="Create configured session folders, then exit")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    _ensure_terminal_configured()

    config_path = args.config or _resolve_experiment_config()
    if config_path:
        os.environ["APA_EXPERIMENT_YAML"] = str(config_path)
    os.environ["APA_MASTER_STEP_INPUT_FOLDER"] = str(_resolve_workspace_path(MASTER_STEP_INPUT_FOLDER))
    os.environ["APA_STEPPARSER_OUTPUT_FOLDER"] = str(_resolve_workspace_path(STEPPARSER_OUTPUT_FOLDER))

    interactive = TERMINAL_INTERACTIVE
    if args.interactive:
        interactive = True
    if args.auto:
        interactive = False

    if args.step_file:
        runs = [_create_experiment_session(args.step_file, args.assembly)]
    elif args.session_root:
        assembly_name = args.assembly or Path(args.session_root).name
        runs = [(assembly_name, args.session_root)]
    else:
        step_files = _get_step_files()
        if args.assembly:
            if args.assembly not in step_files:
                raise FileNotFoundError(
                    f"Assembly {args.assembly!r} not found in {MASTER_STEP_INPUT_FOLDER}"
                )
            selected = {args.assembly: step_files[args.assembly]}
        else:
            selected = step_files
        runs = [_create_experiment_session(path, name) for name, path in selected.items()]

    _print_folder_structure(config_path)

    for assembly_name, session_root in runs:
        additional_files = list(args.additional_file or [])
        additional_files.extend(_get_textbased_files(assembly_name))
        if args.setup_only:
            print("\n" + "=" * 80)
            print(f"V3 SETUP ONLY: {assembly_name}")
            print("=" * 80)
            print(f"Session: {session_root}")
            print(f"STEP: {session_root / 'input' / f'{assembly_name}.STEP'}")
            print(f"Additional text files: {len(additional_files)}")
            continue
        run_app_workflow_v3_terminal(
            config_path=config_path,
            assembly_name=assembly_name,
            step_file=session_root / "input" / f"{assembly_name}.STEP",
            additional_files=additional_files,
            user_notes=args.notes,
            session_root=session_root,
            auto=not interactive,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
