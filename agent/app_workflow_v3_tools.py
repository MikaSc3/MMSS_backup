"""Grouped workflow tools for the agent-driven app workflow v3."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from agent.content_agent import ContentAgent, ContentUnderstanding


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


def setup_session_v3(
    *,
    assembly_name: str,
    step_file: Optional[str | Path] = None,
    session_root: Optional[str | Path] = None,
    config: Optional[Dict[str, Any]] = None,
    prompt_library: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Create a v2-compatible V3 session and initial workflow state."""
    assembly_name = assembly_name.strip()
    if not assembly_name:
        raise ValueError("assembly_name is required")

    if session_root is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        session_root_path = WORKSPACE_ROOT / "data" / "sessions" / f"{timestamp}_{assembly_name}"
    else:
        session_root_path = Path(session_root)
        if not session_root_path.is_absolute():
            session_root_path = WORKSPACE_ROOT / session_root_path

    for subdir in ["input", "preprocessing", "Agent_txt_files", "enriched_parts", "ffa_assessment"]:
        (session_root_path / subdir).mkdir(parents=True, exist_ok=True)

    source_step = Path(step_file) if step_file else WORKSPACE_ROOT / "data" / "input" / f"{assembly_name}.STEP"
    if not source_step.is_absolute():
        source_step = WORKSPACE_ROOT / source_step
    if source_step.exists():
        target_step = session_root_path / "input" / f"{assembly_name}.STEP"
        if source_step.resolve() != target_step.resolve():
            shutil.copy2(source_step, target_step)
    elif step_file:
        raise FileNotFoundError(f"STEP file not found: {source_step}")

    os.environ["APA_EXPERIMENT_OUTPUT_DIR"] = str(session_root_path)

    state: Dict[str, Any] = {
        "assembly_name": assembly_name,
        "session_root": str(session_root_path),
        "sequence_run_counter": 0,
        "config": config or {},
        "prompt_library": prompt_library or {},
    }
    return state


def run_stepparser_and_resolve_paths(state: Dict[str, Any]) -> Dict[str, Any]:
    """Automatic precondition: run STEP preprocessing and resolve node paths."""
    assembly_name = state["assembly_name"]
    session_root = Path(state["session_root"])
    config = state.get("config", {})

    configured_stepparser_root = os.environ.get("APA_STEPPARSER_OUTPUT_FOLDER")
    if configured_stepparser_root:
        stepparser_output_root = Path(configured_stepparser_root)
        if not stepparser_output_root.is_absolute():
            stepparser_output_root = WORKSPACE_ROOT / stepparser_output_root
    else:
        stepparser_output_root = session_root / "preprocessing" / "stepparser"

    preprocessing_dir = stepparser_output_root / assembly_name

    if not preprocessing_dir.exists():
        from stepparser.processor import StepProcessor

        processor = StepProcessor(
            input_folder=str(session_root / "input"),
            output_folder=str(stepparser_output_root),
            skip_if_processed=True,
            color_mode="geometry",
            transparency_values=[0.0],
            headless_mode=config.get("rendering_headless_mode", True),
        )
        processor.process_all_step_files()

    standard_location = WORKSPACE_ROOT / "data" / "processed" / "stepparser" / assembly_name
    if preprocessing_dir.resolve() != standard_location.resolve():
        standard_location.parent.mkdir(parents=True, exist_ok=True)
        if preprocessing_dir.exists():
            shutil.copytree(preprocessing_dir, standard_location, dirs_exist_ok=True)

    from agent.workflow import _node_resolve_paths

    resolved = _node_resolve_paths({"datasource_root": str(preprocessing_dir)})
    state.update(resolved)
    state["preprocessing_dir"] = str(preprocessing_dir)
    state["standard_stepparser_dir"] = str(standard_location)
    return state


def ingest_user_documents_tool(
    state: Dict[str, Any],
    document_paths: Iterable[str | Path],
) -> Dict[str, Any]:
    """Read uploaded/provided documents into saved Markdown artifacts."""
    agent = _content_agent_from_state(state)
    bundle = agent.ingest_documents(list(document_paths or []))
    state["document_bundle"] = bundle
    state["ingested_document_count"] = len(bundle.documents)
    state["ingestion_warnings"] = bundle.warnings
    return state


def build_content_understanding_tool(
    state: Dict[str, Any],
    *,
    user_notes: str = "",
    corrections: str = "",
    assembly_analysis_summary: str = "",
    sequence_summary: str = "",
) -> Dict[str, Any]:
    """Build and persist the content-agent understanding and context block."""
    agent = _content_agent_from_state(state)
    understanding = agent.build_understanding(
        bundle=state.get("document_bundle"),
        user_notes=user_notes or state.get("user_notes", ""),
        corrections=corrections or state.get("content_agent_corrections", ""),
        assembly_analysis_summary=assembly_analysis_summary,
        sequence_summary=sequence_summary,
    )
    state["content_agent_understanding"] = understanding
    state["additional_context_block"] = understanding.additional_context_block
    state["user_notes"] = user_notes or state.get("user_notes", "")
    if corrections:
        state["content_agent_corrections"] = corrections
    return state


def analyse_assembly_tool(
    state: Dict[str, Any],
    *,
    context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """Run assembly analysis with a tool-call-scoped context block."""
    from agent.workflow import _node_run_assembly

    return _call_node_with_context(_node_run_assembly, state, context_block)


def analyse_monoparts_and_merge_tool(
    state: Dict[str, Any],
    *,
    context_block: Optional[str] = None,
) -> Dict[str, Any]:
    """Run monopart analysis and mechanical merge steps as one agent tool."""
    from agent.workflow import (
        _node_list_parts,
        _node_merge_bom,
        _node_merge_copy_part_data,
        _node_run_monoparts,
    )

    state = _node_list_parts(state)
    state = _call_node_with_context(_node_run_monoparts, state, context_block)
    state = _node_merge_copy_part_data(state)
    state = _node_merge_bom(state)
    return state


def generate_or_revise_sequence_tool(
    state: Dict[str, Any],
    *,
    context_block: Optional[str] = None,
    revision_remarks: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate the first sequence or regenerate it from user revision remarks."""
    from agent.workflow import (
        _node_generate_assembly_sequence,
        _node_generate_assembly_sequence_v2_agent_feedback,
    )

    state["enable_assembly_sequence"] = True
    state["asg_use_manual_order"] = False
    state["asg_include_gt_sequence"] = False

    if revision_remarks:
        session_root = Path(state["session_root"])
        remarks_file = session_root / f"remarks_{state['assembly_name']}.txt"
        remarks_file.write_text(revision_remarks, encoding="utf-8")
        state["previous_remarks_context"] = revision_remarks
        return _call_node_with_context(_node_generate_assembly_sequence_v2_agent_feedback, state, context_block)

    return _call_node_with_context(_node_generate_assembly_sequence, state, context_block)


def run_final_assessment_pipeline_tool(
    state: Dict[str, Any],
    *,
    context_block: Optional[str] = None,
    stage_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, Any]:
    """Run render, interaction analysis, FFA assessment, report, and post-processing."""
    from agent.workflow import (
        _node_assess_ffa,
        _node_ffa_post_processing,
        _node_ffa_reporter,
        _node_interaction_analysis,
        _node_render_assembly_steps,
    )

    if stage_callback:
        stage_callback("FINAL_RENDERING", 8)
    state = _node_render_assembly_steps(state)
    if stage_callback:
        stage_callback("FINAL_INTERACTIONS", 8)
    state = _call_node_with_context(_node_interaction_analysis, state, context_block)
    if stage_callback:
        stage_callback("FINAL_FFA", 9)
    state = _node_assess_ffa(state)
    if stage_callback:
        stage_callback("FINAL_REPORT", 10)
    state = _node_ffa_reporter(state)
    state = _node_ffa_post_processing(state)
    return state


def _call_node_with_context(node, state: Dict[str, Any], context_block: Optional[str]) -> Dict[str, Any]:
    node_state = dict(state)
    if context_block:
        node_state["_tool_context_block"] = context_block
    else:
        node_state.pop("_tool_context_block", None)
    result = node(node_state)
    result.pop("_tool_context_block", None)
    state.update(result)
    return state


def _content_agent_from_state(state: Dict[str, Any]) -> ContentAgent:
    config = state.get("config") or {}
    content_config = config.get("content_agent") if isinstance(config, dict) else {}
    max_context_chars = int((content_config or {}).get("max_context_chars", 12000))
    return ContentAgent(
        session_root=state["session_root"],
        assembly_name=state["assembly_name"],
        input_queue=state.get("_input_queue"),
        ui_callback=state.get("_ui_callback"),
        max_context_chars=max_context_chars,
    )
