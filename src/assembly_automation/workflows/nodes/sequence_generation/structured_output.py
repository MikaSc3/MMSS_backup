"""Structured assembly-sequence contract."""

from pydantic import BaseModel, Field, field_validator

class AssemblyStep(BaseModel):
    step_id: int = Field(ge=1, description="Consecutive one-based execution order.")
    step_description: str = Field(min_length=1, description="One concise sentence describing the physical operation.")
    belongs_to: str = Field(min_length=1, description="Main assembly or named subassembly context.")
    base_part: str | None = Field(default=None, description="Previously introduced instance_id serving as base; null for initial placement.")
    joining_part: str | list[str] = Field(description="One or more instance_id values introduced by this step.")
    joining_process: str = Field(min_length=1, description="Manufacturing operation such as Place, Insert, Screw or Press-fit.")

    @field_validator("joining_part")
    @classmethod
    def joining_parts_are_nonempty(cls, value):
        values = [value] if isinstance(value, str) else value
        if not values or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError("joining_part must contain nonempty instance IDs")
        if len(set(values)) != len(values):
            raise ValueError("joining_part cannot repeat an instance ID in one step")
        return value

class AssemblySequence(BaseModel):

    assembly_description: list[str] = Field(
        description=(
            "Detailed assembly process description, including subassemblies and overall strategy."
            "Target no more than 20 words per bullet."
        )
    )

    sequence_rationale: list[str] = Field(
        description=(
            "Up to 4 compact bullets using 'Constraint: decision'. "
            "Explain the decisive base selection, precedence, access, "
            "or support requirements. Include subassembly justification "
            "only when relevant. Avoid narrating the steps."
        )
    )

    sequence_notation: str = Field(
        min_length=1,
        description=(
            "Compact composition tree using exact instance IDs. "
            "Format: assembly[instance_a,instance_b,...] or "
            "assembly[SA1[instance_a,instance_b],instance_c,...]. "
            "Each physical instance appears once. "
            "Shows composition, not execution order."
        )
    )

    steps: list[AssemblyStep] = Field(
        min_length=1,
        description=(
            "Consecutive physical operations. Introduce every BOM instance "
            "exactly once. Each description starts with an action verb and "
            "states the relevant target, direction, or final seating condition. "
            "Target 8–20 words per description."
        )
    )

    assumptions: list[str] = Field(default_factory=list,
        description=(
            "Up to 5 compact bullets identifying consequential unverified "
            "premises affecting insertion, joining, access, or support. "
            "State premises directly; avoid generic caveats. "
            "Use an empty list when none are consequential."
        )
    )

    @field_validator("assembly_description", "sequence_rationale", mode="before")
    @classmethod
    def legacy_text_becomes_one_bullet(cls, value):
        """Keep saved v1 string fields usable after their list migration."""
        return [value] if isinstance(value, str) else value

class AssemblySequence_LEGACY(BaseModel):
    assembly_name: str = Field(min_length=1)
    assembly_description: str = Field(min_length=1, description="Assembly-process-focused description.")
    sequence_rationale: str = Field(min_length=1, description="Why the order is feasible, stable and accessible.")
    sequence_notation: str = Field(min_length=1, description="Compact assembly/subassembly notation.")
    steps: list[AssemblyStep] = Field(min_length=1)


SCHEMAS = {"assembly_sequence_v1": AssemblySequence}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown sequence-generation schema: {schema_id}") from exc
