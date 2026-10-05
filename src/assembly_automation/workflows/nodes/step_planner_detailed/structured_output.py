"""One selected detailed automation realization for one assembly step."""

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class AutomationPlannerMeasure(BaseModel):
    name: str = Field(
        description="Short measure name, maximum 4 words."
    )

    beschreibung: str = Field(
        description=(
            "One short action addressing a consequential unresolved condition. "
            "Do not repeat normal operations or equipment specifications."
        )
    )

    verantwortlich: str = Field(
        description=(
            "Implementation owner, such as Mechanical design, "
            "Controls engineering, Process engineering, or Production."
        )
    )


class AutomationPlannerEquipment(BaseModel):
    name: str = Field(
        description=(
            "Concrete equipment type that would be required for this step. "
            "Reuse supplied names where applicable. No supplier model guesses."
        )
    )

    function: str = Field(
        description="How will the equipment be used in this step? One short action-led description."
    )

    step_id: int = Field(
        ge=1,
        description="Must equal montageschritt_nr."
    )

    specimen: list[str] = Field(
        max_length=2,
        description=(
            "Up to two short technical bullets: contact geometry, tooling, "
            "motion, or sensing features decisive for this step. "
            "No unsupported numerical specifications. "
            "Empty when no additional characteristics are needed."
        )
    )


class AutomationPlannerSubprozess(BaseModel):
    ausfuehrung: Literal[
        "manuell",
        "automatisiert",
        "manuell_mit_technischer_unterstuetzung",
        "nicht_erforderlich",
    ] = Field(
        description="Selected execution mode for this subprocess."
    )

    loesung: str = Field(
        description=(
            "One short action-led realization, normally 6–16 words. "
            "Describe the action and target; keep equipment details elsewhere. "
            "For nicht_erforderlich, state the reason briefly."
        )
    )

    equipment_names: list[str] = Field(
        description=(
            "Exact names of equipment entries used by this subprocess. "
            "Empty when none are used."
        )
    )


class AutomationPlannerSubprozesse(BaseModel):
    vereinzelung: AutomationPlannerSubprozess = Field(
        description="Separation and individual presentation of the joining instances."
    )
    handhabung: AutomationPlannerSubprozess = Field(
        description="Acquisition, movement, and orientation of the joining instances."
    )
    positionierung: AutomationPlannerSubprozess = Field(
        description="Location and support of base and joining instances for joining."
    )
    fuegen: AutomationPlannerSubprozess = Field(
        description="Physical assembly operation that establishes the intended connection."
    )

    pruefen: AutomationPlannerSubprozess | None = Field(
        default=None,
        description=(
            "Include only for a specific necessary verification. Otherwise null."
        )
    )

    uebergeben: AutomationPlannerSubprozess = Field(
        description="Release, retention, or handover of the resulting assembly state."
    )


class DetailedStepPlan(BaseModel):
    montageschritt_nr: int = Field(
        ge=1,
        description="Current assembly step ID."
    )

    basisteil: str | None = Field(
        default=None,
        description="Exact base instance_id from the supplied assembly step."
    )

    fuegeteil: str | list[str] = Field(
        description="Exact joining instance_id values from the supplied step."
    )

    bereitstellungsart: str = Field(
        description="Short provisioning mode used for this step."
    )

    bereitstellungsstatus: Literal[
        "vorgegeben",
        "planungsannahme",
    ] = Field(
        description="Whether provisioning is supplied or selected as an assumption."
    )

    strategie: Literal[
        "manuell",
        "halbautomatisiert",
        "vollautomatisiert",
    ] = Field(
        description=(
            "Overall strategy consistent with routine subprocess execution "
            "and the accepted global concept."
        )
    )

    subprozesse: AutomationPlannerSubprozesse = Field(
        description="Selected realization for every subprocess of this assembly step."
    )

    equipment: list[AutomationPlannerEquipment] = Field(
        default_factory=list,
        description=(
            "Equipment used in this step, each distinct item listed once. "
            "Referenced by exact name from subprocesses."
        )
    )

    massnahmen: list[AutomationPlannerMeasure] = Field(
        default_factory=list,
        max_length=2,
        description=(
            "Only consequential unresolved implementation actions. "
            "Empty when normal operations and selected equipment suffice."
        )
    )

    @model_validator(mode="after")
    def validate_equipment(self):
        if any(
            item.step_id != self.montageschritt_nr
            for item in self.equipment
        ):
            raise ValueError(
                "Every equipment step_id must equal montageschritt_nr"
            )

        names = [item.name for item in self.equipment]
        if len(names) != len(set(names)):
            raise ValueError("Equipment names must be unique within this step")

        referenced = set()
        for subprocess in (
            self.subprozesse.vereinzelung,
            self.subprozesse.handhabung,
            self.subprozesse.positionierung,
            self.subprozesse.fuegen,
            self.subprozesse.pruefen,
            self.subprozesse.uebergeben,
        ):
            if subprocess is not None:
                referenced.update(subprocess.equipment_names)

        if referenced != set(names):
            raise ValueError(
                "Equipment entries and subprocess references must match"
            )

        return self


SCHEMAS = {"detailed_step_plan_v1": DetailedStepPlan}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown detailed-step-planner schema: {schema_id}") from exc

