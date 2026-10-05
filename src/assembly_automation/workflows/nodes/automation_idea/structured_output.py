"""Structured contract for a reviewable automation-planning idea."""

from pydantic import BaseModel, Field


class AutomationPlanningBrief(BaseModel):
    global_constraints: list[str] = Field(
    default_factory=list,
    description=(
        "Decisive requirements applying across the concept, derived "
        "from user constraints and engineering/FfA evidence. "
        "Identify feasibility conditions for requested automation. "
        "Do not repeat the complete FfA assessment but reflect on the processes and edge cases with high technical risk. If there are less than 10 processes, reflect on all."
    )
    )
        
    concept_direction: list[str] = Field(
        description=(
            "Compact bullets defining the preferred automation level, "
            "central concept, and decisive planning priority. "
        )
    )

    human_role: list[str] = Field(
        description=(
            "Which processes will be carried out by a human or multiple operators and which additional tools might be used."
        )
    )

    machine_role: list[str] = Field(
        description=(
            "Which processes will be carried out by machines and which equipment classes could be used. "
        )
    )

    montageablauf: list[str] = Field(
        description=(
            "Describe which steps will be carried out after each other and which steps can be carried out in parallel. and which are done by human or machines"
        )
    )

    system_architecture: list[str] = Field(
        description=(
            "Make the concept concrete for a human to read. Get accross the idea of the concept and the main equipment classes and the human machine split."
        )
    )


    material_flow_intent: list[str] = Field(
        description=(
            "High-level part supply, assembly transfer, and output flow. "
            "Name the preferred transfer principle and support/carrier approach "
            "when relevant. Do not automatically require a conveyor or robots."
        )
    )

    parallelization_intent: list[str] = Field(
        description=(
            "Preferred sequential or parallel organization and its decisive "
            "reason. Name independent work packages when parallelization "
            "is justified. Do not invent throughput gains or bottlenecks."
        )
    )

    assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Consequential unverified premises used to select the architecture. "
            "Do not restate supplied facts or invent numerical production targets."
        )
    )

    decisions_required: list[str] = Field(
        default_factory=list,
        description=(
            "Remaining design selections requiring evaluation before detailed "
            "planning. Identify the selection and decisive evaluation criterion. "
            "Do not reopen decisions already made without a specific reason."
        )
    )

    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Short questions requesting missing user or production information "
            "whose answers would materially change the architecture. "
            "Do not duplicate assumptions or design decisions."
        )
    )

    remarkforadmin: list[str] = Field(default_factory=list,
        description=(
            "Up to 10 short bullet statements for internal use only. "
            "Include any relevant information that may you help future planning."
            "Use an empty list when none are relevant."
            "Are there problems in the prompt, provided data or anything?"
            "how can we help you improve the prompt or the data to get better results?"
        )
    )   



class AutomationPlanningBrief_LEGACY(BaseModel):

    concept_direction: list[str] = Field(min_length=1, max_length=6, description="High-level principles that define the intended automation concept, such as the degree of automation, technical focus, and division of work.")
    global_constraints: list[str] = Field(default_factory=list, description="Constraints that apply to the complete automation concept, reflecting on FfA results.")
    human_role: list[str] = Field(description="Intended responsibilities of human operators within the automation concept.")
    machine_role: list[str] = Field( description="Intended responsibilities of machines within the automation concept.")
    material_flow_intent: list[str] = Field( description="High-level intent for supplying parts, moving the assembly, and transferring material through the assembly process.")
    decisions_required: list[str] = Field(default_factory=list, description="Important decisions that must be made before detailed automation planning can be finalized.")
    open_questions: list[str] = Field(default_factory=list, description="Questions for the user whose answers could materially change the automation idea.")

SCHEMAS = {"automation_planning_brief_v1": AutomationPlanningBrief}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown automation-idea schema: {schema_id}") from exc
