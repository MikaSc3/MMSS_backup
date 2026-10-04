
from typing import List, Literal

from pydantic import BaseModel, Field

from assembly_automation.workflows.nodes.automation_concept.structured_output import (
    EquipmentCoordinate,
    StationCoordinate,
)


# Output folder: automation_planner/03a_layoutplanung/layout_{strategie}.json
class LayoutPlanerStation(BaseModel):
    station_nr: int = Field(..., description="Station number matching the source automation concept.")
    station_layout: str = Field(..., description="Top-view description of the physical arrangement of all equipment in this station, including operator and material access where applicable.")
    equipment_coordinates: List[EquipmentCoordinate] = Field(..., description="Exactly one coordinate entry for every equipment_station row. Preserve each equipment name verbatim. Coordinates are equipment center points in cm relative to the station origin.")


class LayoutPlanerErgebnis(BaseModel):
    varianten_id: str = Field(..., description="Variant identifier matching the source automation concept.")
    strategie: Literal["manuell", "halbautomatisiert", "vollautomatisiert"] = Field(..., description="Automation strategy matching the source automation concept.")
    stationen: List[LayoutPlanerStation] = Field(..., description="Exactly one layout entry for every station in the source automation concept.")
    layout_gesamt: str = Field(..., description="Top-view description of how all stations are arranged relative to one another, consistent with station transfer and material flow.")
    station_coordinates: List[StationCoordinate] = Field(..., description="Exactly one coordinate entry for every station. Coordinates are station origin points in cm relative to station 1 at 0,0.")


SCHEMAS = {"layout_planning_v1": LayoutPlanerErgebnis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown layout-planning schema: {schema_id}") from exc
