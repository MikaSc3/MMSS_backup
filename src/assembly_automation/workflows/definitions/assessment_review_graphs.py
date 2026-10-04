"""Cohesive LangGraph capabilities between assessment review checkpoints.

Each graph ends at a deliberate human-in-the-loop boundary. The existing
workflow methods remain the domain implementation and preserve artifacts,
revisions, and manifest semantics.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from .app_v3 import AssemblyAssessmentWorkflow


class ReviewCapabilityState(TypedDict, total=False):
    step_file: str
    revision_id: str
    user_context: str
    sequence_mode: str
    initial_sequence: Any
    sequence_constraints: str
    user_feedback_summary: str
    result: dict[str, Any]


def _compile(name: str, action: Callable[[ReviewCapabilityState], dict[str, Any]]) -> Any:
    def execute(state: ReviewCapabilityState) -> dict[str, Any]:
        return {"result": action(state)}

    graph = StateGraph(ReviewCapabilityState)
    graph.add_node(name, execute)
    graph.add_edge(START, name)
    graph.add_edge(name, END)
    return graph.compile(name=name)


def _result(graph: Any, input_state: ReviewCapabilityState) -> dict[str, Any]:
    state = graph.invoke(input_state)
    result = state.get("result") if isinstance(state, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError("Assessment review graph did not produce a result")
    return result


def run_assembly_review_graph(*, workflow: "AssemblyAssessmentWorkflow", step_file: str | Path,
                              user_context: str = "", force: bool = False) -> dict[str, Any]:
    """Preprocess and analyse the assembly, then stop for assembly-context review."""
    source = Path(step_file).resolve(strict=True)

    def action(state: ReviewCapabilityState) -> dict[str, Any]:
        workflow.preprocess(step_file=source)
        return workflow.analyze_assembly(user_context=state.get("user_context", ""), force=force)

    return _result(_compile("assembly_review", action), {"step_file": str(source),
                                                           "user_context": user_context})


def run_bom_review_graph(*, workflow: "AssemblyAssessmentWorkflow", user_context: str = "",
                         part_ids: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    """Analyse selected/all monoparts and merge the BOM, then stop for review."""
    def action(state: ReviewCapabilityState) -> dict[str, Any]:
        return workflow.analyze_monoparts(user_context=state.get("user_context", ""),
                                          part_ids=part_ids, force=force)

    return _result(_compile("bom_review", action), {"user_context": user_context})


def run_sequence_review_graph(*, workflow: "AssemblyAssessmentWorkflow", revision_id: str,
                              mode: str = "generate", initial_sequence: Any = None,
                              user_context: str = "", sequence_constraints: str = "",
                              user_feedback_summary: str = "") -> dict[str, Any]:
    """Generate/revise a sequence and stop for explicit sequence review."""
    if not revision_id:
        raise ValueError("Sequence review requires a revision ID")

    def action(state: ReviewCapabilityState) -> dict[str, Any]:
        return workflow.generate_sequence(
            revision_id=revision_id, mode=mode, initial_sequence=initial_sequence,
            user_context=state.get("user_context", ""),
            sequence_constraints=sequence_constraints,
            user_feedback_summary=user_feedback_summary)

    return _result(_compile("sequence_review", action), {
        "revision_id": revision_id, "sequence_mode": mode,
        "initial_sequence": initial_sequence, "user_context": user_context,
        "sequence_constraints": sequence_constraints,
        "user_feedback_summary": user_feedback_summary,
    })
