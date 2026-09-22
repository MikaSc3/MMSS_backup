"""Structured contract for one assembly-step interaction analysis."""

from pydantic import BaseModel, Field, field_validator


class InteractionAnalysis(BaseModel):
    geometric_interaction: list[str] = Field(min_length=1, description="Geometric contacts, approaches and final interfaces between the existing assembly and joining instances.")
    positioning_possibilities: list[str] = Field(min_length=1, description="Feasible fixture orientations for the existing assembly and their geometric support.")
    accuracy_of_target_position: list[str] = Field(min_length=1, description="Evidence-based translational and rotational accuracy requirements and consequences of misalignment.")
    positioning_aids: list[str] = Field(min_length=1, description="Chamfers, shoulders, tapers, guide surfaces, stops and other alignment features.")
    additional_orientation_by_rotation: list[str] = Field(min_length=1, description="Required angular orientation, rotational symmetry and features enforcing clocking.")
    joining_tolerances: list[str] = Field(min_length=1, description="Likely fit relationship, sensitivity and tolerance uncertainty without unsupported numerical invention.")
    accessibility_to_joining_position: list[str] = Field(min_length=1, description="Approach directions, visibility, tool clearance and obstructions at this sequence state.")
    joining_motion: list[str] = Field(min_length=1, description="Required insertion or joining trajectory and constrained degrees of freedom.")
    stability_in_positioned_state: list[str] = Field(min_length=1, description="Stability and self-holding behavior before permanent fixing.")
    feeding_of_joining_element: list[str] = Field(min_length=1, description="Any auxiliary fastener, adhesive, lubricant or other process element; the joining part itself is excluded.")
    fixing_of_mounted_part: list[str] = Field(min_length=1, description="Likely fixing process and geometry-driven automation implications.")
    evidence_limitations: list[str] = Field(min_length=1, description="Material uncertainties, hidden geometry and conclusions requiring drawings, tolerances or physical validation.")

    @field_validator("*", mode="after")
    @classmethod
    def bullets_are_nonempty(cls, value):
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("Interaction-analysis bullets must be nonempty strings")
        return value


SCHEMAS = {"interaction_analysis_v1": InteractionAnalysis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown interaction-analysis schema: {schema_id}") from exc
