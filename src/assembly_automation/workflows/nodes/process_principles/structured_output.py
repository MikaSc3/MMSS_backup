from typing import Literal
from pydantic import BaseModel, Field, field_validator

ExecutionMode = Literal["manual", "assisted", "automated", "not_required"]
Subprocess = Literal["separation", "handling", "positioning", "joining", "inspection", "transfer"]

class EquipmentRequirement(BaseModel):
    requirement_id: str = Field(pattern=r"^eqr_[a-z0-9_]+$")
    name: str = Field(min_length=1)
    function: str = Field(min_length=1)
    specifications: list[str] = Field(default_factory=list)

class SubprocessPlan(BaseModel):
    subprocess: Subprocess
    execution_mode: ExecutionMode
    technical_solution: list[str] = Field(min_length=1, max_length=6)
    actor_or_equipment_functions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    required_measures: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)

class StepAutomationPlan(BaseModel):
    step_id: int = Field(ge=1)
    process_objective: str = Field(min_length=1)
    subprocesses: list[SubprocessPlan] = Field(min_length=6, max_length=6)
    equipment_requirements: list[EquipmentRequirement] = Field(default_factory=list)
    interface_requirements: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("subprocesses")
    @classmethod
    def all_subprocesses_once(cls, value):
        names = [item.subprocess for item in value]
        expected = {"separation", "handling", "positioning", "joining", "inspection", "transfer"}
        if set(names) != expected or len(names) != len(set(names)):
            raise ValueError("subprocesses must contain all six subprocesses exactly once")
        return value

SCHEMAS = {"step_automation_plan_v1": StepAutomationPlan}

def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown process-principles schema: {schema_id}") from exc
