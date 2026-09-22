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
