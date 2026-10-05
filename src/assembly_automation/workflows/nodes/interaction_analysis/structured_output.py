"""Structured contract for one assembly-step interaction analysis."""

from pydantic import BaseModel, Field, field_validator

from pydantic import BaseModel, Field


class InteractionAnalysis(BaseModel):
    geometric_interaction: list[str] = Field(
        description=(
            "Up to 5 compact feature-led bullets describing mating geometry "
            "and engagement order. Format: 'Interface: interaction'. "
            "Exclude motion instructions and fixation details."
        )
    )

    positioning_possibilities: list[str] = Field(
        description=(
            "Up to 2 compact bullets identifying useful fixture orientations "
            "and their support/reference surfaces. Prefer the strongest option; "
            "add another only when it offers a distinct practical advantage."
        )
    )

    accuracy_of_target_position: list[str] = Field(
        description=(
            "Up to 2 compact bullets identifying required alignment or final "
            "position and the consequence of error. Avoid unsupported numerical "
            "tolerances and vague accuracy ratings."
        )
    )

    positioning_aids: list[str] = Field(
        description=(
            "Up to 3 compact bullets naming geometric guides, lead-ins, "
            "centering features, or stops and their effects between the parts."
            "If its the first step, you can assume the fixture has lead ins and defined stops"
        )
    )

    additional_orientation_by_rotation: list[str] = Field(
        description=(
            "Up to 2 compact bullets covering angular clocking and "
            "end-for-end orientation where relevant. Distinguish rotational "
            "symmetry from functional orientation requirements."
        )
    )

    joining_tolerances: list[str] = Field(
        description=(
            "Up to 1 compact bullet identifying the supported or working "
            "fit relationship and its decisive sensitivity between the parts. "
            "No invented tolerance values or fit classes."
        )
    )

    accessibility_to_joining_position: list[str] = Field(
        description=(
            "Up to 2 compact bullets identifying the approach corridor "
            "and decisive obstruction or tool/gripper clearance condition "
            "at the current sequence state."
        )
    )

    joining_motion: list[str] = Field(
        description=(
            "Up to 2 compact bullets describing the joining trajectory "
            "and any required sequential translation, rotation, or deformation. "
            "Do not repeat interface geometry."
        )
    )

    stability_in_positioned_state: list[str] = Field(
        description=(
            "Up to 2 compact bullets describing support and remaining "
            "motion after positioning, before final fixation. "
            "Do not equate supported with fully retained."
        )
    )

    feeding_of_joining_element: list[str] = Field(
        description=(
            "Up to 1 compact bullet naming auxiliary process elements "
            "and their delivery requirement. Exclude joining instances. "
            "Return an empty list when none are indicated."
        )
    )

    fixing_of_mounted_part: list[str] = Field(
        description=(
            "Up to 2 compact bullets describing retention established "
            "in this step and any temporary holding needed until later fixation. "
            "Exclude general alignment risks and tolerance discussion."
        )
    )

    assumptions: list[str] = Field(default_factory=list,
        description=(
            "Up to 3 compact bullets recording consequential unverified "
            "premises or unresolved conditions affecting this operation. "
            "Name the decisive missing input only when useful. "
            "Do not repeat generic uncertainty statements."
        )
    )

    remarkforadmin: list[str] = Field(default_factory=list,
        description=(
            "Up to 10 short bullet statements for internal use only. "
            "Include any relevant information that may you help future analysis."
            "Use an empty list when none are relevant."
            "Are there problems in the prompt, provided data or anything?"
            "how can we help you improve the prompt or the data to get better results?"
        )
    )   


class InteractionAnalysis_LEGACY(BaseModel):
    geometric_interaction: list[str] = Field(min_length=1, description="Geometric contacts, approaches and final interfaces between the existing assembly and joining instances. In max. 5 bullets.")
    positioning_possibilities: list[str] = Field(min_length=1, description="Feasible fixture orientations for the existing assembly and their geometric support. In max. 2 bullets.")
    accuracy_of_target_position: list[str] = Field(min_length=1, description="Evidence-based translational and rotational accuracy requirements and consequences of misalignment. In max. 2 bullets.")
    positioning_aids: list[str] = Field(min_length=1, description="Chamfers, shoulders, tapers, guide surfaces, stops and other alignment features. In max. 3 bullets.")
    additional_orientation_by_rotation: list[str] = Field(min_length=1, description="Required angular orientation, rotational symmetry and features enforcing clocking. In max. 2 bullets.")
    joining_tolerances: list[str] = Field(min_length=1, description="Likely fit relationship, sensitivity and tolerance uncertainty without unsupported numerical invention. In max. 1 bullets.")
    accessibility_to_joining_position: list[str] = Field(min_length=1, description="Approach directions, visibility, tool clearance and obstructions at this sequence state. In max. 1 bullets.")
    joining_motion: list[str] = Field(min_length=1, description="Required insertion or joining trajectory and constrained degrees of freedom. In max. 2 bullets.")
    stability_in_positioned_state: list[str] = Field(min_length=1, description="Stability and self-holding behavior before permanent fixing. In max. 2 bullets.")
    feeding_of_joining_element: list[str] = Field(min_length=1, description="Any auxiliary fastener, adhesive, lubricant or other process element; the joining part itself is excluded. In max. 1 bullets.")
    fixing_of_mounted_part: list[str] = Field(min_length=1, description="Likely fixing process and geometry-driven automation implications. In max. 5 bullets.")


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
