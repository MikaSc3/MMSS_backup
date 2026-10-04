"""One selected detailed automation realization for one assembly step."""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class AutomationPlannerMeasure(BaseModel):
    name: Optional[str] = Field(None, description="Short name max 4 words that describes the measure")
    beschreibung: str = Field(..., description="Concise description of what risk is adressed and the technical, organizational, or manual measure.")
    verantwortlich: str = Field(..., description="Responsible role or department for implementing this measure. (Worker, Fixture design, Sensor, Robot, ...)")


class AutomationPlannerEquipment(BaseModel):
    name: str = Field(..., description="Concrete equipment name, as specific as possible. (6DOF-Robot, Linear Axis, Worker, Fixture, Scara, Gripper-partX, an other standard or custom equipment)")
    function: str = Field(..., description="Main task of the equipment in the process. Position, Hold, Align, Rotate, Feed, Inspect, Transport, e.g. Handling part 001 main housing from tray into fixture only use where task is not self explanatory from the name of the equipment. e.g. gripperpart001 is clear")
    step_id: int = Field(..., ge=1, description="Assembly step number in which this equipment is required.")
    specimen: str = Field(..., description="If applicable, specify technical specimen like special sensors, geometry or whatever based on the ablaufbeschreibung. e.g. 2 sensors for positioning of part 001 in fixture")


class AutomationPlannerSubprozess(BaseModel):
    ausfuehrung: Literal[
        "manuell",
        "automatisiert",
        "manuell_mit_technischer_unterstuetzung",
        "nicht_erforderlich",
    ] = Field(..., description="Execution mode selected for this subprocess.")
    loesung: str = Field(..., description="Bullet points describing the technical realization of this subprocess. If manual, describe the human action. If automated, describe the technical solution.")


class AutomationPlannerSubprozesse(BaseModel):
    vereinzelung: AutomationPlannerSubprozess = Field(..., description="Separation/provisioning subprocess concept.")
    handhabung: AutomationPlannerSubprozess = Field(..., description="Handling subprocess concept.")
    positionierung: AutomationPlannerSubprozess = Field(..., description="Positioning subprocess concept.")
    fuegen: AutomationPlannerSubprozess = Field(..., description="Joining/fixing subprocess concept.")
    pruefen: Optional[AutomationPlannerSubprozess] = Field(None, description="Optional inspection or verification subprocess. Only include if uncertainty, quality relevance, or technical risk makes an inspection necessary.")
    uebergeben: AutomationPlannerSubprozess = Field(..., description="Handover to the next state, station, or operator.")


class DetailedStepPlan(BaseModel):
    montageschritt_nr: int = Field(..., description="Assembly step number this result belongs to.")
    montageschritt_beschreibung: str = Field(..., description="Short assembly-step description.")
    basisteil: Optional[str] = Field(None, description="Base part id or name for this step, if present.")
    fuegeteil: Union[str, List[str]] = Field(..., description="Joining part id, name, or list of joining parts for this step.")
    bestaetigte_bereitstellungsart: str = Field(..., description="Provisioning mode used as planning assumption.")
    strategie: Literal["manuell", "halbautomatisiert", "vollautomatisiert"] = Field(..., description="Automation strategy selected for this assembly step based on the global automation idea.")
    subprozesse: AutomationPlannerSubprozesse = Field(..., description="One selected execution concept for the required subprocesses, guided by the global automation idea.")
    massnahmen: List[AutomationPlannerMeasure] = Field(default_factory=list, description="Key measures required to make this step realization robust.")
    equipment: List[AutomationPlannerEquipment] = Field(default_factory=list, description="Based on the selected subprocess solutions, list the concrete equipment required for this assembly step. Use one entry for each distinct equipment item and keep its step_id equal to montageschritt_nr.")
    entscheidungsbegruendung: str = Field(..., description="Concise justification showing how the selected realization follows the global automation idea and addresses the corresponding FfA findings.")

    @model_validator(mode="after")
    def equipment_belongs_to_this_step(self):
        mismatched = [item.step_id for item in self.equipment if item.step_id != self.montageschritt_nr]
        if mismatched:
            raise ValueError("Every equipment step_id must equal montageschritt_nr")
        return self


SCHEMAS = {"detailed_step_plan_v1": DetailedStepPlan}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown detailed-step-planner schema: {schema_id}") from exc
