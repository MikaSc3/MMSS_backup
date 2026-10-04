"""FFA classification contract preserving the established scoring values."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NatureOfProvision(str, Enum):
    MAGAZINE_DEFINED = "in magazine (defined position and orientation)"
    MAGAZINE_UNDEFINED = "in magazine (without defined position or orientation)"
    MAGAZINE_PACKAGING_ISSUES = "in magazine (packaging issues: individual packaging or sticky intermediate layer)"
    MAGAZINE_NON_STICKY = "in magazine (with non-sticky intermediate layer)"
    BULK_EASY_AUTOMATED = "bulk cargo (easy to automated: e.g. spiral conveyors)"
    BULK_BIN_PICKING = "bulk cargo (automation with bin picking)"
    BULK_NO_AUTOMATION = "bulk cargo (no automation possible: e.g. risk of catching)"


class PartRigidity(str, Enum):
    RIGID = "rigid"
    ELASTIC = "elastic"
    FLEXIBLE = "flexible"


class GrippingAreas(str, Enum):
    PRONOUNCED = "pronounced gripping area existing"
    SMALL = "small gripping area existing"
    NONE = "no defined gripping area existing"


class OrientationFeatures(str, Enum):
    SELF_ADJUSTMENT = "mechanical self-adjustement in gripper possible"
    OPTICAL_MEASUREMENT = "optical measurement in part delivery necessary"
    ALIGNING_STATION = "seperate aligning station necessary"
    NO_REFERENCE = "no reference points for orientation"


class SurfaceSensibility(str, Enum):
    IMMUNE = "immune"
    SENSITIVE = "easily scratched, easily broken, easily defomed"


class AccuracyOfTargetPosition(str, Enum):
    BOTH_DEFINED = "base part position defined / joining point position defined"
    BASE_DEFINED_JOINING_TOLERANCE = "base part position defined / joining point position with tolerance"
    BASE_TOLERANCE_JOINING_DEFINED = "base part position with tolerance / joining point position defined"
    BOTH_TOLERANCE = "base part position with tolerance / joining point position with tolerance"


class PositioningAids(str, Enum):
    CHAMFERS_AND_STOPS = "insertion chamfers and stopping edge"
    CHAMFERS_ONLY = "insertion chamfers"
    STOPS_ONLY = "stopping edges"
    NO_AIDS = "no positioning aids"


class AdditionalOrientation(str, Enum):
    NOT_REQUIRED = "not required"
    MECHANICAL_GUIDANCE = "mechanical guidance"
    OPTICAL_INFORMATION = "optical information necessary"
    NOT_FEASIBLE = "required but not feasible"


class Accessibility(str, Enum):
    VISIBILITY_AND_CLEARANCES = "visibility given / tool clearances given"
    NO_VISIBILITY_CLEARANCES = "no visibility / tool clearances given"
    VISIBILITY_NO_CLEARANCES = "visibility given / no tool clearances"
    BLOCKED = "no visibility / no tool clearances (e.g. blocked by cables, hoses etc.)"


class PositioningMotion(str, Enum):
    LINEAR = "linear joining motion"
    PATH_MOTION = "path motion necessary"
    SENSOR_GUIDED = "sensor-guided (linear/path)"


class PositioningTolerances(str, Enum):
    PLUS_MINUS_X_MM = "+/- x mm"
    PLUS_MINUS_0X_MM = "+/- 0.x mm"
    ZERO_CLEARANCE = "0 clearance"
    ADJUSTMENT_REQUIRED = "adjustment of end position after assembly required"


class Stability(str, Enum):
    STABLE_SELF_HOLDING = "stable, self-holding"
    HOLDING_REQUIRED = "holding during joining process required"


class FeedingOfJoiningElement(str, Enum):
    NOT_NECESSARY = "not necessary"
    STANDARD_SOLUTION = "automatable with standard solution"
    LIMITED_FEEDING = "limited feeding (e.g. accessibility)"
    SPECIAL_DEVELOPMENT = "automatable with special development"
    NOT_FORESEEABLE = "special development, not foreseeable"


class FixingOfMountedPart(str, Enum):
    STANDARD_SOLUTION = "automatable with standard solution"
    SPECIAL_DEVELOPMENT = "automatable with special development"
    NOT_FORESEEABLE = "special development, not foreseeable"


class SeparationAssessment(BaseModel):
    nature_of_provision_reasoning: str = Field(min_length=1, description="Reasoning for the nature of provision assessment. max. 2 bullets.")
    nature_of_provision: NatureOfProvision
    automatable_reasoning: str = Field(min_length=1, description="Reasoning for the overall automation potential of this step. High, Medium, Low: then one sentence.")



class HandlingAssessment(BaseModel):

    rigidity_reasoning: str = Field(min_length=1, description="Reasoning for the part rigidity assessment. max. 2 bullets.")
    part_rigidity: PartRigidity
    gripping_reasoning: str = Field(min_length=1, description="Reasoning for the gripping areas assessment. max. 2 bullets.")
    gripping_areas: GrippingAreas
    orientation_reasoning: str = Field(min_length=1, description="Reasoning for the orientation features assessment. max. 2 bullets.")
    orientation_features: OrientationFeatures
    surface_reasoning: str = Field(min_length=1, description="Reasoning for the surface sensibility assessment. max. 2 bullets.")
    surface_sensibility: SurfaceSensibility
    automatable_reasoning: str = Field(min_length=1, description="Reasoning for the overall automation potential of this step. High, Medium, Low: then one sentence.")



class PositioningAssessment(BaseModel):

    accuracy_reasoning: str = Field(min_length=1, description="Reasoning for the accuracy of target position assessment. max. 2 bullets.")
    accuracy_of_target_position: AccuracyOfTargetPosition
    positioning_aids_reasoning: str = Field(min_length=1, description="Reasoning for the positioning aids assessment. max. 2 bullets.")
    positioning_aids: PositioningAids
    orientation_reasoning: str = Field(min_length=1, description="Reasoning for the additional orientation by rotation assessment. max. 2 bullets.")
    additional_orientation_by_rotation: AdditionalOrientation    
    tolerances_reasoning: str = Field(min_length=1, description="Reasoning for the positioning tolerances assessment. max. 2 bullets.")
    positioning_tolerances: PositioningTolerances
    motion_reasoning: str = Field(min_length=1, description="Reasoning for the positioning motion assessment. max. 2 bullets.")
    positioning_motion: PositioningMotion
    accessibility_reasoning: str = Field(min_length=1, description="Reasoning for the accessibility to joining position assessment. max. 2 bullets.")
    accessibility_to_joining_position: Accessibility    
    stability_reasoning: str = Field(min_length=1, description="Reasoning for the stability in positioned state assessment. max. 2 bullets.")
    stability_in_positioned_state: Stability
    automatable_reasoning: str = Field(min_length=1, description="Reasoning for the overall automation potential of this step. High, Medium, Low: then one sentence.")



class JoiningAssessment(BaseModel):
    feeding_reasoning: str = Field(min_length=1, description="Reasoning for the feeding of joining element assessment. max. 2 bullets.")
    feeding_of_joining_element: FeedingOfJoiningElement
    fixing_reasoning: str = Field(min_length=1, description="Reasoning for the fixing of mounted part assessment. max. 2 bullets.")
    fixing_of_mounted_part: FixingOfMountedPart
    automatable_reasoning: str = Field(min_length=1, description="Reasoning for the overall automation potential of this step. High, Medium, Low: then one sentence.")



class OverallFFA(BaseModel):
    subprocess: Literal["separation", "handling", "positioning", "joining"]
    automation_potential: str = Field(min_length=1)
    risks: str = Field(min_length=1)


class Drawback(BaseModel):
    drawback_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    improvement_measure: str = Field(min_length=1)


class PartDrawbacks(BaseModel):
    part_id: str = Field(min_length=1)
    drawbacks: list[Drawback] = Field(min_length=1, max_length=3)


class AssemblyDrawbacks(BaseModel):
    drawbacks: list[Drawback] = Field(min_length=1, max_length=3)


class FFAAssessment(BaseModel):
    separation: SeparationAssessment
    handling: HandlingAssessment
    positioning: PositioningAssessment
    joining: JoiningAssessment
    overall_ffa: list[OverallFFA] = Field(min_length=4, max_length=4)
    design_drawbacks_base_part: list[PartDrawbacks]
    design_drawbacks_joining_parts: list[PartDrawbacks] = Field(min_length=1)
    design_drawbacks_assembly: list[AssemblyDrawbacks] = Field(min_length=1)

    @field_validator("overall_ffa")
    @classmethod
    def all_subprocesses_once(cls, value):
        names = [item.subprocess for item in value]
        expected = {"separation", "handling", "positioning", "joining"}
        if set(names) != expected or len(names) != len(set(names)):
            raise ValueError("overall_ffa must contain each subprocess exactly once")
        return value


SCHEMAS = {"ffa_assessment_v1": FFAAssessment}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown FFA assessment schema: {schema_id}") from exc
