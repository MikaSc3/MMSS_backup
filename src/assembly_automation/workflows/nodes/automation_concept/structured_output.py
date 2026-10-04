from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field




# Shared helper schema used in multiple automation_planner output folders.
class AutomationPlannerMeasure(BaseModel):

    name: Optional[str] = Field(None, description="Short name max 4 words that describes the measure")
    beschreibung: str = Field(..., description="Concise description of what risk is adressed and the technical, organizational, or manual measure.")
    verantwortlich: str = Field (..., description="Responsible role or department for implementing this measure. (Worker, Fixture design, Sensor, Robot, ...)")


# Shared helper schema used mainly in 02_prozessprinzipien and downstream station outputs.
class AutomationPlannerEquipment(BaseModel):
    bezeichnung: str = Field(..., description="Concrete equipment name, as specific as possible. (Robot, Worker, Fixture, Scara, Gripper-partX, ...)")
    funktion: str = Field(..., description="Main technical function of the equipment in the process.")



# Output folder: automation_planner/01_initiale_anforderungsklaerung.json
class InitialeAnforderungMontageschritt(BaseModel):
    montageschritt_nr: int = Field(..., description="Assembly step number from assembly_sequence.json.")
    beschreibung: str = Field(..., description="Short assembly-step description.")
    basisteil: Optional[str] = Field(None, description="Base part id or name for this assembly step, if present.")
    fuegeteil: Union[str, List[str]] = Field(..., description="Joining part id, name, or list of joining parts for this assembly step.")
    angenommene_bereitstellungsart: str = Field(..., description="Assumed part-provisioning mode, preferably derived from FfA separation classification.")
    qualitative_ffa: Literal["hoch", "mittel", "gering", "unklar"] = Field(..., description="Qualitative FfA level for this step, taken from the FfA report.")
    risks: List[str] = Field(default_factory=list, description="Most important risks that need to be addressed.")


# Main output schema for automation_planner/01_initiale_anforderungsklaerung.json
class InitialeAnforderungsklaerung(BaseModel):
    baugruppenname: str = Field(..., description="Assembly name.")
    montageschritte: List[InitialeAnforderungMontageschritt] = Field(..., description="User-reviewable initial requirements per assembly step.")
    offene_fragen: List[str] = Field(default_factory=list, description="Open questions that should be clarified before detailed planning.")


# Output folder: automation_planner/02_prozessprinzipien/step_{montageschritt_nr}_prozessprinzipien.json
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


class Prozessprinzip(BaseModel):
    strategie: Literal["manuell", "halbautomatisiert", "vollautomatisiert"] = Field(..., description="Automation strategy for this process principle.")
    subprozesse: AutomationPlannerSubprozesse = Field(..., description="Execution concept for the required subprocesses.")
    massnahmen: List[AutomationPlannerMeasure] = Field(default_factory=list, description="Key measures required to make this process principle robust.")
    equipment: List[AutomationPlannerEquipment] = Field(default_factory=list, description="Required core equipment, tools etc.")



# Main output schema for automation_planner/02_prozessprinzipien/step_{montageschritt_nr}_prozessprinzipien.json
class ProzessprinzipErgebnis(BaseModel):
    montageschritt_nr: int = Field(..., description="Assembly step number this result belongs to.")
    montageschritt_beschreibung: str = Field(..., description="Short assembly-step description.")
    basisteil: Optional[str] = Field(None, description="Base part id or name for this step, if present.")
    fuegeteil: Union[str, List[str]] = Field(..., description="Joining part id, name, or list of joining parts for this step.")
    bestaetigte_bereitstellungsart: str = Field(..., description="Provisioning mode used as planning assumption.")
    prozessprinzipien: List[Prozessprinzip] = Field(..., description="Exactly three process principles: manual, semi-automated, and fully automated.")


# Output folder: automation_planner/03_automatisierungsvarianten/variante_{strategie}.json
class MontageablaufEintrag(BaseModel):
    montageschritt_nr: int = Field(..., description="Referenced assembly step number.")
    beschreibung: List[str] = Field(..., description="Technical bullet points for this assembly step, structured by the subprocess logic: Separation, Handling, Positioning, Joining, optional Inspection, and Transfer. Keep all content in English, concise, and engineering-focused.")
    anforderungen: List[str] = Field(..., description="Describing the required technical, organizational, and logistical requirements for this assembly step. Include fixtures, tools, sensors, equipment, worker, and transfer constraints only where relevant.")


class EintragEquipment(BaseModel):
    name: str = Field(..., description="Concrete equipment name, as specific as possible. (6DOF-Robot, Linear Axis, Worker, Fixture, Scara, Gripper-partX, an other standard or custom equipment)")
    function: str = Field(..., description="Main task of the equipment in the process. Position, Hold, Align, Rotate, Feed, Inspect, Transport, e.g. Handling part 001 main housing from tray into fixture only use where task is not self explanatory from the name of the equipment. e.g. gripperpart001 is clear"   )
    step_id: int = Field(..., ge=1, description="Assembly step number in which this equipment is required.")
    specimen: str = Field(..., description="If applicable, specify technical specimen like special sensors, geometry or whatever based on the ablaufbeschreibung. e.g. 2 sensors for positioning of part 001 in fixture")
    quantity: int = Field(..., description="Quantity of the equipment in the station.")


class EquipmentCoordinate(BaseModel):
    equipment_name: str = Field(..., description="Equipment name matching an entry in equipment_station.")
    x: int = Field(..., description="X-coordinate of the equipment center relative to the station origin, in cm.")
    y: int = Field(..., description="Y-coordinate of the equipment center relative to the station origin, in cm.")


class StationCoordinate(BaseModel):
    station_nr: int = Field(..., description="Station number matching an entry in stationen.")
    x: int = Field(..., description="X-coordinate of the station center relative to the layout origin, in cm.")
    y: int = Field(..., description="Y-coordinate of the station center relative to the layout origin, in cm.")


class AutomatisierungsKonzeptStation(BaseModel):
    station_nr: int = Field(..., description="Stable station number within this automation concept.")
    zustand_baugruppe_vor_station: str = Field(..., description="State of the assembly before this station starts. In bullet Points.")
    ablaufbeschreibung: List[str] = Field(..., description="Describe assembly process within the station using single actions. Cover assigned assembly steps using the subprocess logic, human-machine split, material handover. For each action: Ask yourself: Who or what performs the action? What is the action? What is the result?")
    zustand_baugruppe_nach_station: str = Field(..., description="State of the assembly, orientation and other important info for handover / transfer after this station is completed. 3 bullet Points.")
    equipment_station: List[EintragEquipment] = Field(default_factory=list, description="Based on the ablaufbeschreibung, list the equipment required in this station, including quantity. Think of basic safety equipment. You are allowed to combine multiple equipment into one entry (sensors belonging to a fixture, gripper and robot, ...). If you do so, describe the combined equipment in the specimen field. Bullet Points.")


class Parallelisierung(BaseModel):
    reasoning: str = Field(..., description="Which of the single process steps could be done in parallel? Think about technical feasibility. Is there a efficient way to split up machine and human tasks? How can the assembly or subassembly be parallelized? Describe the parallelization method, orientation, and any special requirements or equipment needed for handover. Even if we have only one station. How could we split up single processes to enable a parallelization?")
    parellization_equipment: List[EintragEquipment] = Field(default_factory=list, description="Based on your parallelization reasoning, list the additionalequipment required for parallelization, including quantity. Think of basic safety equipment")
    

# Main output schema for automation_planner/03_automatisierungsvarianten/variante_{strategie}.json
class AutomatisierungsGesamtkonzept(BaseModel):
    varianten_id: str = Field(..., description="Identifier for this automation concept variant. Based on assembly name and strategy.")
    strategie: Literal["manuell", "halbautomatisiert", "vollautomatisiert"] = Field(..., description="Automation strategy represented by this concept.")
    montageablauf: List[MontageablaufEintrag] = Field(..., description="Overall assembly flow in binding assembly order.")
    challenge: List[str] = Field(..., description="Challenge yourself real quick. Are all parts and assembly steps covered in the ablaufbeschreibung? Are there any missing steps or missing parts? If so: make a remark whats missing so u can check it later. Bullet Points.")
    stationen: List[AutomatisierungsKonzeptStation] = Field(..., description="After you thought about the assembly flow and have the remarks. Plan the stations of the layout. High-level station structure for this overall automation concept in process order.")
    stationen_transfer: str = Field(..., description="Based on the stations, how is the assembly or subassembly transferred between stations? Describe the transfer method, orientation, and any special requirements for handover. if we have only one station N/A")
    parallelisierungskonzept: Parallelisierung = Field(..., description="Based on the stations, how can the assembly or subassembly be parallelized? ")

SCHEMAS = {"automation_concept_v1": AutomatisierungsGesamtkonzept}

def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown automation-concept schema: {schema_id}") from exc
