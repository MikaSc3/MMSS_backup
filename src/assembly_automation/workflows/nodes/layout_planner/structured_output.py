from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EquipmentClass = Literal[
    "robot", "fixture", "feeder", "conveyor", "workstation", "storage",
    "inspection", "safety", "operator", "tool", "hmi", "other",
]


class EquipmentPlacement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    name: str = Field(min_length=1, description="Equipment name copied verbatim from the automation concept.")
    equipment_class: EquipmentClass = Field(alias="class",
        description="Rendering class: robot, fixture, feeder, conveyor, workstation, storage, inspection, safety, operator, tool, hmi, or other.")
    x: int = Field(description="Horizontal center coordinate in centimetres; positive values point right.")
    y: int = Field(description="Vertical center coordinate in centimetres; positive values point upward/back in the top view.")
    size: float | None = Field(
        default=None, gt=0,
        description="Optional square footprint side length in centimetres. Use the same value for X and Y; omit only when the class default is appropriate.",
    )


class EquipmentLayout(BaseModel):
    equipment: list[EquipmentPlacement] = Field(
        min_length=1,
        description="Exactly one placement for every distinct equipment item in the automation concept.")


SCHEMAS = {"layout_planner_v1": EquipmentLayout}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown layout-planner schema: {schema_id}") from exc
