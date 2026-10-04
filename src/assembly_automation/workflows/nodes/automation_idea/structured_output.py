"""Structured contract for a reviewable automation-planning idea."""

from pydantic import BaseModel, Field


class SubprocessPolicy(BaseModel):
    separation: str = Field(description="Rationale for the separation subprocess. How is the joining part seperated in the assembly step?")
    handling: str = Field(description="Rationale for the handling subprocess. How is the joining part handled towards the joining position in the assembly step?")
    positioning: str = Field(description="Rationale for the handling subprocess. How is the joining part positioned in its final end state position?")
    joining: str = Field(description="Rationale for the Joining subprocess. How is the joining part handled towards its target position in the assembly step?")
    inspection: str | None = Field(None, description="Rationale for the inspection subprocess. Is inspection required for the joining part in the assembly step? If yes, how is it performed?")
    transfer: str | None = Field(None, description="Rationale for the transfer subprocess. How could the assembled subassembly be transferred to the next assembly step?")


class AutomationPlanningBrief(BaseModel):
    objective: str = Field(min_length=1, description="Primary objective of the automation idea, reflecting what the user wants to achieve.")
    concept_direction: list[str] = Field(min_length=1, max_length=6, description="High-level principles that define the intended automation concept, such as the degree of automation, technical focus, and division of work.")
    global_constraints: list[str] = Field(default_factory=list, description="Constraints that apply to the complete automation concept, such as space, production, safety, budget, or technology restrictions.")
    human_role: list[str] = Field(min_length=1, max_length=5, description="Intended responsibilities of human operators within the automation concept.")
    material_flow_intent: list[str] = Field(min_length=1, max_length=5, description="High-level intent for supplying parts, moving the assembly, and transferring material through the assembly process.")
    expected_benefits: list[str] = Field(default_factory=list, max_length=5, description="Expected benefits of the automation idea, without inventing unverified quantitative improvements.")
    subprocess_policy: SubprocessPolicy = Field(description="Global subprocess guidance that detailed step planning should apply where relevant to each assembly step.")
    preferred_equipment_or_technology: list[str] = Field(default_factory=list, description="List of preferred equipment or technology for the automation idea. This can include specific machines, special tools, fixtures, or technologies that are desired for the automation solution")
    prohibited_equipment_or_technology: list[str] = Field(default_factory=list, description="Equipment or technologies that must not be used in the automation concept.")
    ffa_conflicts: list[str] = Field(default_factory=list, description="Conflicts between the requested automation direction and risks or limitations identified by the FfA assessment.")
    planning_assumptions: list[str] = Field(default_factory=list, description="Assumptions needed to formulate the idea when required product or production information is unavailable.")
    decisions_required: list[str] = Field(default_factory=list, description="Important decisions that must be made before detailed automation planning can be finalized.")
    open_questions: list[str] = Field(default_factory=list, description="Questions for the user whose answers could materially change the automation idea.")

SCHEMAS = {"automation_planning_brief_v1": AutomationPlanningBrief}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown automation-idea schema: {schema_id}") from exc
