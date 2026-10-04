from typing import Literal

from pydantic import BaseModel, Field


class EquipmentPriceMatch(BaseModel):
    equipment_name: str = Field(description="Equipment name copied verbatim from the layout list.")
    catalogue_id: str | None = Field(description="Exact catalogue_id of the selected row, or null when no defensible match exists.")
    quantity: int = Field(ge=1, description="Required quantity copied from the automation concept; use 1 when the concept provides no quantity.")
    match_confidence: Literal["high", "medium", "low", "unmatched"] = Field(description="Confidence that the catalogue row represents the required equipment.")
    matching_reasoning: str = Field(description="Brief explanation based on equipment class, function, specimen, manufacturer, and model; never invent price information.")


class EquipmentPriceMatches(BaseModel):
    matches: list[EquipmentPriceMatch] = Field(min_length=1, description="Exactly one match decision for every equipment name in the layout list.")


SCHEMAS = {"cost_planner_matches_v1": EquipmentPriceMatches}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown cost-planner schema: {schema_id}") from exc
