"""LangGraph boundary for the approved-sequence final FfA capability.

The graph deliberately delegates its domain stages to the established workflow
service during the first migration slice. This makes its input contract and
transition explicit now, without changing artifacts, manifests, or the proven
node implementations. Subsequent slices can split the execution node into
rendering, interaction, assessment, scoring, synthesis, and report nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from .app_v3 import AssemblyAssessmentWorkflow


class FinalAssessmentState(TypedDict, total=False):
    revision_id: str
    approved_sequence: str
    user_context: str
    result: dict[str, Any]


def build_final_assessment_graph(workflow: "AssemblyAssessmentWorkflow") -> Any:
    """Compile the explicit final-assessment capability for one session."""

    def validate(state: FinalAssessmentState) -> dict[str, Any]:
        revision_id = state.get("revision_id", "")
        sequence = state.get("approved_sequence", "")
        if not revision_id or not sequence:
            raise ValueError("Final assessment requires an approved sequence revision and path")
        path = Path(sequence).resolve(strict=True)
        expected = workflow.paths.revision(revision_id).resolve()
        if not path.is_relative_to(expected):
            raise ValueError("Approved sequence must belong to the requested revision")
        return {"approved_sequence": str(path)}

    def execute(state: FinalAssessmentState) -> dict[str, Any]:
        return {"result": workflow.complete_from_sequence(
            revision_id=state["revision_id"],
            approved_sequence=state["approved_sequence"],
            user_context=state.get("user_context", ""),
        )}

    graph = StateGraph(FinalAssessmentState)
    graph.add_node("validate_approved_sequence", validate)
    graph.add_node("execute_final_assessment", execute)
    graph.add_edge(START, "validate_approved_sequence")
    graph.add_edge("validate_approved_sequence", "execute_final_assessment")
    graph.add_edge("execute_final_assessment", END)
    return graph.compile(name="final_ffa_assessment")


def run_final_assessment_graph(*, workflow: "AssemblyAssessmentWorkflow", revision_id: str,
                               approved_sequence: str | Path,
                               user_context: str = "") -> dict[str, Any]:
    """Execute the graph and return the stable workflow-result contract."""
    graph = build_final_assessment_graph(workflow)
    result = graph.invoke({
        "revision_id": revision_id,
        "approved_sequence": str(approved_sequence),
        "user_context": user_context,
    })
    value = result.get("result") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError("Final assessment graph did not produce a result")
    return value
