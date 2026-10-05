"""LangGraph boundary for cohesive automation-concept planning.

The established planner already owns the domain-correct macro idea, parallel
step planning, aggregation, and concept synthesis. This graph keeps that
dependent domain work cohesive without adding an approval transition.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from .automation_planning import AutomationPlanningWorkflow


class AutomationConceptState(TypedDict, total=False):
    idea_path: str
    revision_id: str
    result: dict[str, Any]


def build_automation_concept_graph(workflow: "AutomationPlanningWorkflow") -> Any:
    """Compile the active-idea-to-concept capability for one session."""

    session_root = workflow.paths.root.resolve()

    def validate(state: AutomationConceptState) -> dict[str, Any]:
        revision_id = state.get("revision_id", "")
        idea_path = state.get("idea_path", "")
        if not revision_id or not idea_path:
            raise ValueError("Automation concept planning requires an idea path and revision ID")
        path = Path(idea_path).resolve(strict=True)
        if not path.is_relative_to(session_root / "08_planning" / "01_ideas"):
            raise ValueError("Automation idea must belong to this session")
        return {"idea_path": str(path)}

    def execute(state: AutomationConceptState) -> dict[str, Any]:
        return {"result": workflow.build_concept(
            idea_path=state["idea_path"], revision_id=state["revision_id"])}

    graph = StateGraph(AutomationConceptState)
    graph.add_node("validate_automation_idea", validate)
    graph.add_node("build_automation_concept", execute)
    graph.add_edge(START, "validate_automation_idea")
    graph.add_edge("validate_automation_idea", "build_automation_concept")
    graph.add_edge("build_automation_concept", END)
    return graph.compile(name="automation_concept_planning")


def run_automation_concept_graph(*, workflow: "AutomationPlanningWorkflow",
                                 idea_path: str | Path, revision_id: str) -> dict[str, Any]:
    """Execute the graph and preserve the planner's public result contract."""
    graph = build_automation_concept_graph(workflow)
    result = graph.invoke({"idea_path": str(idea_path), "revision_id": revision_id})
    value = result.get("result") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError("Automation concept graph did not produce a result")
    return value
