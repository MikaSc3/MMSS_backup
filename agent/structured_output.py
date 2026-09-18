"""
Structured Output Models für APA_from_CAD.

Pydantic BaseModels für Assembly, Monopart und FFA Analysen.
Diese definieren die erwarteten JSON-Strukturen vom LLM.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal, Union, Tuple

from pydantic import BaseModel, Field


# ============================================================================
# LEGACY MODELS (können später entfernt werden)
# ============================================================================

class TopicInfo(BaseModel):
    name: str
    relevance: str
    destription: str
    Important_for: list[str]


class Math(BaseModel):
    task: str
    answer: float


class PictureItem(BaseModel):
    pic_name: str
    description: str
    important_facts: List[str]


class Visible_Parts(BaseModel):
    potential_name: str
    color: str
    quantity: int
    important_design_features: List[str]


class PictureAnalysis(BaseModel):
    pictures: List[PictureItem]
    parts: List[Visible_Parts]


# ============================================================================
# CURRENT MODELS (Master aus tools.py)
# ============================================================================

class CertaintyItem(BaseModel):
    """Certainty/Confidence für eine Aussage."""
    topic: str
    level: float  # 0.0 - 1.0 (keine ge/le-Constraint im Schema)


class PartOverview(BaseModel):
    """Part-Übersicht aus Assembly-Kontext."""
    name: str
    color: Optional[str] = None
    quantity: Optional[int] = None
    task: Optional[str] = None


class GeometricFeature(BaseModel):
    """Geometrisches Feature eines Parts."""
    type: str = Field(description="Feature type: 'hole', 'thread', 'chamfer', 'fillet', 'groove', 'slot', 'boss', etc.")
    description: str = Field(description="Detailed description of the feature")
    quantity: Optional[int] = Field(default=None, description="Number of this feature present")
    is_interface: Optional[bool] = Field(default=None, description="True if feature is used for assembly interface")
    certainty: Optional[float] = Field(default=None, description="Confidence level 0.0-1.0", ge=0.0, le=1.0)


class MaterialInfo(BaseModel):
    """Material-bezogene Informationen."""
    possible_materials: List[str] = Field(default_factory=list, description="List of possible materials: 'steel', 'aluminum', 'plastic', 'brass', etc.")
    density: Optional[Literal["low", "medium", "high"]] = Field(default=None, description="Relative density classification")
    mass: Optional[Literal["very_light", "light", "medium", "heavy", "very_heavy"]] = Field(default=None, description="Relative mass classification")
    certainty: Optional[float] = Field(default=None, description="Confidence level 0.0-1.0", ge=0.0, le=1.0)


class PositionXY(BaseModel):
    x: int = Field(..., description="X position in pixel coordinates (original resolution 896)")
    y: int = Field(..., description="Y position in pixel coordinates (original resolution 672)")


class Surface(BaseModel):
    picture: str 
    description: str = Field(
        description=(
            "Provide a detailed geometric analysis in bullet points. "
            "Each bullet should describe a distinct attribute (task of the surface, overall shape, geometric features, etc.). "
            "Do not repeat information. "
            "Include approximate dimensions, and functional relevance when visible. "
            "Limit each bullet to 1–2 sentences."
        )
    )
    name: str
    position: PositionXY = Field(description = "point to the surface you talk about, give x and y position in pixel coordinates. original resolution is 896x672")
    position_description: str = Field(description = " describe the location of the surface (top, bottom, left, right, ...)")
    size: Literal["small", "medium", "large"] = Field(..., description="Relative to total part size")
    chamfers: Literal["yes", "no"] = Field(..., description="Are chamfers present at the ends of the surface?")
    endstops: Literal["yes", "no"] = Field(..., description="Are endstops present at the ends of the surface?")
    suitable_for_gripping_reasoning: str
    suitable_for_gripping: Literal["yes", "no"] = Field(..., description="Is this surface suitable for gripping?")


class AssemblyInterface(BaseModel):
    """Montage-relevante Eigenschaften."""
    gripping_surfaces: List[str] = Field(default_factory=list, description="Description of surfaces suitable for gripping: 'flat surfaces', 'cylindrical body', 'hexagonal head', etc.")
    orientation_by_design: Optional[Literal["symmetric", "asymmetric", "keyed", "polarized", "any"]] = Field(default=None, description="How design constrains assembly orientation")
    additional_joining_elements: List[str] = Field(default_factory=list, description="Joining features: 'threads', 'snap-fit', 'press-fit', 'adhesive surface', 'welding points', etc.")
    certainty: Optional[float] = Field(default=None, description="Confidence level 0.0-1.0", ge=0.0, le=1.0)


class AssemblyAnalysis(BaseModel):
    """Assembly-Analyse aus Vision Model."""
    assembly_description: str = Field(
        description=(
            "Provide a detailed geometric analysis in bullet points. "
            "Each bullet should describe a distinct attribute (type of assembly, task, part, features, etc.). "
            "Do not repeat information. "
            "in Bulletpoints. Short sentences."
        )
    )
    partslist: str = Field(description = "In Bullet Points: List all parts you can identify in the images with a brief description of a name, function and color")
    assembly_name_guess: str = Field(description="Based on what you see - how can we name the assembly. Give one name.")
    primary_function: str = Field(description="Based on what you see - whats the task of the assembly? Describe it on macro level, in Bulletpoints. Short sentences.")


class MonopartAnalysis(BaseModel):
    """
    Intrinsic physical and automation-relevant analysis of a single part.
    No interaction with other parts is considered here.
    All answers in bullet points.
    """

    material_and_mechanical_behavior: str = Field(
        description=(
            "Describe material and mechanical response in bullet points:\n"
            "- What material is likely used?\n"
            "- Does the component contain sensitive functional surfaces?\n"
            "- Would it deform under typical gripping forces (20–50N)?\n"
            "- Are there thin walls, ribs, elastic zones?\n"
            "- Is it solid, brittle, ductile, elastic, flexible?\n"
        )
    )

    bulk_behavior: str = Field(
        description=(
            "Analyze behavior in an unordered bulk condition, in bullet points:\n"
            "- Could parts interlock, hook, or entangle?\n"
            "- Could they nest into each other?\n"
            "- Do they stack naturally or chaotically?\n"
            "- Do they roll, tip, or lie stable on flat surfaces?\n"
            "- Are there protrusions or delicate features?\n"
            "- Is the part suitable for vibration feeding?\n"
            "- Can the part be gripped by a bin picking system?\n"
            "- Is manual seperation required from bulk due to risks?\n"
            "Explain mechanical reasons."
        )
    )

    magazine_behavior: str = Field(
        description=(
            "Analyze magazine/load carrier suitability in bullet points:\n"
            "- Can the component be placed in a load carrier (flat surface, no additional fixtures) in a tilt-stable and positionally stable manner?\n"
            "- Can an intermediate layer be placed on top to enable stacking of a second part layer?\n"
            "- Do parts need to be protected from one another to prevent damage during transport?\n"
            "- Is the use of part separators (e.g., blister packaging or similar inserts) required?\n"
            "- Does the component require an adhesive intermediate layer for protection or lubrication?\n"
        )
    )

    nature_of_provision_guess: str = Field(
        description=(
            "Based on the parts mechanical properties, bulk behavior, and magazine suitability, what is your best guess on how this part is provided for assembly?"
            "Important: Think about an actual real-world scenario. Consider the practicalities of this part in a factory setting. In bullet points, explain your reasoning and give your best guess on how this part is likely provided for assembly"
            "Describe the most likely screnario for this part regarding its provision"
        )
    )

    geometric_characteristics: str = Field(
        description=(
            "Describe geometry in bullet points:\n"
            "- Overall Dominant shape (rotational, prismatic, flat, complex, ...)\n"
            "- Symmetry properties\n"
            "- Distinctive features (bores, flanges, chamfers, ribs, hooks, ...)\n"
            "- Single features"
        )
    )

    gripping_analysis: str = Field(
        description=(
            "Analyze possible gripping strategies, in bullet points:\n"
            "- Where can the part be gripped? Give at least 3 possibilities. Mention the absolute size of the gripping surfaces\n"
            "- Are there parallel surfaces?\n"
            "- Is form-fit gripping possible?\n"
            "- Would gripping enforce orientation or allow misalignment?\n"
            "- Would we need a more complex gripper with index holes or multiple clamps?"
            "- Must the gripper be orientated based on the parts orientation and position?"
            "- Are surfaces sensitive to scratches or marks?\n"
            "- Is the geometry so complex that we would need an aligntment station before gripping is possible?"
            "Focus only on intrinsic gripping behavior."
        )
    )

    handling_implications: str = Field(
        description=(
            "Based on gripping and mechanical behavior, discuss handling implications in bullet points:\n"
            "- Is gripping mechanically stable?\n"
            "- Is orientation control simple or complex?\n"
            "- Is deformation risk relevant?\n"
            "- Are additional alignment steps likely needed?\n"
        )
    )

    intrinsic_summary: str = Field(
        description=(
            "Provide a concise mechanical summary (3–5 sentences):\n"
            "Summarize the intrinsic automation-relevant characteristics of this part."
        )
    )


class SinglePartAnalysis(BaseModel):
    """
    Monopart analysis.
    Semantic interpretation separated from intrinsic automation physics.
    """

    part_identification: str = Field(
        description="What is the part's task within the assembly? (bullet points)"
    )

    part_name_guess: str = Field(
        description="Short suitable name for the part."
    )

    part_color: str = Field(
        description="name the color of the shown part"
    )

    monopart_analysis: MonopartAnalysis

  

class AssemblyBatchAnalysis(BaseModel):
    """Wrapper für Assembly Batch Analysis."""
    analysis: AssemblyAnalysis


class SinglePartBatchAnalysis(BaseModel):
    """Wrapper für Monopart Batch Analysis."""
    analysis: SinglePartAnalysis


# ============================================================================
# FFA (FITNESS FOR AUTOMATION) MODELS
# ============================================================================

# SUBPROCESS 1: SEPARATION (Vereinzelung)
class NatureOfProvisionOption(str, Enum):
    """Nature of provision (joining part) - how parts are supplied/separated."""
    
    MAGAZINE_DEFINED = "in magazine (defined position and orientation)"
    MAGAZINE_UNDEFINED = "in magazine (without defined position or orientation)"
    MAGAZINE_PACKAGING_ISSUES = "in magazine (packaging issues: individual packaging or sticky intermediate layer)"
    MAGAZINE_NON_STICKY = "in magazine (with non-sticky intermediate layer)"
    BULK_EASY_AUTOMATED = "bulk cargo (easy to automated: e.g. spiral conveyors)"
    BULK_BIN_PICKING = "bulk cargo (automation with bin picking)"
    BULK_NO_AUTOMATION = "bulk cargo (no automation possible: e.g. risk of catching)"


class Separation(BaseModel):
    """Assessment: Subprocess Separation (Vereinzelung)."""
    
    options_analysis: str = Field(..., description="Analyze ALL available options (in magazine defined/undefined, bulk cargo easy/bin picking/impossible, etc.) and discuss which fits this specific step BEFORE making final selection. In bullet points 1-2 senteces per Point. Do not repeat information")
    nature_of_provision_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding nature of provision? Answer in bullet points. Whats the most likely scenario for this specific case?.")
    nature_of_provision: NatureOfProvisionOption = Field(..., description="Nature of provision / separability of joining parts")
    evidence: Optional[List[str]] = Field(None, description="Evidence from BOM/Metadata. In bullet points.")


    automatable_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding automation feasibility for separation? Answer in bullet points")
    


# SUBPROCESS 2: HANDLING (Handhaben)  
class PartRigidityOption(str, Enum):
    """Part rigidity options (FFA criterion)."""
    
    RIGID = "rigid"
    ELASTIC = "elastic"
    FLEXIBLE = "flexible"


class GrippingAreasOption(str, Enum):
    """Gripping areas on part options (FFA criterion)."""
    
    PRONOUNCED = "pronounced gripping area existing"
    SMALL = "small gripping area existing"
    NONE = "no defined gripping area existing"


class OrientationFeaturesOption(str, Enum):
    """Features for fine orientation in gripper (FFA criterion)."""
    
    SELF_ADJUSTMENT = "mechanical self-adjustement in gripper possible"
    OPTICAL_MEASUREMENT = "optical measurement in part delivery necessary"
    ALIGNING_STATION = "seperate aligning station necessary"
    NO_REFERENCE = "no reference points for orientation"


class SurfaceSensibilityOption(str, Enum):
    """Surface sensibility options (FFA criterion)."""
    
    IMMUNE = "immune"
    SENSITIVE = "easily scratched, easily broken, easily defomed"


class Handling(BaseModel):
    """Assessment: Subprocess Handling (Handhaben)."""
    
    
    rigidity_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding part rigidity? Answer in bullet points")
    part_rigidity: PartRigidityOption = Field(..., description="Part rigidity")
    
    gripping_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding gripping areas? Answer in bullet points")
    gripping_areas: GrippingAreasOption = Field(..., description="Availability of gripping areas")
    
    orientation_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding orientation features? Answer in bullet points")
    orientation_features: OrientationFeaturesOption = Field(..., description="Orientation features")
    
    surface_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding surface sensibility? Answer in bullet points")
    surface_sensibility: SurfaceSensibilityOption = Field(..., description="Surface sensibility")
    
    evidence: Optional[List[str]] = Field(None, description="Evidence from BOM/Metadata. In bullet points.")

    automatable_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding automation feasibility for handling? Answer in bullet points")




# SUBPROCESS 3: POSITIONING
class AccuracyOfTargetPositionOption(str, Enum):
    """Accuracy of the target position options."""
    
    BOTH_DEFINED = "base part position defined / joining point position defined"
    BASE_DEFINED_JOINING_TOLERANCE = "base part position defined / joining point position with tolerance"
    BASE_TOLERANCE_JOINING_DEFINED = "base part position with tolerance / joining point position defined"
    BOTH_TOLERANCE = "base part position with tolerance / joining point position with tolerance"


class PositioningAidsOption(str, Enum):
    """Positioning aids at the part options."""
    
    CHAMFERS_AND_STOPS = "insertion chamfers and stopping edge"
    CHAMFERS_ONLY = "insertion chamfers"
    STOPS_ONLY = "stopping edges"
    NO_AIDS = "no positioning aids"


class AdditionalOrientationByRotationOption(str, Enum):
    """Additional orientation by rotation options."""
    
    NOT_REQUIRED = "not required"
    MECHANICAL_GUIDANCE = "mechanical guidance"
    OPTICAL_INFORMATION = "optical information necessary"
    NOT_FEASIBLE = "required but not feasible"


class AccessibilityToJoiningPositionOption(str, Enum):
    """Accessibility to the joining position options."""
    
    VISIBILITY_AND_CLEARANCES = "visibility given / tool clearances given"
    NO_VISIBILITY_CLEARANCES = "no visibility / tool clearances given"
    VISIBILITY_NO_CLEARANCES = "visibility given / no tool clearances"
    BLOCKED = "no visibility / no tool clearances (e.g. blocked by cables, hoses etc.)"


class PositioningMotionOption(str, Enum):
    """Positioning motion options."""
    
    LINEAR = "linear joining motion"
    PATH_MOTION = "path motion necessary"
    SENSOR_GUIDED = "sensor-guided (linear/path)"


class PositioningTolerancesOption(str, Enum):
    """Positioning tolerances options."""
    
    PLUS_MINUS_X_MM = "+/- x mm"
    PLUS_MINUS_0X_MM = "+/- 0.x mm"
    ZERO_CLEARANCE = "0 clearance"
    ADJUSTMENT_REQUIRED = "adjustment of end position after assembly required"


class StabilityInPositionedStateOption(str, Enum):
    """Stability in positioned state options."""
    
    STABLE_SELF_HOLDING = "stable, self-holding"
    HOLDING_REQUIRED = "holding during joining process required"


class Positioning(BaseModel):
    """Assessment: Subprocess Positioning."""
    

    accuracy_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding accuracy of target position? Answer in bullet points")
    accuracy_of_target_position: AccuracyOfTargetPositionOption = Field(..., description="Accuracy of the target position")
    
    positioning_aids_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding positioning aids? Answer in bullet points")
    positioning_aids: PositioningAidsOption = Field(..., description="Positioning aids at the part")
    
    orientation_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding additional orientation by rotation? Answer in bullet points")
    additional_orientation_by_rotation: AdditionalOrientationByRotationOption = Field(..., description="Additional orientation by rotation")
    
    accessibility_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding accessibility to joining position? Answer in bullet points")
    accessibility_to_joining_position: AccessibilityToJoiningPositionOption = Field(..., description="Accessibility to the joining position")
    
    motion_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding positioning motion? Answer in bullet points")
    positioning_motion: PositioningMotionOption = Field(..., description="Type of positioning motion")
    
    tolerances_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding tolerances? Answer in bullet points")
    positioning_tolerances: PositioningTolerancesOption = Field(..., description="Positioning tolerances")
    
    stability_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding stability in positioned state? Answer in bullet points")
    stability_in_positioned_state: StabilityInPositionedStateOption = Field(..., description="Stability in positioned state")
    
    evidence: Optional[List[str]] = Field(None, description="Evidence from BOM/Metadata. In bullet points.")
    
    automatable_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding automation feasibility for positioning? Answer in bullet points")


# SUBPROCESS 4: JOINING
class FeedingOfJoiningElementOption(str, Enum):
    """Feeding of the joining element options."""
    
    NOT_NECESSARY = "not necessary"
    STANDARD_SOLUTION = "automatable with standard solution"
    LIMITED_FEEDING = "limited feeding (e.g. accessibility)"
    SPECIAL_DEVELOPMENT = "automatable with special development"
    NOT_FORESEEABLE = "special development, not foreseeable"


class FixingOfMountedPartOption(str, Enum):
    """Fixing of the mounted part options."""
    
    STANDARD_SOLUTION = "automatable with standard solution"
    SPECIAL_DEVELOPMENT = "automatable with special development"
    NOT_FORESEEABLE = "special development, not foreseeable"


class Joining(BaseModel):
    """Assessment: Subprocess Joining."""
    
    feeding_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding feeding of joining element? Answer in bullet points")
    feeding_of_joining_element: FeedingOfJoiningElementOption = Field(..., description="Feeding of the joining element")
    
    fixing_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding fixing of mounted part? Answer in bullet points")
    fixing_of_mounted_part: FixingOfMountedPartOption = Field(..., description="Fixing of the mounted part")
    
    evidence: Optional[List[str]] = Field(None, description="Evidence from BOM/Metadata. In bullet Points.")

    automatable_reasoning: str = Field(..., description="Recollect the info you got regarding that topic. What are your thoughts regarding automation feasibility for joining? Answer in bullet points")
    

# ============================================================================
# DESIGN DRAWBACKS MODELS
# ============================================================================

class OverallFFAItem(BaseModel):
    """Overall FFA summary per subprocess."""
    subprocess: Literal["separation", "handling", "positioning", "joining"]
    automation_potential: str = Field(..., description="1-2 sentences on automation potential for this subprocess, use Low, Moderate, High as a classification and explain your reasoning")
    risks: str = Field(..., description="1-2 sentences on identified risks or constraints for this subprocess")


class DrawbackItem(BaseModel):
    """Individual design drawback that hinders automation."""
    drawback_id: str = Field(..., description="Unique ID for this drawback (e.g., 'drawback_1', ...)")
    description: str = Field(..., description="Concise description of the design issue that hinders automation (1-2 sentences) as short as possible")
    improvement_measure: str = Field(..., description="Specific improvement measure to address this drawback, as short and as precise as possible (Add ..., Change ..., Remove ..., Substitute ..., etc.)")


class DesignDrawbacksPart(BaseModel):
    """Design drawbacks for a specific part in an assembly step."""
    step_id: int = Field(..., description="Assembly step number")
    part_id: str = Field(..., description="Part identifier (e.g., 'part_001')")
    drawbacks: List[DrawbackItem] = Field(..., min_items=1, max_items=3, description="List of design drawbacks / flaws / issues on the base part that hinder automation in that step or create a risk for automation")


class DesignDrawbacksAssembly(BaseModel):
    """Design drawbacks at the assembly/interaction level."""
    step_id: int = Field(..., description="Assembly step number")
    drawbacks: List[DrawbackItem] = Field(..., min_items=1, max_items=3, description="List of design drawbacks / flaws / issues of the assembly that hinder automation in that step (1-3 items)")


# COMPLETE FFA ASSESSMENT
class FFA_Assessment_Complete(BaseModel):
    """
    Fitness for Automation Assessment - Complete assessment of all 4 subprocesses.
    
    IMPORTANT EVALUATION LOGIC:
    - SEPARATION: For JOINING PART (how is it supplied to assembly station?)
    - HANDLING: For JOINING PART (how is it gripped/transported?)
    - POSITIONING: For the INTERACTION between parts (how are they aligned/positioned together?)
    - JOINING: For the INTERACTION between parts (how are they connected?)
    
    The LLM must classify each assessment criterion.
    Used by the FFA Assessment Node.
    """

    # SEPARATION: Joining part only (how is it supplied to assembly station?)
    separation: Separation = Field(None, description="Separation assessment for JOINING PART")
    
    # HANDLING: Joining part only (base part already in assembly, no handling needed)
    handling: Handling = Field(None, description="Handling assessment for JOINING PART")
    
    # POSITIONING: Interaction between parts
    positioning: Positioning = Field(..., description="Positioning assessment for INTERACTION between base and joining parts (alignment, accuracy, motion)")
    
    # JOINING: Interaction between parts
    joining: Joining = Field(..., description="Joining assessment for INTERACTION between parts (feeding, fixing)")

    # Overall FFA Summary per subprocess
    overall_ffa: List[OverallFFAItem] = Field(..., description="Summary of automation potential and risks for each subprocess")
    
    # Design Drawbacks at different levels
    design_drawbacks_base_part: List[DesignDrawbacksPart] = Field(..., description="Design drawbacks / flaws / issues on the base part that hinder automation in that step or create a risk for automation")
    design_drawbacks_joining_parts: List[DesignDrawbacksPart] = Field(..., description="Design drawbacks / flaws  / issues  on the joining part(s) that hinder automation in that step or create a risk for automation")
    design_drawbacks_assembly: List[DesignDrawbacksAssembly] = Field(..., description="Design drawbacks / issues at assembly level, Give big changes on assembly level (delete parts, change parts, substitute parts, ...)")
    


# ============================================================================
# ASSEMBLY SEQUENCE GENERATION MODELS (MINIMAL)
# ============================================================================


class PartInfoReduced(BaseModel):
    """Reduced listing of BOM 
    """

    part_id: str = Field(None, description="Part ID (e.g. part_001)")
    part_name: str = Field(None, description="Part name from BOM")
    quantity: int = Field(None, description="Part quantity")                   

class AssemblyStep(BaseModel):
    """Assembly step with clear structure for both subassemblies and main assembly.
    
    Rendering needs: step_id, base_part, joining_part, belongs_to
    Human-readable: step_description, joining_process
    
    IMPORTANT: First step of each assembly/subassembly has base_part=null (initial placement).
    """
    
    step_id: int = Field(..., description="Unique step ID (1, 2, 3, ...)")
    step_description: str = Field(..., description="Free-text description of what happens in this step (e.g., 'Place helical gear on table', 'Insert ball bearings into gear')")
    belongs_to: str = Field(..., description="Assembly context: 'Assembly (basic config)' for main assembly, 'Subassy 1', 'Subassy 2', etc. for subassemblies")
    base_part: Optional[str] = Field(None, description="Part ID serving as base (e.g., 'part_001'). NULL for initial placement steps (first step of assembly/subassembly).")
    joining_part: Optional[Union[str, List[str]]] = Field(None, description="Part ID(s) being joined. String for single part, list for multiple parts/subassemblies. MUST be present for all steps.")
    joining_process: str = Field(..., description="Process/method used (e.g., 'Place', 'Insert', 'Screw', 'Press-fit', 'Snap-fit')")


class AssemblySequence(BaseModel):
    """Clean, flat assembly sequence structure.
    
    Provides clear overview with assembly name, logic, notation, and flat list of steps.
    Each step clearly indicates whether it belongs to main assembly or a subassembly.
    """
    
    assembly_name: str = Field(..., description="Name of the assembly (e.g., 'worm gear demonstrator')")
    assembly_description: str = Field(..., description = "Give a comprehensive description of the assembly use the data and img you are provided. Focus on assembly process related info. in Bulletpoints. Short sentences")
    sequence_description: str = Field(..., description = "Think about a possible assembly sequence and write down your thoughts here.")
    sequence_logic_prior: str = Field(..., description="Free-text explanation of assembly strategy: WHY this sequence, what constraints were considered, blockages identified, subassembly rationale, optimization decisions. This is the LLM's reasoning BEFORE generating the sequence.")
    sequence_notation_prior: str = Field(..., description="Assembly sequence in compact notation. Format: 'assembly[SA1[part_001,part_002] part_003,part_004,SA2[part_005,part_006]]' where SA1/SA2 are subassemblies. Main assembly parts listed at root level.")
    steps: List[AssemblyStep] = Field(..., description="Flat list of assembly steps in execution order. Each step clearly shows: step_id (1,2,3...), step_description, belongs_to (Assembly or Subassy), base_part, joining_part, joining_process.")
    sequence_notation: str = Field(..., description="Assembly sequence in compact notation. Format: 'assembly[SA1[part_001,part_002] part_003,part_004,SA2[part_005,part_006]]' where SA1/SA2 are subassemblies. Main assembly parts listed at root level.")
    


# Rebuild model to resolve forward references (nur noch AssemblySequence, Subassembly entfernt)
AssemblySequence.model_rebuild()


# ============================================================================
# ASSEMBLY SEQUENCE FROM GROUND TRUTH (ASGT) – LLM fills descriptions only
# ============================================================================

class AssemblyStepDescription(BaseModel):
    """LLM-generated fields for one GT-defined assembly step.
    
    The step structure (step_id, belongs_to, base_part, joining_part) is fixed by GT.
    The LLM only generates step_description and joining_process.
    """
    step_id: int = Field(
        ...,
        description="Step ID matching the ground truth step (1, 2, 3, ...)"
    )
    step_description: str = Field(
        ...,
        description=(
            "Clear, concise one-sentence description of what physically happens in this step. "
            "Mention the specific part names. "
            "Example: 'Insert the cylindrical bearing into the housing bore.'"
        )
    )
    joining_process: str = Field(
        ...,
        description=(
            "The manufacturing joining process used in this step. "
            "Use precise process terms: 'Place', 'Insert', 'Press-fit', 'Screw', "
            "'Snap-fit', 'Weld', 'Glue', 'Rivet', 'Crimp', etc."
        )
    )


class AssemblySequenceStepDescriptions(BaseModel):
    """LLM output when generating step descriptions for a GT-structured sequence.
    
    The sequence structure (which parts go in which order) is fixed by ground truth.
    The LLM provides: step_descriptions, joining_processes, assembly meta-fields.
    Python then merges these with the GT step structure to produce a full AssemblySequence.
    """
    assembly_name: str = Field(
        ..., description="Name of the assembly"
    )
    assembly_description: str = Field(
        ..., description="Comprehensive description of the assembly focusing on assembly process."
    )
    sequence_description: str = Field(
        ..., description="Brief description of the assembly sequence logic."
    )
    sequence_logic_prior: str = Field(
        ..., description="Reasoning about WHY this sequence makes sense given the GT step order."
    )
    steps: List[AssemblyStepDescription] = Field(
        ...,
        description="One entry per GT step. step_id must match GT. Fill step_description and joining_process."
    )
    sequence_notation: str = Field(
        ...,
        description="Assembly sequence in compact notation reflecting the GT step order."
    )


AssemblySequenceStepDescriptions.model_rebuild()

class AssemblyStepValidation(BaseModel):
    """Validation result for a single assembly step."""
    
    step_number: int = Field(..., description="Step number being validated (1-indexed)")
    step_description: str = Field(..., description="Based on the provided images: What happends in that process?")
    step_remarks: str = Field(..., description ="Are there any problems visible?")
    suggested_improvements: List[str] = Field(default_factory=list, description="Suggestions to improve this step if needed")


class AssemblySequenceValidation(BaseModel):
    """Complete validation results for an assembly sequence."""
    
    assembly_name: str = Field(..., description="Name of the assembly being validated")
    assembly_sequence_id: str = Field(..., description="Reference to the assembly_sequence.json that was validated")
    validation_id: str = Field(..., description="Unique validation ID")
    validated_at: str = Field(..., description="ISO timestamp of validation")
    
    step_validations: List[AssemblyStepValidation] = Field(..., description="Validation results for each step")
    
    overall_confidence: float = Field(..., description="Overall confidence across all steps (0-100)", ge=0, le=100)
    overall_valid: bool = Field(..., description="Overall assessment: is sequence valid?")
    overall_risk_level: Literal["LOW", "MEDIUM", "HIGH"] = Field(..., description="Overall risk level across all steps")
    
    token_usage: Optional[dict] = Field(None, description="Token usage statistics (prompt_tokens, completion_tokens, total_tokens)")


# ============================================================================
# INTERACTION ANALYSIS MODELS
# ============================================================================

class InteractionAnalysisDetailed(BaseModel):
    """Detailed interaction analysis addressing fixture strategy, geometry, positioning, and joining process."""

    # -------------------------
    # CATEGORY 1 – Base Part Fixture Capability
    # -------------------------
    
    geometric_interaction: List[str] = Field(
        description=(
            "Describe how base and joining part geometries interact during assembly and in the final state. "
            "In bullet points, address: "
            "DURING ASSEMBLY: "
            "- How do the geometries interact while parts are being assembled? "
            "- What geometric features and surfaces are in contact or approach each other? "
            "- Which features are critical for aligning the parts during this phase? "
            "\n"
            "IN ASSEMBLED STATE: "
            "- How do the geometries interact in the final assembled position? "
            "- What surfaces or interfaces bear loads or provide structural connection? "
            "- Which features maintain stability and alignment in the final state?"
        )
    )

    positioning_possibilities: List[str] = Field(
        description=(
            "In what orientations can the existing subassembly (base part and already placed parts) be placed on the assembly table? "
            "Assume there is a fixture available."
            "For each orientation possibility: What geometric features assist or enable this placement? "
            "List 3 possibilities in bullet points."
            "Which possibility is most likely to be used in actual assembly conditions based on the geometry (based on accessibility and so on)?"
        )
    )


    accuracy_of_target_position: List[str] = Field(
        description=(
            "Assume the existing base part / subassembly is placed in the fixture. What accuracy of the target position of the joining part is required for successful assembly? "
            "In bullet points, specify: "
            "- What translational precision is required? (e.g., +/- x mm from reference) "
            "- What rotational precision is required? (e.g., within ± degrees) "
            "- Which fit type determines the required accuracy? (clearance, transition, interference fit) "
            "- What surfaces or features define the target position? "
            "- What are the mechanical consequences if positional tolerance is exceeded?"
        )
    )

    positioning_aids: List[str] = Field(
        description=(
            "Identify geometric features that assist alignment or centering between base and joining parts during assembly. "
            "In bullet points, describe: "
            "- What positioning aids are present? (e.g., chamfers, tapers, fillets, shoulders, guide surfaces, endstops, bore edges, shaft keys) "
            "- How do these features mechanically guide or constrain movement during positioning? "
            "- Are insertion chamfers or stopping edges present and effective? "
            "- Do alignment features ensure repeatable, reliable positioning?"
        )
    )

    additional_orientation_by_rotation: List[str] = Field(
        description=(
            "Determine whether rotational alignment is required between base and joining parts. "
            "In bullet points, address: "
            "- Is a defined angular orientation required between joining part and base part before joining?"
            "- What geometric features enforce or indicate the required angular position? "
            "- What are the mechanical consequences if angular alignment is incorrect? (e.g., misfit, uneven loading, assembly failure)"
        )
    )

    joining_tolerances: List[str] = Field(
        description=(
            "Analyze the tolerance relationship required between base and joining parts for successful assembly. "
            "In bullet points, determine: "
            "- What is the most probable industrial tolerance class between the parts?"
            "- What geometric fit type is required? (clearance fit, transition fit, interference fit, form-fit) "
            "- How mechanically sensitive is the assembly to tolerance variation? "
            "- What are the consequences of over/under-tolerance?"
        )
    )

    accessibility_to_joining_position: List[str] = Field(
        description=(
            "Evaluate whether the joining location is geometrically accessible to tools and the joining part. Assume your chosen orientation of subassembly / base part."
            "In bullet points, address: "
            "- Are visibility and tool clearances available at the joining location? "
            "- What are possible approach directions (axial, radial, angular)? "
            "- What insertion depth is required, and are there obstructions? "
            "- Do existing assembly components restrict or block access to the joining position? "
            "- Is the joining motion visible and unblocked, or is it hidden/constrained by surrounding geometry? "
            "(Note: Section views may not show the normal assembly orientation—consider the actual assembly perspective.)"
        )
    )

    joining_motion: List[str] = Field(
        description=(
            "Describe the mechanically required joining motion based strictly on geometry. Based on your chosen orientation of subassembly / base part, and the geometric interaction between parts, what motion is required to achieve the final assembled state? "
            "In bullet points, specify: "
            "- What joining motion is required? (e.g., axial insertion, rotation, Point to Point motion, Linear Motion, combined motion, press-fit, snap-fit engagement) "
            "- Which degrees of freedom are constrained vs. free during the motion? "
            "- Are there intermediate steps or multi-axis motions? "
            "- What geometric interactions drive the motion (e.g., aligned bores, guiding surfaces, tapers)?"
        )
    )

    stability_in_positioned_state: List[str] = Field(
        description=(
            "Evaluate the mechanical stability of the joining part in its final assembled state." 
            "In bullet points, address both scenarios: "
            "BEST CASE (optimal orientation): Would gravity and geometry ensure the joining part remains stable and self-holding if the base part moves? "
            "WORST CASE (suboptimal orientation): Would the joining part fall off or shift if the assembly is moved or inverted? "
            "Then assess: "
            "- Which scenario (best or worst case) is more likely in actual assembly conditions?"
            "- Are there unintended movements or slip risks based interaction? "
        )
    )

    # -------------------------
    # CATEGORY 4 – Joining Process
    # -------------------------

    feeding_of_joining_element: List[str] = Field(
        description=(
            "Identify and analyze additional joining elements required for the assembly step. IMPORTANT: JOINING PART IS NOT CONSIDERED AS AN ADDITIONAL ELEMENT. Only non visible elements that might be required for the joining process are considered here."
            "In bullet points, address: "
            "- Is an additional joining element required? (e.g., adhesive, fastener, clip, retaining ring, lubricant, gasket) "
            "- What is its mechanical function? "
            "- How can it be fed to the process? "
        )
    )

    fixing_of_mounted_part: List[str] = Field(
        description=(
            "Describe the joining process between base and joining parts and analyze automation feasibility. "
            "In bullet points, address: "
            "- What joining process is required?"
            "- Is the process automatable with standard solutions, special development, or not feasible? "
        )
    )




class StepInteractionAnalysis(BaseModel):
    """Analysis of geometric interaction between base and joining parts for a single assembly step."""
    
    step_id: int = Field(..., description="Step ID being analyzed (1, 2, 3, ...)")
    step_description: str = Field(..., description="Description of the assembly step and parts involved")
    InteractionAnalysisDetail: InteractionAnalysisDetailed = Field(..., description="Detailed geometric and mechanical interaction analysis")


# ============================================================================
# STEPPARSER METADATA MODELS (PHASE 4.1)
# ============================================================================

class MomentOfInertia(BaseModel):
    """Moment of Inertia tensor components."""
    Ixx: float
    Iyy: float
    Izz: float
    Ixy: float
    Ixz: float
    Iyz: float


class BoundingBoxData(BaseModel):
    """Bounding box with min/max points and absolute dimensions."""
    min: List[float] = Field(..., description="Minimum point [x, y, z]")
    max: List[float] = Field(..., description="Maximum point [x, y, z]")
    absolute: dict = Field(..., description="Absolute dimensions {x, y, z}")


class CenterOfMass(BaseModel):
    """Center of Mass in absolute and relative coordinates."""
    absolute: List[float] = Field(..., description="Absolute COM coordinates [x, y, z]")
    relative_bbox: List[float] = Field(..., description="Relative COM within bounding box [rx, ry, rz]")


class GeometrySummary(BaseModel):
    """Summary of geometric topology."""
    face_count: int
    edge_count: int
    vertex_count: int
    cylinder_surfaces: int
    plane_surfaces: int
    sphere_surfaces: int
    other_surfaces: int


class DetailedBrepFace(BaseModel):
    """Detailed BREP analysis for a single face."""
    face_id: int
    type: str
    area: float
    centroid: Optional[List[float]] = None
    normal: Optional[List[float]] = None
    # Cylinder-specific
    radius: Optional[float] = None
    axis: Optional[List[float]] = None
    # Plane-specific
    plane_normal: Optional[List[float]] = None
    # Additional geometric properties
    properties: Optional[dict] = None


class DetailedBrepAnalysis(BaseModel):
    """Detailed BREP analysis results."""
    faces: dict = Field(..., description="Faces analysis with 'details' key containing list of DetailedBrepFace")


class PartMetadataFull(BaseModel):
    """
    Complete Stepparser Metadata for a Part.
    Contains ALL fields from stepparser output (Part.to_metadata_dict()).
    Used for merge_copy_part_data to preserve instance-specific position/orientation.
    """
    part_id: str = Field(..., description="Unique part ID (e.g., 'part_001', 'part_001_copy1')")
    name: str = Field(..., description="Part name from STEP file")
    directory: Optional[str] = Field(None, description="Absolute path to part folder")
    
    # Geometric properties
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    mom_inertia: Optional[MomentOfInertia] = None
    
    # Spatial properties (CRITICAL for duplicate handling)
    bounding_box: Optional[BoundingBoxData] = None
    COM: Optional[CenterOfMass] = None
    
    # Topology
    geometry_summary: Optional[GeometrySummary] = None
    
    # Appearance
    color: Optional[List[int]] = Field(None, description="RGB color values [r, g, b]")
    
    # Duplicate tracking
    quantity_in_assembly: int = Field(1, description="Number of identical parts in assembly")
    identical_to: List[str] = Field(default_factory=list, description="List of part_ids with identical geometry")
    
    # Optional detailed analysis
    detailed_brep_analysis: Optional[DetailedBrepAnalysis] = None


class AssemblyMetadataFull(BaseModel):
    """
    Complete Stepparser Metadata for an Assembly.
    Contains ALL fields from stepparser output (Assembly.to_metadata_dict()).
    """
    assembly_id: Optional[str] = None
    name: str
    directory: Optional[str] = None
    depth: int = Field(0, description="Depth in assembly hierarchy (0 = top level)")
    
    # Statistics
    total_parts: int
    unique_parts: int
    direct_children: int
    
    # Hierarchy
    subassemblies: List[str] = Field(default_factory=list, description="List of subassembly IDs")
    parts: List[str] = Field(default_factory=list, description="List of direct child part IDs")
    
    # Spatial properties
    bounding_box: Optional[BoundingBoxData] = None
    COM: Optional[dict] = Field(None, description="Center of mass with absolute and relative_bbox_centered")
    total_volume: Optional[float] = None


class PartEnrichedMerged(BaseModel):
    """
    Merged Part Data: LLM Enrichment + Stepparser Metadata.
    Created by merge_copy_part_data node (Phase 4.2).
    Preserves instance-specific position/orientation for duplicate parts.
    """
    # Part Identity (from Stepparser)
    part_id: str = Field(..., description="Unique part ID including copy suffix (e.g., 'part_001', 'part_001_copy1')")
    part_name: str = Field(..., description="Part name from STEP file")
    
    # LLM Enrichment fields (from -enriched.json)
    # TODO: Add all enrichment fields here when implementing 4.2
    # Example placeholders:
    description: Optional[str] = None
    geometric_features: Optional[List[GeometricFeature]] = None
    material_info: Optional[MaterialInfo] = None
    assembly_interface: Optional[AssemblyInterface] = None
    
    # Stepparser Metadata fields (CRITICAL for instance-awareness)
    position: Optional[dict] = Field(None, description="Absolute position from Stepparser (if available)")
    orientation: Optional[dict] = Field(None, description="Orientation/rotation from Stepparser (if available)")
    placement: Optional[dict] = Field(None, description="Placement info from Stepparser (if available)")
    bounding_box: Optional[BoundingBoxData] = None
    COM: Optional[CenterOfMass] = None
    volume: Optional[float] = None
    surface_area: Optional[float] = None
    color: Optional[List[int]] = None
    
    # Metadata
    quantity_in_assembly: int = Field(1, description="Always 1 for instance-specific parts")
    identical_to: List[str] = Field(default_factory=list, description="List of other part_ids with identical geometry")


# ============================================================================
# FFA REPORT DESTILLED MODELS (LLM OUTPUT)
# ============================================================================

class PartDrawbacks(BaseModel):
    """Drawbacks list for a single part in FFA Report."""
    part_id: str = Field(..., description="Part ID (e.g., 'part_001')")
    part_drawbacks: List[str] = Field(
        ..., 
        description="List of unique automation challenges for this part. Extracted from overall_ffa and design_drawbacks. Remove duplicates."
    )
    part_improvements: List[str] = Field(
        ...,
        description="Specific improvement suggestions for this part. Extracted from improvements field."
    )


class FFAReportDestilled(BaseModel):
    """
    Destilled FFA Report for a single assembly.
    Aggregates key findings from FFA assessment into management-friendly format.
    """
    assembly_name: str = Field(..., description="Assembly name (e.g., 'AS2814 motor assembly')")
    assembly_drawbacks: List[str] = Field(
        ...,
        description=(
            "Unique assembly-level automation challenges. "
            "Aggregate across ALL steps using overall_ffa and design_drawbacks. "
            "Remove duplicate items (if same challenge mentioned in multiple steps, include only once). "
            "Keep as bullet points or concise statements."
        )
    )
    assembly_improvements: List[str] = Field(
        ...,
        description=(
            "Specific improvement recommendations at assembly level. "
            "Extracted from improvements field across all steps, filtered for assembly-level measures. "
            "Remove duplicates."
        )
    )
    parts: List[PartDrawbacks] = Field(
        ...,
        description="List of PartDrawbacks for each unique part_id present in the assembly."
    )


# ============================================================================
# FFA REPORTER STRUCTURED OUTPUT
# ============================================================================

class StepAutomatability(BaseModel):
    """Automatability assessment per subprocess for a single step."""
    step_id: int = Field(..., description="Assembly step number (1, 2, 3, ...)")
    step_description: List[str] = Field(..., description="High-level description of this assembly step (1-2 sentences per bullet, covering what parts are involved, what the step achieves). CRITICAL: Append [] to every statement for validation tracking.\"")

    separation_potential: List[str] = Field(..., description="Automation potential for separation subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    separation_risks: List[str] = Field(..., description="Identified risks or constraints for separation subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")  
    handling_potential: List[str] = Field(..., description="Automation potential for handling subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    handling_risks: List[str] = Field(..., description="Identified risks or constraints for handling subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    positioning_potential: List[str] = Field(..., description="Automation potential for positioning subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    positioning_risks: List[str] = Field(..., description="Identified risks or constraints for positioning subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    joining_potential: List[str] = Field(..., description="Automation potential for joining subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")
    joining_risks: List[str] = Field(..., description="Identified risks or constraints for joining subprocess TAKE THE CONTENT FROM THE FFA ASSESSMENT OVERALL_FFA NO CHANGES. CRITICAL: Append [] to every statement for validation tracking.")


class AssemblyLevelFindings(BaseModel):
    """Assembly-level (cross-step) automation analysis."""
    drawbacks: List[str] = Field(
        ...,
        description=(
            "Aggregated and deduplicated design drawbacks at assembly level across all steps. "
            "Only synthesize what is actually present in the FFA assessment — do NOT invent new issues. "
            "Only give design related issues / flaws here. Do not talk about fixture or gripper related stuff that is not backed by actual design"
            "Bullet points, 1-2 sentences each. CRITICAL: Append [] to every statement for validation tracking."
        )
    )
    improvements: List[str] = Field(
        ...,
        description=(
            "Aggregated and deduplicated improvement measures at assembly level across all steps. "
            "Only use measures actually mentioned in the FFA assessment — do NOT propose new ones. "
            "Bullet points, 1-2 sentences each. CRITICAL: Append [] to every statement for validation tracking."
        )
    )


class PartLevelFindings(BaseModel):
    """Part-level automation analysis with BOM enrichment."""
    part_id: str = Field(..., description="Part identifier (e.g., 'part_001', 'part_002')")
    
    # BOM enrichment fields (as bullet-point lists)
    geometric_characteristics: List[str] = Field(
        ...,
        description="Geometric summary as bullet points: shape, dimensions, symmetry, key features (1-2 sentences per bullet). CRITICAL: Append [] to every statement for validation tracking."
    )
    material: List[str] = Field(
        ...,
        description="Material and mechanical properties as bullet points (1-2 sentences per bullet). CRITICAL: Append [] to every statement for validation tracking."
    )
    nature_of_provision_guess: List[str] = Field(
        ...,
        description="Supply/packaging method as bullet points (1-2 sentences per bullet). CRITICAL: Append [] to every statement for validation tracking."
    )
    gripping_analysis: List[str] = Field(
        ...,
        description="Feasible gripping methods and considerations as bullet points (1-2 sentences per bullet). CRITICAL: Append [] to every statement for validation tracking."
    )
    handling_implications: List[str] = Field(
        ...,
        description="Automation challenges for handling as bullet points (1-2 sentences per bullet). CRITICAL: Append [] to every statement for validation tracking."
    )
    
    # FFA findings
    drawbacks: List[str] = Field(
        ...,
        description=(
            "Aggregated and deduplicated design drawbacks for this part across all steps where it appears. "
            "Only synthesize what is actually in the FFA assessment — do NOT invent new issues. "
            "Bullet points, 1-2 sentences each. CRITICAL: Append [] to every statement for validation tracking."
        )
    )
    improvements: List[str] = Field(
        ...,
        description=(
            "Aggregated and deduplicated improvement measures for this part across all steps. "
            "Only use measures actually mentioned in the FFA assessment — do NOT propose new ones. "
            "Bullet points, 1-2 sentences each. CRITICAL: Append [] to every statement for validation tracking."
        )
    )


class FFAReportPerAssembly(BaseModel):
    """
    FFA Reporter Output: Summarized FFA Assessment per Assembly.
    
    Aggregates findings from full FFA assessment into three levels:
    1. Assembly overview information (name, description, part counts)
    2. Step-level automatability (per subprocess)
    3. Assembly-level findings (cross-step synthesis)
    4. Part-level findings (per unique part_id)
    
    CRITICAL: This node shall NOT invent anything — only use provided content from FFA assessment.
    All content is deduplicated and aggregated from the source FFA assessment.
    """
    
    # Assembly overview information (at top)
    assembly_name: str = Field(..., description="Assembly name from FFA assessment")
    assembly_name_guess: str = Field(..., description="Assembly name from overview analysis")
    total_parts: int = Field(..., description="Total number of parts (including copies)")
    unique_parts: int = Field(..., description="Number of unique parts")
    assembly_description: List[str] = Field(..., description="Detailed assembly description from overview as bullet points (context, parts, layout, function). CRITICAL: Append [] to every statement for validation tracking.")
    primary_function: List[str] = Field(..., description="Primary functional purpose of the assembly as bullet points (1-2 sentences each). CRITICAL: Append [] to every statement for validation tracking.")
    
    # Assessment data
    total_steps: int = Field(..., description="Total number of assembly steps")
    
    steps: List[StepAutomatability] = Field(
        ...,
        description="Per-step automatability assessment across all 4 subprocesses"
    )
    
    assembly_level: AssemblyLevelFindings = Field(
        ...,
        description="Cross-step synthesis of assembly-level design issues and improvements"
    )
    
    parts: List[PartLevelFindings] = Field(
        ...,
        description="Per-part synthesis of challenges and improvements across all steps"
    )
    
    # Metadata
    report_created_at: Optional[str] = Field(None, description="ISO timestamp of report creation")
    llm_model: Optional[str] = Field(None, description="LLM model used for FFA Reporter")


class FFAReportSynthesisOnly(BaseModel):
    """
    Lean FFA Reporter LLM output.

    Step-level subprocess fields are copied deterministically from
    ffa_assessment.step_assessments[].assessment.overall_ffa by workflow.py.
    This schema keeps the LLM focused on overview, assembly-level, and part-level
    synthesis only, while the saved report still matches FFAReportPerAssembly.
    """

    assembly_name: str = Field(..., description="Assembly name from FFA assessment")
    assembly_name_guess: str = Field(..., description="Assembly name from overview analysis")
    total_parts: int = Field(..., description="Total number of parts (including copies)")
    unique_parts: int = Field(..., description="Number of unique parts")
    assembly_description: List[str] = Field(..., description="Detailed assembly description as bullet points. CRITICAL: Append [] to every statement for validation tracking.")
    primary_function: List[str] = Field(..., description="Primary functional purpose as bullet points. CRITICAL: Append [] to every statement for validation tracking.")
    total_steps: int = Field(..., description="Total number of assembly steps")
    assembly_level: AssemblyLevelFindings = Field(..., description="Cross-step synthesis of assembly-level design issues and improvements")
    parts: List[PartLevelFindings] = Field(..., description="Per-part synthesis of challenges and improvements across all steps")
    report_created_at: Optional[str] = Field(None, description="ISO timestamp of report creation")
    llm_model: Optional[str] = Field(None, description="LLM model used for FFA Reporter")


# ============================================================================
# AUTOMATION PLANNER V1 MODELS
# ============================================================================

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

# Main output schema for automation_planner/03_automatisierungsvarianten/variante_{strategie}.json
class AutomatisierungsGesamtkonzept(BaseModel):
    varianten_id: str = Field(..., description="Identifier for this automation concept variant. Based on assembly name and strategy.")
    strategie: Literal["manuell", "halbautomatisiert", "vollautomatisiert"] = Field(..., description="Automation strategy represented by this concept.")
    montageablauf: List[MontageablaufEintrag] = Field(..., description="Overall assembly flow in binding assembly order.")
    challenge: List[str] = Field(..., description="Challenge yourself real quick. Are all parts and assembly steps covered in the ablaufbeschreibung? Are there any missing steps or missing parts? If so: make a remark whats missing so u can check it later. Bullet Points.")
    stationen: List[AutomatisierungsKonzeptStation] = Field(..., description="After you thought about the assembly flow and have the remarks. Plan the stations of the layout. High-level station structure for this overall automation concept in process order.")
    stationen_transfer: str = Field(..., description="Based on the stations, how is the assembly or subassembly transferred between stations? Describe the transfer method, orientation, and any special requirements for handover. if we have only one station N/A")


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



# Output folder: automation_planner/04_variantenbewertungen/bewertung_{strategie}.json
class Variantenbewertung(BaseModel):
    varianten_id: str = Field(..., description="Variant identifier matching AutomatisierungsGesamtkonzept.varianten_id.")
    feedback: List[str] = Field(default_factory=list, description="Main technical strengths and risks of the concept.")
    massnahmen: List[AutomationPlannerMeasure] = Field(default_factory=list, description="Measures recommended before continuing this variant.")
    empfehlung_fuer_weiterplanung: str = Field(..., description="Recommendation for whether and how this concept should be continued.")


# Output folder: automation_planner/05_stationsplanung/stationskonzept_{strategie}.json
class StationsMontageschritt(BaseModel):
    montageschritt_nr: int = Field(..., description="Assembly step number assigned to this station.")
    prozessprinzip: str = Field(..., description="Selected process principle or strategy-specific realization for this step.")
    ressourcen: List[str] = Field(default_factory=list, description="Main human or technical resources and equipment needed in this station for this step.")

class Station(BaseModel):
    stations_nr: int = Field(..., description="Stable station number used by workplace-design calls.")
    stationsname: str = Field(..., description="Short station name.")
    stationsfunktion: str = Field(..., description="Main technical purpose of the station.")
    zugeordnete_montageschritte: List[StationsMontageschritt] = Field(..., description="Assembly steps assigned to this station.")
    technische_einrichtungen: List[str] = Field(default_factory=list, description="Core station equipment, tools, fixtures, sensors, or transport devices.")
    layout_station: str = Field(..., description="Concise description of the station layout components.")
    layout_gesamt: str = Field(..., description="Describe the overall layout of used equipment, stations, etc.")

# Main output schema for automation_planner/05_stationsplanung/stationskonzept_{strategie}.json
class Stationskonzept(BaseModel):
    varianten_id: str = Field(..., description="Variant identifier this station concept belongs to.")
    beschreibung_gesamtkonzept: str = Field(..., description="Compact line or station concept description.")
    massnahmen: List[AutomationPlannerMeasure] = Field(default_factory=list, description="Measures that affect more than one station.")
    stationen: List[Station] = Field(..., description="Stations in process order.")


# Output folder: automation_planner/06_montageplatzgestaltung/station_{stations_nr}_{strategie}.json
class DetailliertesStationskonzept(BaseModel):
    stations_nr: int = Field(..., description="Station number matching Station.stations_nr.")
    technische_beschreibung: str = Field(..., description="Compact technical description of the station design.")
    stationsablauf: List[str] = Field(..., description="Detailed station-cycle sequence as concise ordered text steps.")
    equipment: List[str] = Field(default_factory=list, description="Core equipment, tools, fixtures, handling devices, or feeding systems in this station.")
    absicherung_und_pruefung: List[str] = Field(default_factory=list, description="Safety, sensor, inspection, and process-assurance measures.")
    offene_konstruktionsaufgaben: List[str] = Field(default_factory=list, description="Open design tasks for this station.")
    offene_nutzerfragen: List[str] = Field(default_factory=list, description="Questions that require user or domain-expert input.")

# Output folder: automation_planner/06_montageplatzgestaltung/detailliertes_anlagenkonzept_{strategie}.json
class DetailliertesAnlagenkonzept(BaseModel):
    varianten_id: str = Field(..., description="Variant identifier this detailed plant concept belongs to.")
    stationen: List[DetailliertesStationskonzept] = Field(..., description="Detailed station concepts in station order.")
    uebergeordnete_massnahmen: List[AutomationPlannerMeasure] = Field(default_factory=list, description="Aggregated measures that apply across the detailed plant concept.")
