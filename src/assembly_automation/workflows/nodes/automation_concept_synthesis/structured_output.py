"""Structured contract for the consolidated automation equipment list."""

from pydantic import BaseModel, Field


class AutomationEquipment(BaseModel):
    name: str = Field(
        min_length=1,
        description=(
            "Concrete equipment name consolidated from the detailed step plans. "
            "Equivalent shared equipment is represented once under one stable name."
        ),
    )
    step_ids: list[int] = Field(
        min_length=1,
        description=(
            "Assembly step IDs served by this equipment, deduplicated and ordered."
        ),
    )
    specimen: list[str] = Field(
        default_factory=list,
        description=(
            "Consolidated technical characteristics required across the referenced steps. "
            "Preserve consequential contact, tooling, motion, sensing, and safety details."
        ),
    )


class AutomationEquipmentList(BaseModel):
    equipment: list[AutomationEquipment] = Field(
        description=(
            "Station-independent equipment list consolidated from all detailed step plans."
        ),
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description=(
            "Material conflicts or unresolved contradictions between detailed plans that "
            "must be resolved before layout or procurement."
        ),
    )


SCHEMAS = {"automation_equipment_list_v1": AutomationEquipmentList}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown automation-concept-synthesis schema: {schema_id}") from exc
